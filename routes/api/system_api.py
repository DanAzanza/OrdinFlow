"""System & configuration API routes and schemas for the DMS backend."""

import logging
import os
import threading
import time
from dataclasses import asdict
from typing import Any

from flask import Blueprint, jsonify, request

from core.jobs import job_queue
from core.utils import memory_log_handler
from routes.state import DashboardState

system_api_bp = Blueprint("api_system_and_config", __name__)
logger = logging.getLogger(__name__)

# Allowed configuration keys for GET and PUT /api/config
_CONFIG_SAFE_KEYS = [
    "watch_dir",
    "target_base_dir",
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
]


from routes.schemas import (
    ConfigUpdateSchema,
    validate_schema,
)


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
    logging.info("[Dashboard] Shutdown requested...")

    def delayed_trigger():
        time.sleep(1)
        DashboardState.shutdown_event.set()
        time.sleep(5)
        os._exit(0)

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
    memory_log_handler.clear()

    # Safely truncate active FileHandlers without file-lock collisions
    root = logging.getLogger()
    for handler in list(root.handlers):
        if isinstance(handler, logging.FileHandler):
            handler.acquire()
            try:
                if handler.stream and not getattr(handler.stream, "closed", False):
                    try:
                        handler.stream.seek(0)
                        handler.stream.truncate(0)
                        handler.flush()
                    except OSError:
                        pass
            finally:
                handler.release()

    for log_name in ["main.log", "document_router.log", "crash.log"]:
        if os.path.exists(log_name):
            try:
                with open(log_name, "w", encoding="utf-8"):
                    pass
            except OSError:
                pass

    return jsonify({"status": "cleared"})


def _get_empty_log_stats() -> dict[str, Any]:
    return {
        "recordsCount": 0,
        "totalFiles": 0,
        "completedFiles": 0,
        "manualReviewFiles": 0,
        "abortedFiles": 0,
        "emptyFiles": 0,
        "splitBatches": 0,
        "partialDocsSaved": 0,
        "directDocsMoved": 0,
        "totalArchivedDocs": 0,
        "successRate": "100.0",
        "totalProcessingTime": "0.0",
        "maxProcessingTime": "0.0",
        "avgTimePerFile": "0.0",
        "avgTimePerPage": "0.0",
        "totalPages": 0,
        "categoryCounts": {},
        "tier1Count": 0,
        "tier1DirectConsensus": 0,
        "tier2Count": 0,
        "tier2Resolved": 0,
        "tier3Count": 0,
        "tier3Resolved": 0,
        "earlyStopCount": 0,
        "infoCount": 0,
        "warnCount": 0,
        "errorCount": 0,
    }


