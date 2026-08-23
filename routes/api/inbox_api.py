"""Inbox document API endpoints for DMS backend."""

import json
import logging
import os
import shutil
import time
import urllib.parse

from flask import Blueprint, jsonify, request, send_file

from core.utils import send_to_trash
from routes.api.document_helpers import (
    _MIME_MAP,
    _deduplicate_filename,
    _generate_pdf_thumbnail,
    _is_within_base,
    _remove_meta_sidecar,
    _render_target_filename,
    _render_target_folder,
    _resolve_and_guard,
    _validate_required_api_fields,
    load_meta_sidecar,
)
from routes.schemas import (
    AssignDocumentSchema,
    validate_schema,
)
from routes.state import DashboardState

inbox_api_bp = Blueprint("api_inbox", __name__)
logger = logging.getLogger(__name__)


@inbox_api_bp.route("/api/inbox")
def api_inbox():
    if not DashboardState.config:
        return jsonify([])
    watch_dir = DashboardState.config.watch_dir
    if not os.path.exists(watch_dir):
        return jsonify([])

    result = []
    for root, dirs, files in os.walk(watch_dir, topdown=True):
        dirs.sort()
        for f in sorted(files):
            fp = os.path.join(root, f)
            if os.path.isfile(fp):
                if f.lower() == "desktop.ini" or f.lower().endswith(".meta"):
                    continue
                stat = os.stat(fp)
                rel_path = os.path.relpath(fp, watch_dir).replace("\\", "/")

                meta_data = load_meta_sidecar(fp)
                is_review = meta_data is not None
                reason = meta_data.get("grund", meta_data.get("reason", "")) if meta_data else ""
                extracted = meta_data.get("extracted", {}) if meta_data else {}

                result.append(
                    {
                        "name": f,
                        "path": rel_path,
                        "reason": reason,
                        "grund": reason,  # Backward compatibility alias
                        "extracted": extracted,
                        "is_review": is_review,
                        "is_pruefen": is_review,  # Backward compatibility alias
                        "size": stat.st_size,
                        "modified": time.strftime("%Y-%m-%d %H:%M", time.localtime(stat.st_mtime)),
                        "preview_url": f"/api/inbox/preview/{urllib.parse.quote(rel_path, safe='/')}"
                        if f.lower().endswith(".pdf")
                        else "",
                        "file_url": f"/api/file/inbox/{rel_path}",
                    }
                )
    return jsonify(result)


@inbox_api_bp.route("/api/file/meta/inbox/<path:filename>")
def api_file_meta_inbox(filename: str):
    if not DashboardState.config:
        return jsonify({"error": "Config not available"}), 503
    filepath, err = _resolve_and_guard(filename, DashboardState.config.watch_dir)
    if err is not None:
        return err[0], err[1]
    if not filepath:
        return jsonify({"error": "File not found"}), 404

    data = load_meta_sidecar(filepath)
    if data is not None:
        return jsonify(data)
    return jsonify({"error": "No meta file found"}), 404


@inbox_api_bp.route("/api/inbox/<path:filename>/retry", methods=["POST"])
def api_inbox_retry(filename: str):
    if not DashboardState.config:
        return jsonify({"error": "Not available"}), 503

    filepath, err = _resolve_and_guard(filename, DashboardState.config.watch_dir)
    if err is not None:
        return err[0], err[1]
    if not filepath:
        return jsonify({"error": "File not found"}), 404

    _remove_meta_sidecar(filepath)
    if DashboardState.processor:
        with DashboardState.processor.processing_lock:
            DashboardState.processor.processing_files.discard(filepath)
    logger.info("[Dashboard] Deleted .meta sidecar: %s", filename)

    try:
        from core.skills.queue import get_skill_queue_manager

        qm = get_skill_queue_manager()
        default_import = qm.skill_manager.get_default_import_skill()
        skill_id = default_import["id"] if default_import else "import_eingang"
        task = qm.add_to_queue(skill_id, context={"filepath": filepath})
        qm.start_queue()
        logger.info("[Dashboard] Released file for reprocessing via Skill Queue: %s (Task %s)", filename, task.id)
        return jsonify({"status": "ok", "task_id": task.id})
    except (AttributeError, TypeError, RuntimeError) as e:
        return jsonify({"error": str(e)}), 500


@inbox_api_bp.route("/api/inbox/<path:filename>", methods=["DELETE"])
def api_inbox_delete(filename: str):
    if not DashboardState.config:
        return jsonify({"error": "Config not available"}), 503
    filepath, err = _resolve_and_guard(filename, DashboardState.config.watch_dir)
    if err is not None:
        return err[0], err[1]
    if not filepath:
        return jsonify({"error": "File not found"}), 404

    try:
        send_to_trash(filepath)
        _remove_meta_sidecar(filepath, use_trash=True)

        if DashboardState.processor:
            with DashboardState.processor.processing_lock:
                DashboardState.processor.processing_files.discard(filepath)

        logger.info("[Dashboard] Moved inbox file (incl. .meta) to trash: %s", filepath)
        return jsonify({"status": "ok"})
    except OSError as e:
        return jsonify({"error": str(e)}), 500


