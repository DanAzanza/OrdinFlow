"""System & configuration API routes and schemas for the DMS backend."""

import logging
import os
from pathlib import Path
import sys
import threading
import time
from dataclasses import asdict
from typing import Any

from flask import Blueprint, Response, jsonify, request

from core.jobs import job_queue
from core.logging_service import compute_log_stats, get_empty_log_stats
from core.platform_utils import get_system_drives, pick_path_dialog
from core.utils import memory_log_handler, sanitize_safe_path
from routes.schemas import (
    ConfigUpdateSchema,
    validate_schema,
)
from routes.state import DashboardState

system_api_bp = Blueprint("api_system_and_config", __name__)
logger = logging.getLogger(__name__)

_get_empty_log_stats = get_empty_log_stats
_compute_log_stats = compute_log_stats
_get_system_drives = get_system_drives
_pick_path_dialog = pick_path_dialog

# Allowed configuration keys for GET and PUT /api/config
_CONFIG_SAFE_KEYS = [
    "watch_dir",
    "target_base_dir",
    "keep_inbox_files",
    "dashboard_port",
    "document_types",
    "folder_structure",
    "folder_delimiter",
    "match_folder_by",
    "llm_backend",
    "server_url",
    "server_api_key",
    "llm_model_path",
    "mmproj_path",
    "n_gpu_layers",
    "n_batch",
    "n_ubatch",
    "type_k",
    "type_v",
    "max_tokens",
    "n_threads",
    "render_dpi",
    "vision_api_timeout",
    "vision_api_retries",
    "crop_edge_threshold",
    "min_contour_area",
    "crop_padding",
    "white_border",
    "contrast_limit",
    "classify_dimension",
    "tier1_dimension",
    "tier2_dimension",
    "tier3_dimension",
    "vision_patch_size",
]


# ── System & Status Endpoints ──


@system_api_bp.route("/api/status")
def api_status():
    DashboardState.last_heartbeat = time.time()
    stats: dict[str, Any] = {}
    if DashboardState.processor:
        stats = DashboardState.processor.get_stats()
    else:
        stats = {"paused": False, "avg_duration": 0, "processed_count": 0}

    try:
        from core.skills.queue import get_skill_queue_manager

        qm = get_skill_queue_manager()
        stats["skill_queue"] = qm.get_queue_state()
    except Exception as e:
        logger.debug("[SystemAPI] Could not retrieve skill queue state: %s", e)
        stats["skill_queue"] = {"is_running": False, "items": [], "active_item": None}

    return jsonify(stats)


@system_api_bp.route("/api/jobs", methods=["GET"])
def api_jobs_list():
    return jsonify({"jobs": job_queue.list_jobs()})


@system_api_bp.route("/api/events", methods=["GET"])
def api_events():
    """Streams real-time log, status, and queue notifications via Server-Sent Events."""
    import json
    import queue
    from core.state import event_broadcaster

    q = event_broadcaster.subscribe()

    def stream():
        try:
            while not DashboardState.shutdown_event.is_set():
                try:
                    event = q.get(timeout=10.0)
                    yield f"data: {json.dumps(event)}\n\n"
                except queue.Empty:
                    # Keep-alive comment ping to flush socket and catch disconnected clients
                    yield ": ping\n\n"
        except (GeneratorExit, OSError):
            pass
        finally:
            event_broadcaster.unsubscribe(q)

    return Response(
        stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )





@system_api_bp.route("/api/router/pause", methods=["POST"])
def api_pause():
    if DashboardState.processor:
        DashboardState.processor.pause()
    from core.skills.queue import get_skill_queue_manager

    get_skill_queue_manager().pause_queue()
    return jsonify({"status": "paused"})


@system_api_bp.route("/api/router/resume", methods=["POST"])
def api_resume():
    if DashboardState.processor:
        DashboardState.processor.resume()
    from core.skills.queue import get_skill_queue_manager

    get_skill_queue_manager().resume_queue()
    return jsonify({"status": "active"})


@system_api_bp.route("/api/router/shutdown", methods=["POST"])
def api_shutdown():
    logger.info("[Dashboard] Shutdown requested...")

    def delayed_trigger():
        time.sleep(0.5)
        DashboardState.shutdown_event.set()

    threading.Thread(target=delayed_trigger, daemon=True).start()
    return jsonify({"status": "shutdown"})


@system_api_bp.route("/api/heartbeat", methods=["POST"])
def api_heartbeat():
    DashboardState.last_heartbeat = time.time()
    return jsonify({"status": "ok"})


# ── Log Endpoints ──


