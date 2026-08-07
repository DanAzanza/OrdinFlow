"""Document API routes for the DMS backend (inbox, process folders, preview & file access)."""

import json
import logging
import os
import shutil
import threading
import time
import urllib.parse
from collections import OrderedDict
from typing import Any

from flask import Blueprint, Response, jsonify, request, send_file

try:
    import fitz
except ImportError:
    fitz = None

from core.routing import (
    parse_folder_name,
    render_filename,
    render_folder_name,
)
from core.utils import is_missing_value
from routes.api.system_api import (
    AssignDocumentSchema,
    FolderEditSchema,
    validate_schema,
)
from routes.state import DashboardState

documents_api_bp = Blueprint("api_documents", __name__)
logger = logging.getLogger(__name__)

_MIME_MAP = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}


# ── Helper functions for path, name & file handling ──


def _is_within_base(path: str, base_dir: str) -> bool:
    """Security check against directory traversal attacks."""
    return os.path.abspath(path).startswith(os.path.abspath(base_dir))


def _remove_meta_sidecar(filepath: str) -> None:
    """Deletes the .meta sidecar file if present (idempotent, suppresses errors)."""
    meta_path = filepath + ".meta"
    if os.path.exists(meta_path):
        try:
            os.remove(meta_path)
        except OSError:
            pass


def _get_config_folder_structure() -> list | None:
    return DashboardState.config.folder_structure if DashboardState.config else None


def _get_config_delimiter() -> str:
    return DashboardState.config.folder_delimiter if DashboardState.config else "--"


def _deduplicate_filename(target_dir: str, target_filename: str) -> tuple[str, str]:
    target_path = os.path.join(target_dir, target_filename)
    if not os.path.exists(target_path):
        return target_filename, target_path
    base_name, ext = os.path.splitext(target_filename)
    counter = 1
    while os.path.exists(target_path):
        target_filename = f"{base_name}_{counter}{ext}"
        target_path = os.path.join(target_dir, target_filename)
        counter += 1
    return target_filename, target_path


def _get_doc_routing_cfg(doc_type: str) -> dict:
    if not DashboardState.config:
        return {}
    doc_cfg = DashboardState.config.document_types.get(doc_type, {})
    if isinstance(doc_cfg, dict) and "routing" in doc_cfg:
        return doc_cfg.get("routing") or {}
    return {}


def _resolve_and_guard(subpath: str, base_dir: str) -> "tuple[str | None, Any]":
    """Resolves subpath against base_dir and applies standard security guards.

    Returns (full_path, None) on success, or (None, error_response_tuple) on failure.
    """
    full_path = os.path.join(base_dir, subpath)
    if not os.path.isfile(full_path):
        return None, (jsonify({"error": "File not found"}), 404)
    if not _is_within_base(full_path, base_dir):
        return None, (jsonify({"error": "Access denied"}), 403)
    return full_path, None


def _get_doc_optional_fields(doc_type: str) -> set:
    if not DashboardState.config:
        return set()
    doc_cfg = DashboardState.config.document_types.get(doc_type, {})
    if isinstance(doc_cfg, dict):
        return set(doc_cfg.get("validation", {}).get("optional_fields", []))
    return set()


def _render_target_folder(data: dict, doc_type: str = "") -> str:
    routing_cfg = _get_doc_routing_cfg(doc_type)
    optional_fields = _get_doc_optional_fields(doc_type)
    return render_folder_name(
        data,
        routing_cfg=routing_cfg,
        optional_fields=optional_fields,
        folder_structure=_get_config_folder_structure(),
        delimiter=_get_config_delimiter(),
    )


def _render_target_filename(data: dict, doc_type: str, ext: str) -> str:
    routing_cfg = _get_doc_routing_cfg(doc_type)
    return render_filename(
        data,
        routing_cfg=routing_cfg,
        ext=ext,
        fallbacks={"Document": doc_type},
    )


