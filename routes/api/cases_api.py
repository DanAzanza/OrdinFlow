"""Cases & process folder API endpoints for DMS backend."""

import json
import logging
import os
import time
import urllib.parse
from typing import Any

from flask import Blueprint, jsonify, request, send_file

from core.skills import get_skill_manager
from core.utils import cleanup_empty_folder, send_to_trash
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
    FolderEditSchema,
    validate_schema,
)
from routes.state import DashboardState

cases_api_bp = Blueprint("api_cases", __name__)
logger = logging.getLogger(__name__)


def _get_skill_manager():
    return get_skill_manager()


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

    result = []
    try:
        entries = sorted(os.scandir(base_dir), key=lambda e: e.name)
    except OSError as e:
        logger.debug("[Dashboard] Could not scandir %s: %s", base_dir, e)
        return jsonify([])

    for entry in entries:
        if not entry.is_dir():
            continue
        item = entry.name
        if delimiter and delimiter not in item:
            continue

        item_path = entry.path
        parsed = _parse_folder_name(item)

        doc_types_set = set()
        files = []
        is_approved = False

        try:
            folder_entries = os.scandir(item_path)
        except OSError as e:
            logger.debug("[Dashboard] Could not scandir folder %s: %s", item_path, e)
            folder_entries = []

        for fe in folder_entries:
            fname = fe.name
            if fname == ".approved":
                is_approved = True
                continue
            if fe.is_file():
                if (
                    not fname.startswith(".")
                    and not fname.lower().endswith(".jpg")
                    and not fname.lower().endswith(".meta")
                ):
                    files.append(fname)

        # Calculate granular multi-skill execution status
        folder_executed_skills: set[str] = set()
        total_applicable_tasks = 0
        completed_applicable_tasks = 0
        files_with_any_export = 0

        for fname in files:
            meta_fp = os.path.join(item_path, fname + ".meta")
            f_meta: dict[str, Any] = load_meta_sidecar(meta_fp) or {}
            f_doc_type = f_meta.get("Document") or f_meta.get("Dokument") or f_meta.get("document_type") or "UNKNOWN"

            if f_doc_type == "UNKNOWN" and "__" in fname:
                parts = fname.split("__")
                if len(parts) >= 2:
                    f_doc_type = parts[0]

            if f_doc_type == "UNKNOWN" and delimiter and delimiter in fname:
                parts = fname.split(delimiter)
                if len(parts) >= 1:
                    f_doc_type = parts[0]

            if f_doc_type and f_doc_type != "UNKNOWN":
                for dt in f_doc_type.split("+"):
                    dt_clean = dt.strip()
                    if dt_clean:
                        doc_types_set.add(dt_clean)

            executed_skills = f_meta.get("executed_skills", [])
            if not isinstance(executed_skills, list):
                executed_skills = []
            for s_id in executed_skills:
                folder_executed_skills.add(str(s_id))

            if executed_skills:
                files_with_any_export += 1

            # Determine applicable export skills for this file
            applicable_skills = []
            for s in export_skills:
                s_types = [t.lower().strip() for t in s.get("document_types", ["*"]) if isinstance(t, str)]
                if "*" in s_types or "all" in s_types or f_doc_type.lower() in s_types:
                    applicable_skills.append(s.get("id"))

            for app_skill_id in applicable_skills:
                total_applicable_tasks += 1
                if app_skill_id in executed_skills:
                    completed_applicable_tasks += 1

        if not is_approved:
            export_status = "pending_approval"
        elif total_applicable_tasks > 0 and completed_applicable_tasks >= total_applicable_tasks:
            export_status = "completed"
        elif files_with_any_export > 0 or completed_applicable_tasks > 0:
            export_status = "partially_exported"
        else:
            export_status = "approved"

        doc_types = sorted(doc_types_set)

        result.append(
            {
                "folder": item,
                "display_title": parsed.get("display_title", item),
                "person": parsed.get("person") or parsed.get("Person") or item,
                "datum": parsed.get("datum") or parsed.get("Datum") or "",
                "produkt": parsed.get("produkt") or parsed.get("Produkt") or "",
                "parts": parsed.get("parts", []),
                "doc_types": doc_types,
                "file_count": len(files),
                "is_approved": is_approved,
                "export_status": export_status,
                "executed_skills": sorted(list(folder_executed_skills)),
                "total_applicable_tasks": total_applicable_tasks,
                "completed_applicable_tasks": completed_applicable_tasks,
            }
        )
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
    folder_path = os.path.abspath(os.path.join(target_base, folder_name))
    if not _is_within_base(folder_path, target_base) or not os.path.isdir(folder_path):
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
        logger.error("[Dashboard] Failed to toggle approval for %s: %s", folder_name, e)
        return jsonify({"error": str(e)}), 500


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
    folder_path = os.path.join(DashboardState.config.target_base_dir, folder_name)
    if not _is_within_base(folder_path, DashboardState.config.target_base_dir):
        return jsonify({"error": "Access denied"}), 403
    if not os.path.isdir(folder_path):
        return jsonify({"error": "Folder not found"}), 404

    files = []
    for f in sorted(os.listdir(folder_path)):
        fp = os.path.join(folder_path, f)
        if os.path.isfile(fp):
            if f.startswith(".") or f.lower().endswith(".jpg") or f.lower().endswith(".meta"):
                continue

            stat = os.stat(fp)
            has_preview = f.lower().endswith(".pdf")
            preview_url = (
                f"/api/preview/Cases/{urllib.parse.quote(folder_name, safe='/')}/{urllib.parse.quote(f, safe='/')}"
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
                except (json.JSONDecodeError, OSError):
                    pass

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

    folder_path = os.path.join(DashboardState.config.target_base_dir, folder_name)
    if not _is_within_base(folder_path, DashboardState.config.target_base_dir):
        return jsonify({"error": "Access denied"}), 403
    if not os.path.isdir(folder_path):
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

    new_path = os.path.join(DashboardState.config.target_base_dir, new_folder_name)
    if not _is_within_base(new_path, DashboardState.config.target_base_dir):
        return jsonify({"error": "Access denied"}), 403
    if os.path.exists(new_path):
        return jsonify({"error": "Target folder already exists"}), 409

    try:
        _safe_rename_dir(folder_path, new_path)
        logger.info("[Dashboard] Renamed folder: %s -> %s", folder_name, new_folder_name)
        return jsonify({"status": "ok", "folder": new_folder_name})
    except OSError as e:
        return jsonify({"error": str(e)}), 500


@cases_api_bp.route("/api/file/meta/cases/<folder>/<filename>")
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

    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    doc_type = str(data.get("document") or data.get("Document") or "Document").strip()
    err = _validate_required_api_fields(data, doc_type)
    if err:
        return jsonify({"error": err}), 400

    src_path, guard_err = _resolve_and_guard(os.path.join(folder_name, filename), DashboardState.config.target_base_dir)
    if guard_err is not None:
        return guard_err[0], guard_err[1]
    if not src_path:
        return jsonify({"error": "File not found"}), 404

    move = data.get("move", True)
    if move:
        new_folder_name = _render_target_folder(data, doc_type)
    else:
        new_folder_name = folder_name

    target_dir = os.path.join(DashboardState.config.target_base_dir, new_folder_name)
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
        return jsonify({"error": str(e)}), 500


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
        return jsonify({"error": str(e)}), 500


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
        return jsonify({"error": str(e)}), 500





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
    return _generate_pdf_thumbnail(full_path)  # type: ignore[arg-type]
