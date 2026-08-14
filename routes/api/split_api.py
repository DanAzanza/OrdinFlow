"""Split Inspector API endpoints for manual and multi-document PDF slicing."""

import logging
import os
import shutil
from typing import Any

from flask import Blueprint, jsonify, request

try:
    import fitz
except ImportError:
    fitz = None

from core.skills_engine import SkillManager
from routes.api.document_helpers import (
    _deduplicate_filename,
    _is_within_base,
    _remove_meta_sidecar,
    _render_target_filename,
    _render_target_folder,
)
from routes.state import DashboardState

split_api_bp = Blueprint("api_split", __name__)
logger = logging.getLogger(__name__)


def _parse_pages_input(val: Any, total_pages: int = 999) -> list[int]:
    if isinstance(val, list):
        res = []
        for x in val:
            if str(x).isdigit():
                res.append(int(x))
        return res
    if isinstance(val, int):
        return [val]
    if isinstance(val, str):
        val = val.strip()
        if not val or val.lower() in ("all", "*", "alle"):
            return list(range(1, total_pages + 1))
        pages = set()
        parts = val.split(",")
        for p in parts:
            p = p.strip()
            if "-" in p:
                sub = p.split("-")
                if len(sub) == 2 and sub[0].isdigit() and sub[1].isdigit():
                    s, e = int(sub[0]), int(sub[1])
                    for i in range(min(s, e), max(s, e) + 1):
                        pages.add(i)
            elif p.isdigit():
                pages.add(int(p))
        return sorted([p for p in pages if 1 <= p <= total_pages])
    return list(range(1, total_pages + 1))


def _is_split_enabled_for_import_skill() -> bool:
    if DashboardState.config and hasattr(
        DashboardState.config, "split_multi_documents"
    ):
        return bool(getattr(DashboardState.config, "split_multi_documents", True))

    for skill in SkillManager().list_skills():
        if skill.get("type") == "import" and skill.get("enabled", True):
            return bool(skill.get("split_multi_documents", True))
    return True


@split_api_bp.route("/api/split_inspector/submit", methods=["POST"])
def api_split_inspector_submit():
    if not DashboardState.config:
        return jsonify({"error": "Config not available"}), 503

    raw_data = request.get_json() or {}
    context = raw_data.get("context", "inbox")
    filename = raw_data.get("filename")
    folder = raw_data.get("folder")

    if not filename:
        return jsonify({"error": "Filename is required"}), 400

    documents_input = raw_data.get("documents")
    if not documents_input or not isinstance(documents_input, list):
        # Fallback to single document payload
        single_doc = {}
        for k, v in raw_data.items():
            if k in ("context", "filename", "folder", "documents"):
                continue
            single_doc[k] = v.strip() if isinstance(v, str) else v
        documents_input = [single_doc]

    if context == "cases":
        if not folder:
            return jsonify({"error": "Folder is required for cases context"}), 400
        src_path = os.path.join(DashboardState.config.target_base_dir, folder, filename)
        if not os.path.isfile(src_path):
            return jsonify({"error": "File not found"}), 404
        if not _is_within_base(src_path, DashboardState.config.target_base_dir):
            return jsonify({"error": "Access denied"}), 403
    else:
        src_path = os.path.join(DashboardState.config.watch_dir, filename)
        if not os.path.isfile(src_path):
            return jsonify({"error": "File not found"}), 404
        if not _is_within_base(src_path, DashboardState.config.watch_dir):
            return jsonify({"error": "Access denied"}), 403

    ext = os.path.splitext(src_path)[1]
    is_pdf = ext.lower() == ".pdf"

    total_pages = 1
    pdf_doc = None
    if is_pdf and fitz is not None:
        try:
            with open(src_path, "rb") as f:
                pdf_bytes = f.read()
            pdf_doc = fitz.open(stream=pdf_bytes, filetype="pdf")  # type: ignore[union-attr]
            total_pages = len(pdf_doc)
        except (OSError, ValueError, RuntimeError, TypeError) as e:
            logger.warning("Could not open PDF for splitting: %s", e)
            is_pdf = False

    processed_results = []
    is_multi_doc_submit = len(documents_input) > 1

    try:
        for doc_sec in documents_input:
            data = dict(doc_sec)
            doc_type = str(
                data.get("document") or data.get("Document") or data.get("dokument") or data.get("Dokument") or "Document"
            ).strip()
            data["Document"] = doc_type

            target_folder = _render_target_folder(data, doc_type)
            target_dir = os.path.join(
                DashboardState.config.target_base_dir, target_folder
            )
            os.makedirs(target_dir, exist_ok=True)

            target_filename = _render_target_filename(data, doc_type, ext)
            target_filename, target_path = _deduplicate_filename(
                target_dir, target_filename
            )

            pages_to_extract = _parse_pages_input(data.get("pages"), total_pages)
            should_slice = is_pdf and fitz is not None and pdf_doc is not None and (
                is_multi_doc_submit or len(pages_to_extract) < total_pages
            )

            if should_slice:
                new_doc = fitz.open()  # type: ignore[union-attr]
                for p_idx in pages_to_extract:
                    if 1 <= p_idx <= total_pages:
                        new_doc.insert_pdf(
                            pdf_doc, from_page=p_idx - 1, to_page=p_idx - 1
                        )
                new_doc.save(target_path)
                new_doc.close()
            else:
                if os.path.abspath(src_path) != os.path.abspath(target_path):
                    shutil.move(src_path, target_path)

            processed_results.append({"folder": target_folder, "file": target_filename})

        if pdf_doc:
            pdf_doc.close()

        # Clean up source sidecar and file
        _remove_meta_sidecar(src_path)
        if os.path.isfile(src_path):
            try:
                os.remove(src_path)
            except OSError:
                pass

        if context == "cases" and folder:
            src_dir = os.path.join(DashboardState.config.target_base_dir, folder)
            if os.path.exists(src_dir):
                try:
                    remaining_files = os.listdir(src_dir)
                    doc_files = [
                        f
                        for f in remaining_files
                        if not f.lower().endswith(".meta")
                        and f.lower() != "desktop.ini"
                    ]
                    if not doc_files:
                        for f in remaining_files:
                            try:
                                os.remove(os.path.join(src_dir, f))
                            except OSError:
                                pass
                        os.rmdir(src_dir)
                except OSError as e:
                    logger.warning(
                        "Could not remove empty process folder %s: %s", src_dir, e
                    )

        logger.info(
            "[Dashboard] Inspector submit (%s): %s -> %d document(s) processed.",
            context,
            filename,
            len(processed_results),
        )
        return jsonify(
            {
                "status": "ok",
                "message": f"{len(processed_results)} document(s) processed successfully!",
                "results": processed_results,
            }
        )
    except (OSError, RuntimeError, ValueError, TypeError) as e:
        logger.error("Error in split inspector submit: %s", e, exc_info=True)
        if pdf_doc:
            pdf_doc.close()
        return jsonify({"error": str(e)}), 500