def _validate_required_api_fields(data: dict, doc_type: str) -> str | None:
    """Flexibly checks based on configuration whether required fields are filled out."""
    if not DashboardState.config:
        return None
    routing_cfg = _get_doc_routing_cfg(doc_type)
    mapping = routing_cfg.get("mapping", {})

    if mapping:
        lower_data = {k.lower(): v for k, v in data.items()}
        missing = []
        for val in mapping.values():
            raw_val = lower_data.get(val.lower(), data.get(val, ""))
            if is_missing_value(raw_val):
                missing.append(val)
        if len(missing) == len(mapping) and len(mapping) > 0:
            return f"Please fill out at least one of the configured fields: {', '.join(mapping.values())}"
    return None


def _parse_folder_name(folder_name: str) -> dict:
    """Parses a folder name based on configured delimiter and folder structure."""
    return parse_folder_name(
        folder_name,
        folder_structure=_get_config_folder_structure(),
        delimiter=_get_config_delimiter(),
    )


def _get_doc_types_from_files(folder_path: str) -> list:
    """Determines existing document types from filenames."""
    doc_types = set()
    if not os.path.isdir(folder_path):
        return []
    delimiter = _get_config_delimiter()
    for f in os.listdir(folder_path):
        if os.path.isfile(os.path.join(folder_path, f)):
            parts = f.split(delimiter)
            if len(parts) >= 1:
                doc_type = parts[0]
                if not f.lower().endswith(".jpg") and not f.lower().endswith(".meta"):
                    for dt in doc_type.split("+"):
                        doc_types.add(dt.strip())
    return sorted(doc_types)


# ── LRU Thumbnail Cache ──


class ThumbnailCache:
    """Thread-safe LRU cache with configurable maximum size."""

    def __init__(self, maxsize: int = 200):
        self._cache: OrderedDict = OrderedDict()
        self._lock = threading.Lock()
        self._maxsize = maxsize

    def get(self, key) -> tuple | None:
        with self._lock:
            if key not in self._cache:
                return None
            self._cache.move_to_end(key)
            return self._cache[key]

    def set(self, key, value):
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = value
            if len(self._cache) > self._maxsize:
                self._cache.popitem(last=False)


_thumbnail_cache: ThumbnailCache = ThumbnailCache(maxsize=200)


def _generate_pdf_thumbnail(full_path: str):
    mtime = os.path.getmtime(full_path)
    cached = _thumbnail_cache.get(full_path)
    if cached and cached[0] == mtime:
        return Response(cached[1], mimetype="image/jpeg")

    if not fitz:
        return jsonify({"error": "PyMuPDF (fitz) not available"}), 500
    try:
        doc = fitz.open(full_path)
        try:
            page = doc[0]
            zoom = 300 / page.rect.width
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat)
            img_bytes = pix.tobytes("jpeg")
        finally:
            doc.close()

        _thumbnail_cache.set(full_path, (mtime, img_bytes))
        return Response(img_bytes, mimetype="image/jpeg")
    except (OSError, RuntimeError, ValueError, TypeError) as e:
        return jsonify({"error": f"Preview error: {e}"}), 500


# ── INBOX API Endpoints ──


@documents_api_bp.route("/api/inbox")
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

                meta_path = fp + ".meta"
                reason = ""
                extracted = {}
                is_review = os.path.isfile(meta_path)
                if is_review:
                    try:
                        with open(meta_path, encoding="utf-8") as mf:
                            meta_data = json.load(mf)
                        reason = meta_data.get("grund", meta_data.get("reason", ""))
                        extracted = meta_data.get("extracted", {})
                    except (
                        OSError,
                        UnicodeError,
                        json.JSONDecodeError,
                        ValueError,
                        TypeError,
                    ):
                        logger.debug("Could not load inbox metadata from %s", meta_path)

                result.append(
                    {
                        "name": f,
                        "path": rel_path,
                        "grund": reason,
                        "extracted": extracted,
                        "is_pruefen": is_review,
                        "size": stat.st_size,
                        "modified": time.strftime(
                            "%Y-%m-%d %H:%M", time.localtime(stat.st_mtime)
                        ),
                        "preview_url": f"/api/inbox/preview/{urllib.parse.quote(rel_path, safe='/')}"
                        if f.lower().endswith(".pdf")
                        else "",
                        "file_url": f"/api/file/inbox/{rel_path}",
                    }
                )
    return jsonify(result)


