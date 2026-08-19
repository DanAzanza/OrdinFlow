"""System & configuration API routes and schemas for the DMS backend."""

import logging
import os
import threading
import time
from dataclasses import asdict
from typing import Any

from flask import Blueprint, jsonify, request
from pydantic import BaseModel, ConfigDict, Field, ValidationError

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
    "flash_attn",
    "vision_api_timeout",
    "vision_api_retries",
    "crop_edge_threshold",
    "min_contour_area",
    "max_dimension",
    "crop_padding",
    "white_border",
    "contrast_limit",
    "classify_dimension",
    "tier1_dimension",
    "tier2_dimension",
    "tier3_dimension",
]


# ── Pydantic Validation Schemas ──


class FlexibleDocumentPayload(BaseModel):
    """Base schema for document metadata with dynamic extra fields."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    document: str | None = Field(
        default="Document",
        alias="Document",
        description="Type or category of the document",
    )

    def to_clean_dict(self) -> dict[str, Any]:
        """Returns all parsed fields (incl. dynamic fields) as a dictionary."""
        data = self.model_dump(by_alias=False)
        cleaned = {}
        for k, v in data.items():
            if isinstance(v, str):
                cleaned[k] = v.strip()
            else:
                cleaned[k] = v
        if "document" in cleaned:
            cleaned["Document"] = cleaned["document"]
        return cleaned


class AssignDocumentSchema(FlexibleDocumentPayload):
    """Schema for POST /api/inbox/<filename>/assign."""


class FolderEditSchema(BaseModel):
    """Schema for PUT /api/cases/<folder_name>."""

    model_config = ConfigDict(extra="allow")

    def to_clean_dict(self) -> dict[str, Any]:
        return {k: v.strip() if isinstance(v, str) else v for k, v in self.model_dump().items()}


class ConfigUpdateSchema(BaseModel):
    """Schema for PUT /api/config."""

    model_config = ConfigDict(extra="allow")

    folder_delimiter: str | None = None
    folder_structure: list[Any] | None = None
    document_types: dict[str, Any] | None = None


def validate_schema(schema_cls, data: dict[str, Any] | None) -> tuple[Any | None, str | None]:
    """Helper function to safely validate JSON payloads against a Pydantic schema."""
    if data is None:
        return None, "No input data received (JSON expected)."
    if not isinstance(data, dict):
        return None, "Invalid data format (dictionary expected)."
    try:
        instance = schema_cls.model_validate(data)
        return instance, None
    except ValidationError as e:
        errors = []
        for err in e.errors():
            loc = " -> ".join(str(item) for item in err.get("loc", []))
            msg = err.get("msg", "")
            errors.append(f"{loc}: {msg}")
        return None, "; ".join(errors)


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


@system_api_bp.route("/api/jobs/<job_id>", methods=["GET"])
def api_job_detail(job_id: str):
    job = job_queue.get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


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
        "successRate": "100.0",
        "totalProcessingTime": "0.0",
        "maxProcessingTime": "0.0",
        "avgTimePerFile": "0.0",
        "avgTimePerPage": "0.0",
        "totalPages": 0,
        "categoryCounts": {},
        "tier1Count": 0,
        "tier2Count": 0,
        "tier3Count": 0,
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
    total_processing_time = 0.0
    max_processing_time = 0.0
    total_pages = 0

    category_counts: dict[str, int] = {}
    tier1_count = 0
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
        elif "manual assignment required" in line or "manual review required" in line:
            if not match_incomplete:
                manual_review_files += 1

        match_abort = re.search(r"aborted due to error after ([\d\.]+) seconds", line, re.IGNORECASE)
        if match_abort:
            aborted_files += 1
            secs = float(match_abort.group(1))
            total_processing_time += secs
            if secs > max_processing_time:
                max_processing_time = secs

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

        # Tier 1 (Direct Consensus): Document finalized directly in Tier 1
        if (
            "validated with >= 2 measurements" in line
            or "Finalizing document" in line
            or "Early stop after Tier 1" in line
        ):
            tier1_count += 1

        # Tier 2 (High-Res Verification): Escalation for pending fields
        if "Starting Vision-LLM Tier 2 for pending fields" in line or "Starting Tier 2" in line:
            tier2_count += 1

        # Tier 3 (Tiebreaker Audit): Escalation for conflicting fields
        if (
            "Starting Vision-LLM Tier 3 Tiebreaker" in line
            or "Disagreement in field(s)" in line
            or "Starting Tier 3" in line
        ):
            tier3_count += 1

    total_files = completed_files + manual_review_files + aborted_files
    success_rate = f"{((completed_files / total_files) * 100):.1f}" if total_files > 0 else "100.0"
    avg_time_file = f"{(total_processing_time / total_files):.1f}" if total_files > 0 else "0.0"
    avg_time_page = f"{(total_processing_time / total_pages):.1f}" if total_pages > 0 else "0.0"

    return {
        "recordsCount": len(lines),
        "totalFiles": total_files,
        "completedFiles": completed_files,
        "manualReviewFiles": manual_review_files,
        "abortedFiles": aborted_files,
        "successRate": success_rate,
        "totalProcessingTime": f"{total_processing_time:.1f}",
        "maxProcessingTime": f"{max_processing_time:.1f}",
        "avgTimePerFile": avg_time_file,
        "avgTimePerPage": avg_time_page,
        "totalPages": total_pages,
        "categoryCounts": category_counts,
        "tier1Count": tier1_count,
        "tier2Count": tier2_count,
        "tier3Count": tier3_count,
        "earlyStopCount": tier1_count,
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
        logger.warning("[!] Native file/folder dialog failed: %s", e)

    return selected_path


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
