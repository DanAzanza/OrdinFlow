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
    """Parses page numbers/ranges (e.g. '1-3, 5', [1, 2], 'all') into a 1-based page list."""
    if isinstance(val, list):
        return [int(x) for x in val if str(x).isdigit()]
    if isinstance(val, int):
        return [val]
    if isinstance(val, str):
        val = val.strip()
        if not val or val.lower() in ("all", "*", "alle"):
            return list(range(1, total_pages + 1))
        pages: set[int] = set()
        for part in val.split(","):
            p = part.strip()
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


def _resolve_split_source(context: str, folder: str | None, filename: str) -> tuple[str | None, tuple[Any, int] | None]:
    """Validates and resolves the source document path for split inspection."""
    if not DashboardState.config:
        return None, (jsonify({"error": "Config not available"}), 503)

    if context == "cases":
        if not folder:
            return None, (jsonify({"error": "Folder is required for cases context"}), 400)
        src_path = os.path.join(DashboardState.config.target_base_dir, folder, filename)
        if not os.path.isfile(src_path):
            return None, (jsonify({"error": "File not found"}), 404)
        if not _is_within_base(src_path, DashboardState.config.target_base_dir):
            return None, (jsonify({"error": "Access denied"}), 403)
    else:
        src_path = os.path.join(DashboardState.config.watch_dir, filename)
        if not os.path.isfile(src_path):
            return None, (jsonify({"error": "File not found"}), 404)
        if not _is_within_base(src_path, DashboardState.config.watch_dir):
            return None, (jsonify({"error": "Access denied"}), 403)

    return src_path, None


def _slice_or_move_document(
    doc_sec: dict[str, Any],
    src_path: str,
    ext: str,
    is_pdf: bool,
    total_pages: int,
    pdf_doc: Any,
    is_multi_doc: bool,
) -> dict[str, str]:
    """Renders target destination and slices PDF pages or moves full file."""
    data = dict(doc_sec)
    doc_type = str(
        data.get("document") or data.get("Document") or data.get("dokument") or data.get("Dokument") or "Document"
    ).strip()
    data["Document"] = doc_type

    target_folder = _render_target_folder(data, doc_type)
    target_dir = os.path.join(DashboardState.config.target_base_dir, target_folder)
    os.makedirs(target_dir, exist_ok=True)

    target_filename = _render_target_filename(data, doc_type, ext)
    target_filename, target_path = _deduplicate_filename(target_dir, target_filename)

    pages_to_extract = _parse_pages_input(data.get("pages"), total_pages)
    should_slice = (
        is_pdf and fitz is not None and pdf_doc is not None and (is_multi_doc or len(pages_to_extract) < total_pages)
    )

    if should_slice and fitz is not None and pdf_doc is not None:
        with fitz.open() as new_doc:
            for p_idx in pages_to_extract:
                if 1 <= p_idx <= total_pages:
                    new_doc.insert_pdf(pdf_doc, from_page=p_idx - 1, to_page=p_idx - 1)
            new_doc.save(target_path)
    else:
        if os.path.abspath(src_path) != os.path.abspath(target_path):
            shutil.move(src_path, target_path)

    return {"folder": target_folder, "file": target_filename}


def _cleanup_empty_case_folder(folder: str) -> None:
    """Removes empty process folder if no remaining documents exist."""
    src_dir = os.path.join(DashboardState.config.target_base_dir, folder)
    if not os.path.exists(src_dir):
        return
    try:
        remaining = os.listdir(src_dir)
        doc_files = [f for f in remaining if not f.lower().endswith(".meta") and f.lower() != "desktop.ini"]
        if not doc_files:
            for f in remaining:
                try:
                    os.remove(os.path.join(src_dir, f))
                except OSError as e:
                    logger.debug("Could not remove auxiliary file %s during cleanup: %s", f, e)
            os.rmdir(src_dir)
    except OSError as e:
        logger.warning("Could not remove empty process folder %s: %s", src_dir, e)


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
        single_doc = {
            k: (v.strip() if isinstance(v, str) else v)
            for k, v in raw_data.items()
            if k not in ("context", "filename", "folder", "documents")
        }
        documents_input = [single_doc]

    src_path, err_resp = _resolve_split_source(context, folder, filename)
    if err_resp is not None:
        return err_resp[0], err_resp[1]
    if not src_path:
        return jsonify({"error": "Failed to resolve file"}), 400

    ext = os.path.splitext(src_path)[1]
    is_pdf = ext.lower() == ".pdf"
    total_pages = 1
    pdf_doc = None

    if is_pdf and fitz is not None:
        try:
            with open(src_path, "rb") as f:
                pdf_doc = fitz.open(stream=f.read(), filetype="pdf")
            total_pages = len(pdf_doc)
        except (OSError, ValueError, RuntimeError, TypeError) as e:
            logger.warning("Could not open PDF for splitting: %s", e)
            is_pdf = False

    processed_results: list[dict[str, str]] = []
    is_multi_doc = len(documents_input) > 1

    try:
        try:
            for doc_sec in documents_input:
                res = _slice_or_move_document(
                    doc_sec=doc_sec,
                    src_path=src_path,
                    ext=ext,
                    is_pdf=is_pdf,
                    total_pages=total_pages,
                    pdf_doc=pdf_doc,
                    is_multi_doc=is_multi_doc,
                )
                processed_results.append(res)
        finally:
            if pdf_doc:
                pdf_doc.close()

        _remove_meta_sidecar(src_path)
        if os.path.isfile(src_path):
            try:
                os.remove(src_path)
            except OSError as e:
                logger.debug("Could not remove src_path %s: %s", src_path, e)

        if context == "cases" and folder:
            _cleanup_empty_case_folder(folder)

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
        return jsonify({"error": str(e)}), 500
