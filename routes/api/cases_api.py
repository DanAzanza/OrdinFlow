"""Cases & process folder API endpoints for DMS backend."""

import json
import logging
import os
import time
import urllib.parse
from typing import Any

from flask import Blueprint, jsonify, request, send_file

from core.skills import get_skill_manager
from core.skills.case_router import extract_all_skill_document_types
from core.utils import cleanup_empty_folder, safe_join_path, send_to_trash
from routes.api.document_helpers import (
    _MIME_MAP,
    _deduplicate_filename,
    _generate_pdf_thumbnail,
    _is_within_base,
    _parse_folder_name,
    _remove_meta_sidecar,
    _render_target_filename,
    _render_target_folder,
    _resolve_and_guard,
    _validate_required_api_fields,
    load_meta_sidecar,
    safe_move_with_meta,
)
from routes.schemas import (
    FlexibleDocumentPayload,
    FolderEditSchema,
    validate_schema,
)
from routes.state import DashboardState

cases_api_bp = Blueprint("api_cases", __name__)
logger = logging.getLogger(__name__)


def _get_skill_manager():
    return get_skill_manager()


def _extract_file_doc_type(fname: str, f_meta: dict[str, Any], delimiter: str) -> str:
    """Extracts document type from .meta sidecar or falls back to filename splitting."""
    f_doc_type = f_meta.get("Document") or f_meta.get("Dokument") or f_meta.get("document_type") or "UNKNOWN"
    if f_doc_type == "UNKNOWN" and "__" in fname:
        parts = fname.split("__")
        if len(parts) >= 2:
            return parts[0]
    if f_doc_type == "UNKNOWN" and delimiter and delimiter in fname:
        parts = fname.split(delimiter)
        if len(parts) >= 1:
            return parts[0]
    return f_doc_type


def _build_case_folder_summary(
    folder_rel_path: str,
    folder_abs_path: str,
    export_skills: list[dict[str, Any]],
    delimiter: str,
) -> dict[str, Any] | None:
    """Inspects a candidate case folder and builds a normalized summary dictionary or None."""
    try:
        folder_entries = sorted(os.scandir(folder_abs_path), key=lambda e: e.name)
    except OSError as e:
        logger.debug("[Dashboard] Could not scandir folder %s: %s", folder_abs_path, e)
        return None

    is_approved = False
    files: list[str] = []
    for fe in folder_entries:
        if fe.name == ".approved":
            is_approved = True
        elif fe.is_file() and not fe.name.startswith(".") and not fe.name.lower().endswith((".jpg", ".meta")):
            files.append(fe.name)

    folder_rel_posix = folder_rel_path.replace("\\", "/")
    folder_basename = os.path.basename(folder_abs_path)
    is_top_level = "/" not in folder_rel_posix
    has_delimiter = bool(delimiter and delimiter in folder_basename)
    has_content = bool(files or is_approved)

    if not ((is_top_level and has_delimiter) or has_content):
        return None

    parsed = _parse_folder_name(folder_basename)

    skill_types_map: list[tuple[str, list[str]]] = []
    for s in export_skills:
        s_id = str(s.get("id") or "")
        if s_id:
            all_types = extract_all_skill_document_types(s)
            skill_types_map.append((s_id, [t.lower().strip() for t in all_types if isinstance(t, str)]))

    doc_types_set: set[str] = set()
    folder_executed_skills: set[str] = set()
    total_applicable_tasks = 0
    completed_applicable_tasks = 0
    files_with_any_export = 0

    for fname in files:
        meta_fp = os.path.join(folder_abs_path, fname + ".meta")
        f_meta: dict[str, Any] = load_meta_sidecar(meta_fp) or {}
        f_doc_type = _extract_file_doc_type(fname, f_meta, delimiter)

        if f_doc_type != "UNKNOWN":
            for dt in f_doc_type.split("+"):
                dt_clean = dt.strip()
                if dt_clean:
                    doc_types_set.add(dt_clean)

        raw_executed = f_meta.get("executed_skills", [])
        executed_skills = [str(sid) for sid in raw_executed] if isinstance(raw_executed, list) else []
        for s_id in executed_skills:
            folder_executed_skills.add(s_id)

        if executed_skills:
            files_with_any_export += 1

        doc_subtypes = [t.strip().lower() for t in f_doc_type.split("+") if t.strip()]
        for s_id, s_types in skill_types_map:
            if "*" in s_types or "all" in s_types or any(st in s_types for st in doc_subtypes):
                total_applicable_tasks += 1
                if s_id in executed_skills:
                    completed_applicable_tasks += 1

    if not is_approved:
        export_status = "pending_approval"
    elif total_applicable_tasks > 0 and completed_applicable_tasks >= total_applicable_tasks:
        export_status = "completed"
    elif files_with_any_export > 0 or completed_applicable_tasks > 0:
        export_status = "partially_exported"
    else:
        export_status = "approved"

    return {
        "folder": folder_rel_posix,
        "display_title": parsed.get("display_title", folder_basename),
        "person": parsed.get("person") or parsed.get("Person") or folder_basename,
        "datum": parsed.get("datum") or parsed.get("Datum") or "",
        "produkt": parsed.get("produkt") or parsed.get("Produkt") or "",
        "parts": parsed.get("parts", []),
        "doc_types": sorted(doc_types_set),
        "file_count": len(files),
        "is_approved": is_approved,
        "export_status": export_status,
        "executed_skills": sorted(folder_executed_skills),
        "total_applicable_tasks": total_applicable_tasks,
        "completed_applicable_tasks": completed_applicable_tasks,
    }


