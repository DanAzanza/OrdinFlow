import json
import logging
import os
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any

from flask import Response, jsonify, request

try:
    import fitz
except ImportError:
    fitz = None

from core.routing import (
    parse_folder_name,
    render_filename,
    render_folder_name,
)
from core.utils import (
    deduplicate_path,
    is_missing_value,
    remove_source_with_meta,
    safe_move,
    trash_source_with_meta,
)
from routes.state import DashboardState

logger = logging.getLogger(__name__)

_MIME_MAP = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}


def _is_within_base(path: str, base_dir: str) -> bool:
    """Security check against directory traversal attacks."""
    try:
        p = Path(path).resolve()
        b = Path(base_dir).resolve()
        return p.is_relative_to(b)
    except (ValueError, TypeError, RuntimeError):
        return False


def load_meta_sidecar(filepath: str) -> dict[str, Any] | None:
    """Reads and parses the accompanying .meta JSON sidecar file if present."""
    meta_path = filepath if filepath.endswith(".meta") else filepath + ".meta"
    if os.path.isfile(meta_path):
        try:
            with open(meta_path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError) as e:
            logger.debug("[DocumentHelpers] Could not load sidecar %s: %s", meta_path, e)
    return None


def _remove_meta_sidecar(filepath: str, use_trash: bool = True) -> None:
    """Deletes or trashes the .meta sidecar file if present."""
    meta_path = filepath if filepath.endswith(".meta") else filepath + ".meta"
    if os.path.exists(meta_path):
        if use_trash:
            trash_source_with_meta(meta_path)
        else:
            remove_source_with_meta(meta_path)


def safe_move_with_meta(src_path: str, dst_path: str) -> None:
    """Moves a file and its associated .meta sidecar file atomically if present with Windows lock retry."""
    safe_move(src_path, dst_path)
    src_meta = src_path + ".meta"
    dst_meta = dst_path + ".meta"
    if os.path.isfile(src_meta):
        safe_move(src_meta, dst_meta)


def _get_config_folder_structure() -> list | None:
    return DashboardState.config.folder_structure if DashboardState.config else None


def _get_config_delimiter() -> str:
    return DashboardState.config.folder_delimiter if DashboardState.config else "--"


def _deduplicate_filename(target_dir: str, target_filename: str) -> tuple[str, str]:
    target_path = deduplicate_path(os.path.join(target_dir, target_filename))
    return os.path.basename(target_path), target_path


def _get_doc_routing_cfg(doc_type: str) -> dict:
    if not DashboardState.config:
        return {}
    doc_cfg = DashboardState.config.document_types.get(doc_type, {})
    if isinstance(doc_cfg, dict) and "routing" in doc_cfg:
        return doc_cfg.get("routing") or {}
    return {}


def _resolve_and_guard(subpath: str, base_dir: str) -> tuple[str | None, tuple[Any, int] | None]:
    """Resolves subpath against base_dir and applies security and existence guards."""
    full_path = os.path.abspath(os.path.join(base_dir, subpath))
    if not _is_within_base(full_path, base_dir):
        return None, (jsonify({"error": "Access denied"}), 403)
    if not os.path.isfile(full_path):
        return None, (jsonify({"error": "File not found"}), 404)
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


# ── LRU Thumbnail Cache ──


class ThumbnailCache:
    """Thread-safe LRU cache with configurable maximum size."""

    def __init__(self, maxsize: int = 3000):
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


_thumbnail_cache: ThumbnailCache = ThumbnailCache(maxsize=3000)


def _generate_pdf_thumbnail(full_path: str):
    try:
        mtime = os.path.getmtime(full_path)
        size = os.path.getsize(full_path)
    except OSError as e:
        return jsonify({"error": f"File error: {e}"}), 404

    etag = f'"{int(mtime)}-{size}"'
    if request.headers.get("If-None-Match") == etag:
        res = Response(status=304)
        res.headers["ETag"] = etag
        res.headers["Cache-Control"] = "public, max-age=86400"
        return res

    cached = _thumbnail_cache.get(full_path)
    if cached and cached[0] == mtime:
        res = Response(cached[1], mimetype="image/jpeg")
        res.headers["ETag"] = etag
        res.headers["Cache-Control"] = "public, max-age=86400"
        return res

    if not fitz:
        return jsonify({"error": "PyMuPDF (fitz) not available"}), 500
    try:
        with fitz.open(full_path) as doc:
            page = doc[0]
            zoom = 280 / max(page.rect.width, 1.0)
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img_bytes = pix.tobytes("jpeg", jpg_quality=75)
            del pix

        _thumbnail_cache.set(full_path, (mtime, img_bytes))
        res = Response(img_bytes, mimetype="image/jpeg")
        res.headers["ETag"] = etag
        res.headers["Cache-Control"] = "public, max-age=86400"
        return res
    except (OSError, RuntimeError, ValueError, TypeError) as e:
        return jsonify({"error": f"Preview error: {e}"}), 500