def _compute_log_stats(lines: list[str]) -> dict[str, Any]:
    import re

    completed_files = 0
    manual_review_files = 0
    aborted_files = 0
    empty_files = 0

    total_processing_time = 0.0
    max_processing_time = 0.0
    total_pages = 0

    split_batches = 0
    partial_docs_saved = 0
    direct_docs_moved = 0

    category_counts: dict[str, int] = {}
    tier1_count = 0
    tier1_direct_consensus = 0
    tier2_count = 0
    tier3_count = 0

    info_count = 0
    warn_count = 0
    error_count = 0

    for line in lines:
        if " [INFO] " in line:
            info_count += 1
        elif " [WARNING] " in line or " [WARN] " in line:
            warn_count += 1
        elif " [ERROR] " in line or " [CRITICAL] " in line:
            error_count += 1

        match_completed = re.search(r"completed successfully after ([\d\.]+) seconds", line, re.IGNORECASE)
        if match_completed:
            completed_files += 1
            secs = float(match_completed.group(1))
            total_processing_time += secs
            if secs > max_processing_time:
                max_processing_time = secs

        match_incomplete = re.search(r"incomplete \(([\d\.]+)s\)", line, re.IGNORECASE)
        if match_incomplete:
            manual_review_files += 1
            secs = float(match_incomplete.group(1))
            total_processing_time += secs
            if secs > max_processing_time:
                max_processing_time = secs

        match_abort = re.search(r"aborted due to error after ([\d\.]+) seconds", line, re.IGNORECASE)
        if match_abort:
            aborted_files += 1
            secs = float(match_abort.group(1))
            total_processing_time += secs
            if secs > max_processing_time:
                max_processing_time = secs

        if "consists only of empty pages and will be deleted" in line:
            empty_files += 1

        # Document routing & splitting counters
        if "Splitting batch PDF" in line:
            split_batches += 1
        if "saved successfully" in line and ("Partial PDF" in line or "partial PDF" in line):
            partial_docs_saved += 1
        if "Moving file" in line:
            direct_docs_moved += 1

        match_class = re.search(r"Page \d+ classification:\s*(.+)", line)
        if match_class:
            total_pages += 1
            cat = match_class.group(1).strip()
            if "\ufffd" in cat and DashboardState.config and DashboardState.config.document_types:
                for valid_type in DashboardState.config.document_types:
                    if len(valid_type) == len(cat) and all(
                        c1 == c2 for c1, c2 in zip(valid_type, cat) if c2 != "\ufffd"
                    ):
                        cat = valid_type
                        break
            category_counts[cat] = category_counts.get(cat, 0) + 1

        # Tier 1 Invocations: Base Vision-LLM or Spatial OCR pass started
        if "Starting Vision-LLM Tier 1" in line:
            tier1_count += 1

        # Tier 1 Direct Consensus (Early Stop / Resolved without Tier 2)
        if (
            "validated with >= 2 measurements" in line
            or "Finalizing document" in line
            or "Early stop after Tier 1" in line
        ):
            tier1_direct_consensus += 1

        # Tier 2 Invocations: Escalation for pending / unconfident fields
        if "Starting Vision-LLM Tier 2 for pending fields" in line or "Starting Tier 2" in line:
            tier2_count += 1

        # Tier 3 Invocations: Tiebreaker escalation on conflict fields
        if (
            "Starting Vision-LLM Tier 3 Tiebreaker" in line
            or "Disagreement in field(s)" in line
            or "Starting Tier 3" in line
        ):
            tier3_count += 1

    total_files = completed_files + manual_review_files + aborted_files + empty_files
    total_archived_docs = partial_docs_saved + direct_docs_moved

    tier2_resolved = max(0, tier2_count - tier3_count)
    tier3_resolved = tier3_count

    success_rate = f"{((completed_files / total_files) * 100):.1f}" if total_files > 0 else "100.0"
    avg_time_file = f"{(total_processing_time / total_files):.1f}" if total_files > 0 else "0.0"
    avg_time_page = f"{(total_processing_time / total_pages):.1f}" if total_pages > 0 else "0.0"

    return {
        "recordsCount": len(lines),
        "totalFiles": total_files,
        "completedFiles": completed_files,
        "manualReviewFiles": manual_review_files,
        "abortedFiles": aborted_files,
        "emptyFiles": empty_files,
        "splitBatches": split_batches,
        "partialDocsSaved": partial_docs_saved,
        "directDocsMoved": direct_docs_moved,
        "totalArchivedDocs": total_archived_docs,
        "successRate": success_rate,
        "totalProcessingTime": f"{total_processing_time:.1f}",
        "maxProcessingTime": f"{max_processing_time:.1f}",
        "avgTimePerFile": avg_time_file,
        "avgTimePerPage": avg_time_page,
        "totalPages": total_pages,
        "categoryCounts": category_counts,
        "tier1Count": tier1_count,
        "tier1DirectConsensus": tier1_direct_consensus,
        "tier2Count": tier2_count,
        "tier2Resolved": tier2_resolved,
        "tier3Count": tier3_count,
        "tier3Resolved": tier3_resolved,
        "earlyStopCount": tier1_direct_consensus,
        "infoCount": info_count,
        "warnCount": warn_count,
        "errorCount": error_count,
    }


