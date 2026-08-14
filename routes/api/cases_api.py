"""Cases & process folder API endpoints for DMS backend."""

import json
import logging
import os
import shutil
import time
import urllib.parse

from flask import Blueprint, jsonify, request, send_file

from routes.api.document_helpers import (
    _MIME_MAP,
    _deduplicate_filename,
    _generate_pdf_thumbnail,
    _get_doc_types_from_files,
    _is_within_base,
    _parse_folder_name,
    _remove_meta_sidecar,
    _render_target_filename,
    _render_target_folder,
    _resolve_and_guard,
    _validate_required_api_fields,
    safe_move_with_meta,
)
from routes.api.system_api import (
    FolderEditSchema,
    validate_schema,
)
from routes.state import DashboardState

cases_api_bp = Blueprint("api_cases", __name__)
logger = logging.getLogger(__name__)


@cases_api_bp.route("/api/cases")
def api_cases():
    if not DashboardState.config:
        return jsonify([])
    base_dir = DashboardState.config.target_base_dir
    if not os.path.exists(base_dir):
        return jsonify([])

    delimiter = getattr(DashboardState.config, "folder_delimiter", "--") or "--"

    result = []
    for item in sorted(os.listdir(base_dir)):
        item_path = os.path.join(base_dir, item)
        if os.path.isdir(item_path):
            if delimiter and delimiter not in item:
                continue
            parsed = _parse_folder_name(item)
            doc_types = _get_doc_types_from_files(item_path)
            files = [
                f
                for f in os.listdir(item_path)
                if os.path.isfile(os.path.join(item_path, f))
                and not f.lower().endswith(".jpg")
                and not f.lower().endswith(".meta")
            ]
            is_approved = os.path.exists(os.path.join(item_path, ".approved"))
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
                }
            )
    return jsonify(result)


@cases_api_bp.route("/api/cases/<path:folder_name>")
def api_cases_detail(folder_name: str):
    if not DashboardState.config:
        return jsonify({"error": "Config not available"}), 503
    folder_path = os.path.join(DashboardState.config.target_base_dir, folder_name)
    if not os.path.isdir(folder_path):
        return jsonify({"error": "Folder not found"}), 404

    files = []
    for f in sorted(os.listdir(folder_path)):
        fp = os.path.join(folder_path, f)
        if os.path.isfile(fp):
            if f.lower().endswith(".jpg") or f.lower().endswith(".meta"):
                continue

            stat = os.stat(fp)
            has_preview = f.lower().endswith(".pdf")
            preview_url = (
                f"/api/preview/Cases/{urllib.parse.quote(folder_name, safe='/')}/{urllib.parse.quote(f, safe='/')}"
                if has_preview
                else ""
            )

            files.append(
                {
                    "name": f,
                    "size": stat.st_size,
                    "modified": time.strftime(
                        "%Y-%m-%d %H:%M", time.localtime(stat.st_mtime)
                    ),
                    "has_preview": has_preview,
                    "preview_url": preview_url,
                    "is_preview": False,
                }
            )

    return jsonify({"folder": folder_name, "files": files})


@cases_api_bp.route("/api/cases/<path:folder_name>", methods=["PUT"])
def api_cases_edit(folder_name: str):
    if not DashboardState.config:
        return jsonify({"error": "Config not available"}), 503

    folder_path = os.path.join(DashboardState.config.target_base_dir, folder_name)
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
    if os.path.exists(new_path):
        return jsonify({"error": "Target folder already exists"}), 409

    try:
        os.rename(folder_path, new_path)
        logger.info(
            "[Dashboard] Renamed folder: %s -> %s", folder_name, new_folder_name
        )
        return jsonify({"status": "ok", "folder": new_folder_name})
    except OSError as e:
        return jsonify({"error": str(e)}), 500


@cases_api_bp.route("/api/file/meta/cases/<folder>/<filename>")
def api_file_meta_cases(folder: str, filename: str):
    if not DashboardState.config:
        return jsonify({"error": "Config not available"}), 503
    filepath = os.path.abspath(
        os.path.join(DashboardState.config.target_base_dir, folder, filename)
    )
    if not _is_within_base(filepath, DashboardState.config.target_base_dir):
        return jsonify({"error": "Access denied"}), 403
    meta_path = filepath + ".meta"
    if os.path.isfile(meta_path):
        try:
            with open(meta_path, encoding="utf-8") as mf:
                data = json.load(mf)
            return jsonify(data)
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
            ValueError,
            TypeError,
        ) as e:
            return jsonify({"error": str(e)}), 500
    return jsonify({"error": "No meta file found"}), 404