@cases_api_bp.route("/api/cases")
def api_cases():
    if not DashboardState.config:
        return jsonify([])
    base_dir = DashboardState.config.target_base_dir
    if not os.path.exists(base_dir):
        return jsonify([])

    delimiter = getattr(DashboardState.config, "folder_delimiter", "--") or "--"
    skill_mgr = _get_skill_manager()
    export_skills = [
        s for s in skill_mgr.list_skills() if s.get("type", "export") == "export" and s.get("enabled", True)
    ]

    result: list[dict[str, Any]] = []
    for root, dirs, _ in os.walk(base_dir):
        dirs[:] = sorted([d for d in dirs if not d.startswith(".")])
        if os.path.abspath(root) == os.path.abspath(base_dir):
            continue

        rel_path = os.path.relpath(root, base_dir)
        summary = _build_case_folder_summary(rel_path, root, export_skills, delimiter)
        if summary is not None:
            result.append(summary)
            if summary["file_count"] > 0 or summary["is_approved"]:
                dirs.clear()

    result.sort(key=lambda item: str(item["folder"]))
    return jsonify(result)


@cases_api_bp.route("/api/cases/approve", methods=["POST"])
def api_cases_approve():
    if not DashboardState.config:
        return jsonify({"error": "Config not available"}), 503

    from routes.schemas import CaseApprovalSchema

    validated, err = validate_schema(CaseApprovalSchema, request.get_json())
    if not validated or err:
        return jsonify({"error": err or "Invalid payload"}), 400

    folder_name = validated.folder
    approved = validated.approved

    target_base = DashboardState.config.target_base_dir
    folder_path, guard_err = _resolve_and_guard(
        folder_name,
        target_base,
        require_type="dir",
        allow_root=False,
    )
    if guard_err is not None:
        return guard_err[0], guard_err[1]
    if not folder_path:
        return jsonify({"error": "Folder not found"}), 404

    marker_path = os.path.join(folder_path, ".approved")
    try:
        if approved:
            with open(marker_path, "w", encoding="utf-8") as f:
                f.write(f"Approved at {time.ctime()}\n")
            logger.info("[Dashboard] Approved case folder: %s", folder_name)
        else:
            if os.path.exists(marker_path):
                os.remove(marker_path)
            logger.info("[Dashboard] Revoked approval for case folder: %s", folder_name)
        return jsonify(
            {
                "status": "ok",
                "folder": folder_name,
                "is_approved": bool(approved),
            }
        )
    except OSError as e:
        logger.error("[Dashboard] Failed to toggle approval for %s: %s", folder_name, e, exc_info=True)
        return jsonify({"error": "Failed to update approval status"}), 500


def _safe_rename_dir(src: str, dst: str, retries: int = 5, delay: float = 0.15) -> None:
    """Renames a directory with exponential backoff on transient Windows file locks."""
    for attempt in range(retries):
        try:
            os.rename(src, dst)
            return
        except (PermissionError, OSError):
            if attempt == retries - 1:
                raise
            time.sleep(delay * (2**attempt))


