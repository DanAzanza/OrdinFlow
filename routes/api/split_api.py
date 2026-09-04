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

from core.utils import cleanup_empty_folder, safe_join_path
from routes.api.document_helpers import (
    _deduplicate_filename,
    _is_within_base,
    _remove_meta_sidecar,
    _render_target_filename,
    _render_target_folder,
    _resolve_and_guard,
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
        subpath = os.path.join(folder, filename)
        return _resolve_and_guard(subpath, DashboardState.config.target_base_dir, require_type="file")
    else:
        return _resolve_and_guard(filename, DashboardState.config.watch_dir, require_type="file")


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
    target_dir = safe_join_path(DashboardState.config.target_base_dir, target_folder)
    if not target_dir or not _is_within_base(target_dir, DashboardState.config.target_base_dir):
        raise PermissionError(f"Access denied: Target directory outside base '{target_folder}'")
    os.makedirs(target_dir, exist_ok=True)

    target_filename = _render_target_filename(data, doc_type, ext)
    target_filename, target_path = _deduplicate_filename(target_dir, target_filename)
    if not _is_within_base(target_path, DashboardState.config.target_base_dir):
        raise PermissionError(f"Access denied: Target file outside base '{target_filename}'")

    pages_to_extract = _parse_pages_input(data.get("pages"), total_pages)
    should_slice = (
        is_pdf and fitz is not None and pdf_doc is not None and (is_multi_doc or len(pages_to_extract) < total_pages)
    )

    if should_slice and fitz is not None and pdf_doc is not None:
        with fitz.open() as new_doc:
            for p_idx in pages_to_extract:
                if 1 <= p_idx <= total_pages:
                    new_doc.insert_pdf(pdf_doc, from_page=p_idx - 1, to_page=p_idx - 1)
            new_doc.save(target_path, garbage=4, deflate=True, clean=True)
    else:
        if os.path.abspath(src_path) != os.path.abspath(target_path):
            shutil.move(src_path, target_path)

    return {"folder": target_folder, "file": target_filename}


@split_api_bp.route("/api/split_inspector/submit", methods=["POST"])
def api_split_inspector_submit():
    if not DashboardState.config:
        return jsonify({"error": "Config not available"}), 503

    from routes.schemas import SplitInspectorSubmitSchema, validate_schema

    raw_data = request.get_json(silent=True)
    if not isinstance(raw_data, dict):
        return jsonify({"error": "Invalid request payload (dictionary expected)"}), 400

    validated, schema_err = validate_schema(SplitInspectorSubmitSchema, raw_data)
    if not validated or schema_err:
        return jsonify({"error": schema_err or "Invalid request payload"}), 400

    context = validated.context
    filename = validated.filename
    folder = validated.folder
    documents_input = validated.documents or [
        {
            k: (v.strip() if isinstance(v, str) else v)
            for k, v in raw_data.items()
            if k not in ("context", "filename", "folder", "documents")
        }
    ]

    src_path, err_resp = _resolve_split_source(context, folder, filename)
    if err_resp is not None:
        return err_resp[0], err_resp[1]
    if not src_path:
        return jsonify({"error": "Failed to resolve file"}), 400

    ext = os.path.splitext(src_path)[1]
    is_pdf = ext.lower() == ".pdf"
    total_pages = 1
    pdf_doc = None

    if not is_pdf and len(documents_input) > 1:
        return jsonify({"error": "Multi-document slicing is only supported for PDF files."}), 400

    if is_pdf and fitz is not None:
        try:
            with open(src_path, "rb") as f:
                pdf_doc = fitz.open(stream=f.read(), filetype="pdf")
            total_pages = len(pdf_doc)
        except (OSError, ValueError, RuntimeError, TypeError) as e:
            logger.warning("Could not open PDF for splitting: %s", e)
            is_pdf = False

    # Atomic pre-validation of all section page ranges before any file slicing or folder creation
    if is_pdf:
        for sec_idx, doc_sec in enumerate(documents_input, 1):
            doc_type = str(doc_sec.get("document") or doc_sec.get("Document") or "Document").strip()
            pages_to_extract = _parse_pages_input(doc_sec.get("pages"), total_pages)
            if len(pages_to_extract) == 0:
                if pdf_doc:
                    pdf_doc.close()
                return (
                    jsonify(
                        {
                            "error": f"Invalid or empty page range '{doc_sec.get('pages')}' in section {sec_idx} ({doc_type}). Total document pages: {total_pages}"
                        }
                    ),
                    400,
                )

    if DashboardState.processor:
        with DashboardState.processor.processing_lock:
            DashboardState.processor.processing_files.discard(src_path)

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
            cleanup_empty_folder(
                os.path.join(DashboardState.config.target_base_dir, folder),
                stop_at=DashboardState.config.target_base_dir,
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
        return jsonify({"error": "Failed to process split documents"}), 500