@cases_api_bp.route(
    "/api/cases/<path:folder_name>/<filename>/edit", methods=["POST"]
)
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

    src_path = os.path.join(
        DashboardState.config.target_base_dir, folder_name, filename
    )
    if not os.path.isfile(src_path):
        return jsonify({"error": "File not found"}), 404
    if not _is_within_base(src_path, DashboardState.config.target_base_dir):
        return jsonify({"error": "Access denied"}), 403

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
        src_dir = os.path.dirname(src_path)
        try:
            if not os.listdir(src_dir):
                os.rmdir(src_dir)
        except OSError:
            pass
        return jsonify(
            {"status": "ok", "folder": new_folder_name, "file": target_filename}
        )
    except OSError as e:
        return jsonify({"error": str(e)}), 500


@cases_api_bp.route("/api/cases/<path:folder_name>/<filename>", methods=["DELETE"])
def api_cases_delete_file(folder_name: str, filename: str):
    if not DashboardState.config:
        return jsonify({"error": "Config not available"}), 503
    filepath = os.path.join(
        DashboardState.config.target_base_dir, folder_name, filename
    )
    if not os.path.isfile(filepath):
        return jsonify({"error": "File not found"}), 404
    if not _is_within_base(filepath, DashboardState.config.target_base_dir):
        return jsonify({"error": "Access denied"}), 403

    try:
        os.remove(filepath)
        _remove_meta_sidecar(filepath)
        logger.info("[Dashboard] Deleted file: %s", filepath)
        return jsonify({"status": "ok"})
    except OSError as e:
        return jsonify({"error": str(e)}), 500


@cases_api_bp.route("/api/cases/<path:folder_name>", methods=["DELETE"])
def api_cases_delete_folder(folder_name: str):
    if not DashboardState.config:
        return jsonify({"error": "Config not available"}), 503
    folder_path = os.path.join(DashboardState.config.target_base_dir, folder_name)
    if not os.path.isdir(folder_path):
        return jsonify({"error": "Folder not found"}), 404
    if not _is_within_base(folder_path, DashboardState.config.target_base_dir):
        return jsonify({"error": "Access denied"}), 403

    try:
        shutil.rmtree(folder_path)
        logger.info("[Dashboard] Deleted process folder: %s", folder_path)
        return jsonify({"status": "ok"})
    except OSError as e:
        return jsonify({"error": str(e)}), 500


@cases_api_bp.route("/api/preview/<path:filepath>")
def api_preview(filepath: str):
    if not DashboardState.config:
        return jsonify({"error": "Config not available"}), 503

    full_path = os.path.join(DashboardState.config.target_base_dir, filepath)

    if not os.path.isfile(full_path):
        return jsonify({"error": "File not found"}), 404
    if not _is_within_base(full_path, DashboardState.config.target_base_dir):
        return jsonify({"error": "Access denied"}), 403
    return send_file(full_path, mimetype="image/jpeg")


@cases_api_bp.route("/api/file/cases/<path:subpath>")
def api_file_cases(subpath: str):
    if not DashboardState.config:
        return jsonify({"error": "Config not available"}), 503
    full_path, err = _resolve_and_guard(subpath, DashboardState.config.target_base_dir)
    if err or full_path is None:
        return err
    ext = os.path.splitext(full_path)[1].lower()
    return send_file(full_path, mimetype=_MIME_MAP.get(ext, "application/octet-stream"))


@cases_api_bp.route("/api/preview/Cases/<path:folder_name>/<path:filename>")
def api_cases_preview(folder_name: str, filename: str):
    if not DashboardState.config:
        return jsonify({"error": "Config not available"}), 503
    subpath = os.path.join(folder_name, filename)
    full_path, err = _resolve_and_guard(subpath, DashboardState.config.target_base_dir)
    if err:
        return err
    return _generate_pdf_thumbnail(full_path)  # type: ignore[arg-type]