@cases_api_bp.route("/api/cases/<path:folder_name>")
def api_cases_detail(folder_name: str):
    if not DashboardState.config:
        return jsonify({"error": "Config not available"}), 503
    folder_path, guard_err = _resolve_and_guard(
        folder_name, DashboardState.config.target_base_dir, require_type="dir"
    )
    if guard_err is not None:
        return guard_err[0], guard_err[1]
    if not folder_path:
        return jsonify({"error": "Folder not found"}), 404

    files = []
    for f in sorted(os.listdir(folder_path)):
        fp = safe_join_path(folder_path, f)
        if fp and os.path.isfile(fp):
            if f.startswith(".") or f.lower().endswith(".jpg") or f.lower().endswith(".meta"):
                continue

            stat = os.stat(fp)
            has_preview = f.lower().endswith(".pdf")
            token_q = f"?token={urllib.parse.quote(DashboardState.session_token)}" if DashboardState.session_token else ""
            preview_url = (
                f"/api/preview/Cases/{urllib.parse.quote(folder_name, safe='/')}/{urllib.parse.quote(f, safe='/')}{token_q}"
                if has_preview
                else ""
            )

            meta_path = fp + ".meta"
            meta_data: dict[str, Any] = {}
            executed_skills: list[str] = []
            doc_type = "UNKNOWN"

            if os.path.exists(meta_path):
                try:
                    with open(meta_path, encoding="utf-8") as mf:
                        loaded = json.load(mf)
                        if isinstance(loaded, dict):
                            meta_data = loaded
                            executed_skills = loaded.get("executed_skills", [])
                            doc_type = (
                                loaded.get("Document")
                                or loaded.get("Dokument")
                                or loaded.get("document_type")
                                or "UNKNOWN"
                            )
                except (json.JSONDecodeError, OSError) as e:
                    logger.debug("Failed reading meta JSON for %s: %s", f, e)

            if doc_type == "UNKNOWN" and "__" in f:
                parts = f.split("__")
                if len(parts) >= 2:
                    doc_type = parts[0]

            files.append(
                {
                    "name": f,
                    "size": stat.st_size,
                    "modified": time.strftime("%Y-%m-%d %H:%M", time.localtime(stat.st_mtime)),
                    "has_preview": has_preview,
                    "preview_url": preview_url,
                    "file_url": f"/api/file/cases/{urllib.parse.quote(folder_name, safe='/')}/{urllib.parse.quote(f, safe='/')}",
                    "is_preview": False,
                    "doc_type": doc_type,
                    "executed_skills": executed_skills if isinstance(executed_skills, list) else [],
                    "meta": meta_data,
                }
            )

    return jsonify({"folder": folder_name, "files": files})


@cases_api_bp.route("/api/cases/<path:folder_name>", methods=["PUT"])
def api_cases_edit(folder_name: str):
    if not DashboardState.config:
        return jsonify({"error": "Config not available"}), 503

    folder_path, guard_err = _resolve_and_guard(
        folder_name, DashboardState.config.target_base_dir, require_type="dir"
    )
    if guard_err is not None:
        return guard_err[0], guard_err[1]
    if not folder_path:
        return jsonify({"error": "Folder not found"}), 404

    validated, err = validate_schema(FolderEditSchema, request.get_json())
    if not validated or err:
        return jsonify({"error": err}), 400
    data = validated.to_clean_dict()

    parsed = _parse_folder_name(folder_name)
    merged_data = dict(parsed)
    merged_data.update(data)
    new_folder_name = _render_target_folder(merged_data)

    if new_folder_name == folder_name:
        return jsonify({"status": "ok", "folder": folder_name})

    new_path = safe_join_path(DashboardState.config.target_base_dir, new_folder_name)
    if not new_path or not _is_within_base(new_path, DashboardState.config.target_base_dir):
        return jsonify({"error": "Access denied"}), 403
    if os.path.exists(new_path):
        return jsonify({"error": "Target folder already exists"}), 409

    try:
        _safe_rename_dir(folder_path, new_path)
        logger.info("[Dashboard] Renamed folder: %s -> %s", folder_name, new_folder_name)
        return jsonify({"status": "ok", "folder": new_folder_name})
    except OSError as e:
        logger.error("[Dashboard] Failed to rename folder %s -> %s: %s", folder_name, new_folder_name, e, exc_info=True)
        return jsonify({"error": "Failed to rename folder"}), 500


@cases_api_bp.route("/api/file/meta/cases/<path:folder>/<filename>")
def api_file_meta_cases(folder: str, filename: str):
    if not DashboardState.config:
        return jsonify({"error": "Config not available"}), 503
    filepath, err = _resolve_and_guard(os.path.join(folder, filename), DashboardState.config.target_base_dir)
    if err is not None:
        return err[0], err[1]
    if not filepath:
        return jsonify({"error": "File not found"}), 404

    data = load_meta_sidecar(filepath)
    if data is not None:
        return jsonify(data)
    return jsonify({"error": "No meta file found"}), 404