@documents_api_bp.route("/api/file/meta/inbox/<path:filename>")
def api_file_meta_inbox(filename: str):
    if not DashboardState.config:
        return jsonify({"error": "Config not available"}), 503
    filepath = os.path.abspath(os.path.join(DashboardState.config.watch_dir, filename))
    if not _is_within_base(filepath, DashboardState.config.watch_dir):
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


@documents_api_bp.route("/api/file/meta/cases/<folder>/<filename>")
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


@documents_api_bp.route("/api/inbox/<path:filename>/retry", methods=["POST"])
def api_inbox_retry(filename: str):
    if not DashboardState.config or not DashboardState.file_queue:
        return jsonify({"error": "Not available"}), 503

    filepath = os.path.abspath(os.path.join(DashboardState.config.watch_dir, filename))
    if not _is_within_base(filepath, DashboardState.config.watch_dir):
        return jsonify({"error": "Access denied"}), 403

    if not os.path.isfile(filepath):
        return jsonify({"error": "File not found"}), 404

    _remove_meta_sidecar(filepath)
    if DashboardState.processor:
        with DashboardState.processor.processing_lock:
            DashboardState.processor.processing_files.discard(filepath)
    logger.info("[Dashboard] Deleted .meta sidecar: %s", filename)

    try:
        DashboardState.file_queue.put(filepath)
        logger.info("[Dashboard] Released file for reprocessing: %s", filename)
        return jsonify({"status": "ok"})
    except (AttributeError, TypeError, RuntimeError) as e:
        return jsonify({"error": str(e)}), 500


@documents_api_bp.route("/api/inbox/<path:filename>", methods=["DELETE"])
def api_inbox_delete(filename: str):
    if not DashboardState.config:
        return jsonify({"error": "Config not available"}), 503
    filepath = os.path.join(DashboardState.config.watch_dir, filename)
    if not os.path.isfile(filepath):
        return jsonify({"error": "File not found"}), 404
    if not _is_within_base(filepath, DashboardState.config.watch_dir):
        return jsonify({"error": "Access denied"}), 403

    try:
        os.remove(filepath)
        _remove_meta_sidecar(filepath)

        if DashboardState.processor:
            with DashboardState.processor.processing_lock:
                DashboardState.processor.processing_files.discard(filepath)

        logger.info("[Dashboard] Deleted inbox file (incl. .meta): %s", filepath)
        return jsonify({"status": "ok"})
    except OSError as e:
        return jsonify({"error": str(e)}), 500


@documents_api_bp.route("/api/inbox/<path:filename>/assign", methods=["POST"])
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


@documents_api_bp.route("/api/inbox/<path:filename>/auto_assign", methods=["POST"])
def api_inbox_auto_assign(filename: str):
    if not DashboardState.config:
        return jsonify({"error": "Config not available"}), 503

    src_path = os.path.join(DashboardState.config.watch_dir, filename)
    if not os.path.isfile(src_path):
        return jsonify({"error": "File not found"}), 404
    if not _is_within_base(src_path, DashboardState.config.watch_dir):
        return jsonify({"error": "Access denied"}), 403

    delimiter = (
        DashboardState.config.folder_delimiter
        if hasattr(DashboardState.config, "folder_delimiter")
        else "--"
    )
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

        if not data or not (
            data.get("Nachname") or data.get("person") or data.get("Vorname")
        ):
            return jsonify(
                {
                    "error": "Filename or metadata does not contain sufficient data for auto-assign"
                }
            ), 400

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


# ── CASES API Endpoints ──