@inbox_api_bp.route("/api/inbox/<path:filename>/assign", methods=["POST"])
def api_inbox_assign(filename: str):
    if not DashboardState.config:
        return jsonify({"error": "Config not available"}), 503

    validated, err = validate_schema(AssignDocumentSchema, request.get_json())
    if not validated or err:
        return jsonify({"error": err}), 400
    data = validated.to_clean_dict()
    doc_type = str(data.get("document") or data.get("Document") or "Document").strip()
    err = _validate_required_api_fields(data, doc_type)
    if err:
        return jsonify({"error": err}), 400

    src_path = os.path.join(DashboardState.config.watch_dir, filename)
    if not os.path.isfile(src_path):
        return jsonify({"error": "File not found"}), 404
    if not _is_within_base(src_path, DashboardState.config.watch_dir):
        return jsonify({"error": "Access denied"}), 403

    folder_name = _render_target_folder(data, doc_type)
    target_dir = os.path.join(DashboardState.config.target_base_dir, folder_name)
    os.makedirs(target_dir, exist_ok=True)

    ext = os.path.splitext(src_path)[1]
    target_filename = _render_target_filename(data, doc_type, ext)
    target_filename, target_path = _deduplicate_filename(target_dir, target_filename)

    _remove_meta_sidecar(src_path)

    try:
        shutil.move(src_path, target_path)
        logger.info(
            "[Dashboard] Manual assignment: %s → %s/%s",
            filename,
            folder_name,
            target_filename,
        )
        return jsonify({"status": "ok", "folder": folder_name, "file": target_filename})
    except OSError as e:
        return jsonify({"error": str(e)}), 500


@inbox_api_bp.route("/api/inbox/<path:filename>/auto_assign", methods=["POST"])
def api_inbox_auto_assign(filename: str):
    if not DashboardState.config:
        return jsonify({"error": "Config not available"}), 503

    src_path = os.path.join(DashboardState.config.watch_dir, filename)
    if not os.path.isfile(src_path):
        return jsonify({"error": "File not found"}), 404
    if not _is_within_base(src_path, DashboardState.config.watch_dir):
        return jsonify({"error": "Access denied"}), 403

    delimiter = DashboardState.config.folder_delimiter if hasattr(DashboardState.config, "folder_delimiter") else "--"
    base_name = os.path.splitext(os.path.basename(filename))[0]
    parts = base_name.split(delimiter)

    data: dict = {}
    doc_type = "Document"

    if len(parts) >= 2:
        doc_type = parts[0].strip()
        data["Document"] = doc_type
        folder_structure = getattr(DashboardState.config, "folder_structure", []) or []
        field_order = [s.strip("{}") for s in folder_structure]
        for i, field_name in enumerate(field_order):
            if i + 1 < len(parts):
                data[field_name] = parts[i + 1].strip()
    else:
        # Fallback to .meta sidecar file metadata if available
        meta_path = src_path + ".meta"
        if os.path.isfile(meta_path):
            try:
                with open(meta_path, encoding="utf-8") as mf:
                    meta_data = json.load(mf)
                extracted_data = meta_data.get("extracted", {}) or {}
                if isinstance(extracted_data, dict):
                    data = extracted_data
                    if "Document" in data:
                        doc_type = str(data["Document"]).strip()
            except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError):
                logger.debug("Could not load sidecar metadata for %s", src_path)

        if not data or not (data.get("Nachname") or data.get("person") or data.get("Vorname") or data.get("Person")):
            return jsonify({"error": "Filename or metadata does not contain sufficient data for auto-assign"}), 400

    target_folder = _render_target_folder(data, doc_type)
    target_dir = os.path.join(DashboardState.config.target_base_dir, target_folder)
    os.makedirs(target_dir, exist_ok=True)

    ext = os.path.splitext(src_path)[1]
    target_filename = _render_target_filename(data, doc_type, ext)
    target_filename, target_path = _deduplicate_filename(target_dir, target_filename)

    _remove_meta_sidecar(src_path)

    try:
        shutil.move(src_path, target_path)
        logger.info("[Dashboard] Auto-assign: %s → %s", filename, target_filename)
        return jsonify({"status": "ok"})
    except OSError as e:
        return jsonify({"error": str(e)}), 500


@inbox_api_bp.route("/api/inbox/preview/<path:subpath>")
def api_inbox_preview(subpath: str):
    if not DashboardState.config:
        return jsonify({"error": "Config not available"}), 503
    full_path, err = _resolve_and_guard(subpath, DashboardState.config.watch_dir)
    if err:
        return err
    return _generate_pdf_thumbnail(full_path)  # type: ignore[arg-type]


@inbox_api_bp.route("/api/file/inbox/<path:subpath>")
def api_file_inbox(subpath: str):
    if not DashboardState.config:
        return jsonify({"error": "Config not available"}), 503
    full_path, err = _resolve_and_guard(subpath, DashboardState.config.watch_dir)
    if err:
        return err
    if full_path is None:
        return jsonify({"error": "File not found"}), 404
    ext = os.path.splitext(full_path)[1].lower()
    return send_file(full_path, mimetype=_MIME_MAP.get(ext, "application/octet-stream"))