@cases_api_bp.route("/api/cases/<path:folder_name>/<filename>/edit", methods=["POST"])
def api_cases_edit_file(folder_name: str, filename: str):
    if not DashboardState.config:
        return jsonify({"error": "Config not available"}), 503

    raw_json = request.get_json(silent=True)
    if not raw_json:
        return jsonify({"error": "No data provided"}), 400

    validated, schema_err = validate_schema(FlexibleDocumentPayload, raw_json)
    if not validated or schema_err:
        return jsonify({"error": schema_err or "Invalid payload"}), 400

    data = validated.to_clean_dict()
    move = bool(raw_json.get("move", True)) if isinstance(raw_json, dict) else True

    doc_type = str(data.get("document") or data.get("Document") or "Document").strip()
    err = _validate_required_api_fields(data, doc_type)
    if err:
        return jsonify({"error": err}), 400

    src_path, guard_err = _resolve_and_guard(os.path.join(folder_name, filename), DashboardState.config.target_base_dir)
    if guard_err is not None:
        return guard_err[0], guard_err[1]
    if not src_path:
        return jsonify({"error": "File not found"}), 404
    if move:
        new_folder_name = _render_target_folder(data, doc_type)
    else:
        new_folder_name = folder_name

    target_dir = safe_join_path(DashboardState.config.target_base_dir, new_folder_name)
    if not target_dir or not _is_within_base(target_dir, DashboardState.config.target_base_dir):
        return jsonify({"error": "Access denied"}), 403
    os.makedirs(target_dir, exist_ok=True)

    ext = os.path.splitext(src_path)[1]
    target_filename = _render_target_filename(data, doc_type, ext)
    target_filename, target_path = _deduplicate_filename(target_dir, target_filename)

    if os.path.abspath(src_path) == os.path.abspath(target_path):
        return jsonify({"status": "ok"})

    try:
        safe_move_with_meta(src_path, target_path)
        logger.info(
            "[Dashboard] Edited file: %s → %s/%s",
            filename,
            new_folder_name,
            target_filename,
        )
        cleanup_empty_folder(os.path.dirname(src_path), stop_at=DashboardState.config.target_base_dir)
        return jsonify({"status": "ok", "folder": new_folder_name, "file": target_filename})
    except OSError as e:
        logger.error("[Dashboard] Failed to edit file %s: %s", src_path, e, exc_info=True)
        return jsonify({"error": "Failed to edit file"}), 500


@cases_api_bp.route("/api/cases/<path:folder_name>/<filename>", methods=["DELETE"])
def api_cases_delete_file(folder_name: str, filename: str):
    if not DashboardState.config:
        return jsonify({"error": "Config not available"}), 503
    filepath, err = _resolve_and_guard(os.path.join(folder_name, filename), DashboardState.config.target_base_dir)
    if err is not None:
        return err[0], err[1]
    if not filepath:
        return jsonify({"error": "File not found"}), 404

    try:
        send_to_trash(filepath)
        _remove_meta_sidecar(filepath, use_trash=True)
        cleanup_empty_folder(os.path.dirname(filepath), stop_at=DashboardState.config.target_base_dir)
        logger.info("[Dashboard] Moved file to trash: %s", filepath)
        return jsonify({"status": "ok"})
    except OSError as e:
        logger.error("[Dashboard] Failed to delete file %s: %s", filepath, e, exc_info=True)
        return jsonify({"error": "Failed to delete file"}), 500


@cases_api_bp.route("/api/cases/<path:folder_name>", methods=["DELETE"])
def api_cases_delete_folder(folder_name: str):
    if not DashboardState.config:
        return jsonify({"error": "Config not available"}), 503
    folder_path, err_resp = _resolve_and_guard(
        folder_name,
        DashboardState.config.target_base_dir,
        require_type="dir",
        allow_root=False,
    )
    if err_resp:
        return err_resp
    if not folder_path:
        return jsonify({"error": "Folder not found"}), 404

    try:
        send_to_trash(folder_path)
        logger.info("[Dashboard] Moved process folder to trash: %s", folder_path)
        return jsonify({"status": "ok"})
    except OSError as e:
        logger.error("[Dashboard] Failed to delete folder %s: %s", folder_path, e, exc_info=True)
        return jsonify({"error": "Failed to delete folder"}), 500





@cases_api_bp.route("/api/file/cases/<path:subpath>")
def api_file_cases(subpath: str):
    if not DashboardState.config:
        return jsonify({"error": "Config not available"}), 503
    full_path, err = _resolve_and_guard(subpath, DashboardState.config.target_base_dir)
    if err:
        return err
    if full_path is None:
        return jsonify({"error": "File not found"}), 404
    ext = os.path.splitext(full_path)[1].lower()
    return send_file(full_path, mimetype=_MIME_MAP.get(ext, "application/octet-stream"))


@cases_api_bp.route("/api/preview/Cases/<path:folder_name>/<path:filename>")
@cases_api_bp.route("/api/preview/cases/<path:folder_name>/<path:filename>")
def api_cases_preview(folder_name: str, filename: str):
    if not DashboardState.config:
        return jsonify({"error": "Config not available"}), 503
    subpath = os.path.join(folder_name, filename)
    full_path, err = _resolve_and_guard(subpath, DashboardState.config.target_base_dir)
    if err:
        return err
    if not full_path:
        return jsonify({"error": "File not found"}), 404
    return _generate_pdf_thumbnail(full_path)