@system_api_bp.route("/api/log", methods=["GET"])
def api_get_logs():
    since_id = request.args.get("since_id", 0, type=int)
    limit = request.args.get("limit", 300, type=int)

    mem_logs, max_id = memory_log_handler.get_logs(since_id=since_id, limit=limit)
    return jsonify({"logs": mem_logs, "max_id": max_id})


@system_api_bp.route("/api/log/clear", methods=["POST"])
def api_clear_logs():
    import glob

    memory_log_handler.clear()

    # Safely truncate active FileHandlers without file-lock collisions
    active_dirs: set[str] = set()
    root = logging.getLogger()
    for handler in list(root.handlers):
        if isinstance(handler, logging.FileHandler):
            handler.acquire()
            try:
                if handler.baseFilename:
                    active_dirs.add(os.path.dirname(handler.baseFilename))
                if handler.stream and not getattr(handler.stream, "closed", False):
                    try:
                        handler.stream.seek(0)
                        handler.stream.truncate(0)
                        handler.flush()
                    except OSError:
                        pass
            finally:
                handler.release()

    active_dirs.add(os.getcwd())
    if sys.platform == "win32":
        appdata = os.environ.get("LOCALAPPDATA")
        if appdata:
            active_dirs.add(os.path.join(appdata, "OrdinFlow", "logs"))

    for d in active_dirs:
        if not os.path.exists(d):
            continue
        for prefix in ["main.log", "document_router.log", "service.log", "crash.log"]:
            for log_file in glob.glob(os.path.join(d, f"{prefix}*")):
                try:
                    with open(log_file, "w", encoding="utf-8"):
                        pass
                except OSError as e:
                    logger.debug("Could not clear log file %s: %s", log_file, e)

    return jsonify({"status": "cleared"})


@system_api_bp.route("/api/log/stats", methods=["GET"])
def api_get_log_stats():
    """Parses main.log and rotated backups chronologically to compute accurate server-side historical statistics."""
    lines: list[str] = []
    base_dir = "."
    if not os.path.exists("main.log") and not os.path.exists("document_router.log"):
        root = logging.getLogger()
        for handler in root.handlers:
            if isinstance(handler, logging.FileHandler) and handler.baseFilename:
                base_dir = os.path.dirname(handler.baseFilename)
                break

    # Read backups in chronological order (main.log.3 -> main.log.2 -> main.log.1 -> main.log)
    log_candidates: list[str] = []
    for i in range(3, 0, -1):
        backup_file = os.path.join(base_dir, f"main.log.{i}")
        if os.path.exists(backup_file):
            log_candidates.append(backup_file)

    current_file = os.path.join(base_dir, "main.log")
    if os.path.exists(current_file):
        log_candidates.append(current_file)
    elif os.path.exists(os.path.join(base_dir, "document_router.log")):
        log_candidates.append(os.path.join(base_dir, "document_router.log"))

    if not log_candidates:
        return jsonify(get_empty_log_stats())

    for log_path in log_candidates:
        try:
            with open(log_path, encoding="utf-8", errors="replace") as f:
                lines.extend(f.readlines())
        except OSError as e:
            logger.debug("[SystemApi] Could not read log file %s: %s", log_path, e)

    valid_types = (
        list(DashboardState.config.document_types.keys())
        if (DashboardState.config and DashboardState.config.document_types)
        else None
    )
    return jsonify(compute_log_stats(lines, valid_doc_types=valid_types))


# ── Configuration Endpoints ──


@system_api_bp.route("/api/config", methods=["GET"])
def api_system_config_get():
    if not DashboardState.config:
        return jsonify({"error": "Config not available"}), 503
    cfg = asdict(DashboardState.config)
    safe = {k: cfg.get(k) for k in _CONFIG_SAFE_KEYS if k in cfg}
    return jsonify(safe)


@system_api_bp.route("/api/config", methods=["PUT"])
def api_system_config():
    if not DashboardState.config:
        return jsonify({"error": "Config not available"}), 503

    validated, err = validate_schema(ConfigUpdateSchema, request.get_json())
    if not validated or err:
        return jsonify({"error": err}), 400
    data = validated.to_clean_dict()

    changed = []
    for k, v in data.items():
        if k in _CONFIG_SAFE_KEYS and hasattr(DashboardState.config, k):
            setattr(DashboardState.config, k, v)
            changed.append(k)

    if changed:
        try:
            if any(k in changed for k in ["watch_dir", "target_base_dir"]):
                DashboardState.config.setup_paths()

            DashboardState.config.save_to_yaml()
            if DashboardState.processor and hasattr(DashboardState.processor, "llm_extractor"):
                DashboardState.processor.llm_extractor.invalidate_cache()
            logger.info("[Dashboard] Configuration updated: %s", ", ".join(changed))
        except Exception as e:
            logger.error("[Dashboard] Error saving config: %s", e, exc_info=True)
            return jsonify({"error": "Failed to save configuration"}), 500

    return jsonify({"status": "ok", "changed": changed})