@documents_api_bp.route("/api/cases")
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


@documents_api_bp.route("/api/cases/<path:folder_name>")
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


@documents_api_bp.route("/api/cases/<path:folder_name>", methods=["PUT"])
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
    from core.skills_engine import SkillManager

    for skill in SkillManager().list_skills():
        if skill.get("type") == "import" and skill.get("enabled", True):
            return bool(skill.get("split_multi_documents", True))
    return True


@documents_api_bp.route("/api/split_inspector/submit", methods=["POST"])
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
    split_allowed_by_skill = _is_split_enabled_for_import_skill()

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
    is_multi_split = split_allowed_by_skill and (
        len(documents_input) > 1 or (is_pdf and pdf_doc and total_pages > 1)
    )

    try:
        for doc_sec in documents_input:
            data = dict(doc_sec)
            doc_type = str(
                data.get("dokument") or data.get("Dokument") or "Dokument"
            ).strip()
            data["Dokument"] = doc_type

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

            if (
                is_pdf
                and fitz is not None
                and pdf_doc
                and is_multi_split
                and pages_to_extract
            ):
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
        if pdf_doc:
            pdf_doc.close()
        return jsonify({"error": str(e)}), 500


@documents_api_bp.route(
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
        shutil.move(src_path, target_path)
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


@documents_api_bp.route("/api/cases/<path:folder_name>/<filename>", methods=["DELETE"])
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


@documents_api_bp.route("/api/cases/<path:folder_name>", methods=["DELETE"])
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


# ── PREVIEW & FILE ACCESS API Endpoints ──


@documents_api_bp.route("/api/preview/<path:filepath>")
def api_preview(filepath: str):
    if not DashboardState.config:
        return jsonify({"error": "Config not available"}), 503

    full_path = os.path.join(DashboardState.config.target_base_dir, filepath)

    if not os.path.isfile(full_path):
        return jsonify({"error": "File not found"}), 404
    if not _is_within_base(full_path, DashboardState.config.target_base_dir):
        return jsonify({"error": "Access denied"}), 403
    return send_file(full_path, mimetype="image/jpeg")


@documents_api_bp.route("/api/file/cases/<path:subpath>")
def api_file_cases(subpath: str):
    if not DashboardState.config:
        return jsonify({"error": "Config not available"}), 503
    full_path, err = _resolve_and_guard(subpath, DashboardState.config.target_base_dir)
    if err or full_path is None:
        return err
    ext = os.path.splitext(full_path)[1].lower()
    return send_file(full_path, mimetype=_MIME_MAP.get(ext, "application/octet-stream"))


@documents_api_bp.route("/api/file/inbox/<path:subpath>")
def api_file_inbox(subpath: str):
    if not DashboardState.config:
        return jsonify({"error": "Config not available"}), 503
    full_path, err = _resolve_and_guard(subpath, DashboardState.config.watch_dir)
    if err or full_path is None:
        return err
    ext = os.path.splitext(full_path)[1].lower()
    return send_file(full_path, mimetype=_MIME_MAP.get(ext, "application/octet-stream"))


@documents_api_bp.route("/api/inbox/preview/<path:subpath>")
def api_inbox_preview(subpath: str):
    if not DashboardState.config:
        return jsonify({"error": "Config not available"}), 503
    full_path, err = _resolve_and_guard(subpath, DashboardState.config.watch_dir)
    if err:
        return err
    return _generate_pdf_thumbnail(full_path)  # type: ignore[arg-type]


@documents_api_bp.route("/api/preview/Cases/<path:folder_name>/<path:filename>")
def api_cases_preview(folder_name: str, filename: str):
    if not DashboardState.config:
        return jsonify({"error": "Config not available"}), 503
    subpath = os.path.join(folder_name, filename)
    full_path, err = _resolve_and_guard(subpath, DashboardState.config.target_base_dir)
    if err:
        return err
    return _generate_pdf_thumbnail(full_path)  # type: ignore[arg-type]