@system_api_bp.route("/api/log/stats", methods=["GET"])
def api_get_log_stats():
    """Parses main.log to compute accurate server-side historical statistics."""
    log_path = "main.log" if os.path.exists("main.log") else "document_router.log"
    if not os.path.exists(log_path):
        return jsonify(_get_empty_log_stats())

    try:
        with open(log_path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError as e:
        logger.debug("[SystemApi] Could not read log file %s: %s", log_path, e)
        lines = []

    return jsonify(_compute_log_stats(lines))


# ── Configuration Endpoints ──


@system_api_bp.route("/api/config", methods=["GET"])
def api_config_get():
    if not DashboardState.config:
        return jsonify({"error": "Config not available"}), 503
    cfg = asdict(DashboardState.config)
    return jsonify({k: cfg[k] for k in _CONFIG_SAFE_KEYS if k in cfg})


@system_api_bp.route("/api/config", methods=["PUT"])
def api_config_put():
    if not DashboardState.config:
        return jsonify({"error": "Config not available"}), 503

    validated, err = validate_schema(ConfigUpdateSchema, request.get_json())
    if not validated or err:
        return jsonify({"error": err}), 400
    data = validated.model_dump(exclude_unset=True)

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
            logging.info(f"[Dashboard] Configuration updated: {', '.join(changed)}")
        except Exception as e:
            logging.error(f"[Dashboard] Error saving config: {e}")
            return jsonify({"error": str(e)}), 500

    return jsonify({"status": "ok", "changed": changed})


def _get_system_drives() -> list[str]:
    """Returns available drive letters on Windows or root directory on POSIX."""
    drives = []
    if os.name == "nt":
        import string

        for letter in string.ascii_uppercase:
            drive = f"{letter}:\\"
            if os.path.exists(drive):
                drives.append(drive)
    else:
        drives.append("/")
    return drives


def _pick_path_dialog(picker_type: str = "folder", initial_dir: str = "", title: str = "") -> str | None:
    """Opens a native GUI picker dialog to choose a folder or file."""
    selected_path = None
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        init_dir = initial_dir if (initial_dir and os.path.exists(initial_dir)) else os.getcwd()

        if picker_type == "file":
            filetypes = (
                [("GGUF Models (*.gguf)", "*.gguf"), ("All Files (*.*)", "*.*")]
                if any(x in title.lower() for x in ("model", "gguf", "projector", "mmproj"))
                else [("All Files (*.*)", "*.*")]
            )
            selected = filedialog.askopenfilename(
                initialdir=init_dir,
                title=title or "Datei auswählen",
                filetypes=filetypes,
            )
        else:
            selected = filedialog.askdirectory(
                initialdir=init_dir,
                title=title or "Ordner auswählen",
            )
        root.destroy()
        if selected:
            selected_path = os.path.normpath(selected)
    except Exception as e:
        logger.debug("[!] Native tkinter dialog failed: %s", e)

    # PowerShell fallback on Windows if tkinter didn't produce a path
    if not selected_path and os.name == "nt":
        try:
            import base64
            import subprocess

            init_dir = initial_dir if (initial_dir and os.path.exists(initial_dir)) else os.getcwd()
            fallback_title = "Datei auswählen" if picker_type == "file" else "Ordner auswählen"
            diag_title = title if title else fallback_title

            clean_dir = os.path.abspath(init_dir).replace("'", "''")
            clean_title = diag_title.replace("'", "''").replace("\r", "").replace("\n", " ")

            if picker_type == "file":
                ps_script = (
                    "Add-Type -AssemblyName System.Windows.Forms; "
                    "$f = New-Object System.Windows.Forms.OpenFileDialog; "
                    f"$f.InitialDirectory = '{clean_dir}'; "
                    f"$f.Title = '{clean_title}'; "
                    "if ($f.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { [Console]::Out.Write($f.FileName) }"
                )
            else:
                ps_script = (
                    "Add-Type -AssemblyName System.Windows.Forms; "
                    "$f = New-Object System.Windows.Forms.FolderBrowserDialog; "
                    f"$f.SelectedPath = '{clean_dir}'; "
                    f"$f.Description = '{clean_title}'; "
                    "if ($f.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { [Console]::Out.Write($f.SelectedPath) }"
                )

            encoded_cmd = base64.b64encode(ps_script.encode("utf-16le")).decode("ascii")
            res = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded_cmd],
                capture_output=True,
                text=True,
                timeout=30,
            )
            out = (res.stdout or "").strip()
            if out and os.path.exists(out):
                selected_path = os.path.normpath(out)
        except Exception as e:
            logger.debug("[!] PowerShell picker fallback failed: %s", e)

    return selected_path


@system_api_bp.route("/api/system/fs_list", methods=["GET"])
def api_system_fs_list():
    """Lists filesystem items for the in-app file/folder browser."""
    raw_path = request.args.get("path", "").strip()
    picker_type = request.args.get("type", "folder").strip().lower()
    ext_filter = request.args.get("filter", "").strip().lower()

    base_dir = DashboardState.config.base_dir if DashboardState.config else os.getcwd()

    if not raw_path:
        target_dir = os.path.abspath(base_dir)
    elif os.path.isfile(raw_path):
        target_dir = os.path.dirname(os.path.abspath(raw_path))
    else:
        target_dir = os.path.abspath(raw_path)

    if not os.path.exists(target_dir) or not os.path.isdir(target_dir):
        target_dir = os.path.abspath(base_dir)

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
        scanned = sorted(os.scandir(target_dir), key=lambda e: (not e.is_dir(), e.name.lower()))
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
                    "path": os.path.abspath(e.path),
                    "is_dir": True,
                    "size_str": "",
                    "modified_str": mtime_str,
                })
            elif picker_type == "file":
                if ext_filter and not e.name.lower().endswith(ext_filter):
                    continue
                # Format size
                if size_bytes >= 1024 * 1024 * 1024:
                    sz_str = f"{size_bytes / (1024**3):.2f} GB"
                elif size_bytes >= 1024 * 1024:
                    sz_str = f"{size_bytes / (1024**2):.1f} MB"
                elif size_bytes >= 1024:
                    sz_str = f"{size_bytes / 1024:.0f} KB"
                else:
                    sz_str = f"{size_bytes} B"

                entries.append({
                    "name": e.name,
                    "path": os.path.abspath(e.path),
                    "is_dir": False,
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