@system_api_bp.route("/api/system/fs_list", methods=["GET"])
def api_system_fs_list():
    """Lists filesystem items for the in-app file/folder browser."""
    raw_path = request.args.get("path", "").strip()
    picker_type = request.args.get("type", "folder").strip().lower()
    ext_filter = request.args.get("filter", "").strip().lower()

    base_dir = DashboardState.config.base_dir if DashboardState.config else os.getcwd()
    base_resolved = Path(base_dir).resolve()

    BLOCKED_SYSTEM_DIRS = {"windows", "$recycle.bin", "system volume information", "recovery"}
    target_dir_path = base_resolved
    if raw_path:
        is_safe, clean_path = sanitize_safe_path(raw_path)
        if is_safe and clean_path:
            p = Path(clean_path).resolve()
            path_parts = [part.lower() for part in p.parts]
            if not any(blocked in path_parts for blocked in BLOCKED_SYSTEM_DIRS):
                if p.is_file():
                    target_dir_path = p.parent
                elif p.is_dir():
                    target_dir_path = p

    target_dir = str(target_dir_path)

    # Breadcrumbs
    parts: list[tuple[str, str]] = []
    curr = target_dir
    while True:
        parent, name = os.path.split(curr)
        if not name:
            if curr:
                drive_label = curr.rstrip("\\/") if len(parts) > 0 else curr
                parts.append((drive_label, curr))
            break
        parts.append((name, curr))
        if parent == curr:
            break
        curr = parent

    breadcrumbs = [{"name": name or p, "path": p} for name, p in reversed(parts)]

    # Parent path
    parent_path = os.path.dirname(target_dir)
    if parent_path == target_dir:
        parent_path = None

    # Quick locations
    quick_locations = [{"name": "Project Root", "path": os.path.abspath(base_dir)}]
    if DashboardState.config:
        if DashboardState.config.watch_dir and os.path.exists(DashboardState.config.watch_dir):
            quick_locations.append({"name": "Inbox", "path": os.path.abspath(DashboardState.config.watch_dir)})
        if DashboardState.config.target_base_dir and os.path.exists(DashboardState.config.target_base_dir):
            quick_locations.append({"name": "Cases", "path": os.path.abspath(DashboardState.config.target_base_dir)})
    models_dir = os.path.join(base_dir, "models")
    if os.path.exists(models_dir):
        quick_locations.append({"name": "models", "path": os.path.abspath(models_dir)})

    # List entries
    entries: list[dict[str, Any]] = []
    try:
        target_path_obj = Path(target_dir)
        scanned = sorted(target_path_obj.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
        for e in scanned:
            if e.name.startswith("."):
                continue

            try:
                is_directory = e.is_dir()
                stat = e.stat()
                size_bytes = stat.st_size
                mtime_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(stat.st_mtime))
            except OSError:
                continue

            if is_directory:
                entries.append({
                    "name": e.name,
                    "path": str(e.resolve()),
                    "is_dir": True,
                    "type": "folder",
                    "size_str": "",
                    "modified_str": mtime_str,
                })
            elif picker_type == "file":
                if ext_filter and not e.name.lower().endswith(ext_filter):
                    continue
                sz_str = f"{size_bytes / 1024:.1f} KB" if size_bytes < 1048576 else f"{size_bytes / 1048576:.1f} MB"
                entries.append({
                    "name": e.name,
                    "path": str(e.resolve()),
                    "is_dir": False,
                    "type": "file",
                    "size_str": sz_str,
                    "modified_str": mtime_str,
                })
    except OSError as err:
        logger.warning("[!] Could not list directory %s: %s", target_dir, err)

    return jsonify({
        "status": "ok",
        "current_path": target_dir,
        "parent_path": parent_path,
        "breadcrumbs": breadcrumbs,
        "drives": _get_system_drives(),
        "quick_locations": quick_locations,
        "entries": entries,
    })


@system_api_bp.route("/api/system/browse", methods=["POST"])
def api_system_browse():
    """Opens a native system dialog to select a folder or file and returns the selected path."""
    data = request.get_json() or {}
    picker_type = str(data.get("picker_type", "folder")).lower()
    initial_dir = str(data.get("initial_dir", "")).strip()
    title = str(data.get("title", "")).strip()

    chosen = _pick_path_dialog(picker_type=picker_type, initial_dir=initial_dir, title=title)
    if chosen:
        return jsonify({"status": "ok", "path": chosen})
    return jsonify({"status": "cancelled", "path": None})
