"""Skill Queue and batch case execution API endpoints."""

from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

from core.skills import (
    SkillManager,
    SkillQueueManager,
    get_skill_manager,
    get_skill_queue_manager,
)
from core.skills.engines.export_engine import ExportEngine
from routes.state import DashboardState

skills_queue_api_bp = Blueprint("api_skills_queue", __name__)
logger = logging.getLogger(__name__)


def _get_skill_manager() -> SkillManager:
    return get_skill_manager()


def _get_configured_queue_manager() -> SkillQueueManager:
    return get_skill_queue_manager(_get_skill_manager())


@skills_queue_api_bp.route("/api/skills/queue", methods=["GET"])
def get_skill_queue():
    """Returns current state of the skill execution queue."""
    qm = _get_configured_queue_manager()
    return jsonify(qm.get_queue_state())


@skills_queue_api_bp.route("/api/skills/queue/add", methods=["POST"])
def add_to_skill_queue():
    """Adds a task item to the skill execution queue."""
    data = request.json or {}
    skill_id = data.get("skill_id")
    context = data.get("context", {})
    if not skill_id:
        return jsonify({"error": "skill_id required"}), 400

    qm = _get_configured_queue_manager()
    item = qm.add_to_queue(skill_id, context)
    return jsonify({"status": "ok", "item": item.to_dict()})


@skills_queue_api_bp.route("/api/skills/queue/remove", methods=["POST"])
def remove_from_skill_queue():
    """Removes a pending task from the execution queue."""
    data = request.json or {}
    queue_id = data.get("queue_id")
    if not queue_id:
        return jsonify({"error": "queue_id required"}), 400

    qm = _get_configured_queue_manager()
    success = qm.remove_from_queue(queue_id)
    if success:
        return jsonify({"status": "ok"})
    return jsonify({"error": "Item not found or currently running"}), 400


@skills_queue_api_bp.route("/api/skills/queue/clear", methods=["POST"])
def clear_skill_queue():
    """Clears all pending items from the execution queue."""
    qm = _get_configured_queue_manager()
    qm.clear_queue()
    return jsonify({"status": "ok"})


@skills_queue_api_bp.route("/api/skills/queue/reorder", methods=["POST"])
def reorder_skill_queue():
    """Reorders items in the execution queue."""
    data = request.json or {}
    item_ids = data.get("item_ids", [])
    if not isinstance(item_ids, list):
        return jsonify({"error": "item_ids array required"}), 400

    qm = _get_configured_queue_manager()
    qm.reorder_queue(item_ids)
    return jsonify({"status": "ok"})


@skills_queue_api_bp.route("/api/skills/queue/start", methods=["POST"])
def start_skill_queue():
    """Starts background processing of the skill execution queue."""
    qm = _get_configured_queue_manager()
    success = qm.start_queue()
    return jsonify(
        {
            "status": "started" if success else "empty_or_failed",
            "is_running": qm.is_running,
            "is_paused": qm.is_paused,
        }
    )


@skills_queue_api_bp.route("/api/skills/queue/pause", methods=["POST"])
def pause_skill_queue():
    """Pauses active execution of the skill execution queue."""
    qm = _get_configured_queue_manager()
    success = qm.pause_queue()
    return jsonify(
        {
            "status": "paused" if success else "not_running",
            "is_paused": qm.is_paused,
            "is_running": qm.is_running,
        }
    )


@skills_queue_api_bp.route("/api/skills/queue/resume", methods=["POST"])
def resume_skill_queue():
    """Resumes a paused skill execution queue."""
    qm = _get_configured_queue_manager()
    success = qm.resume_queue()
    return jsonify(
        {
            "status": "resumed" if success else "failed",
            "is_paused": qm.is_paused,
            "is_running": qm.is_running,
        }
    )


@skills_queue_api_bp.route("/api/skills/queue/stop", methods=["POST"])
def stop_skill_queue():
    """Cancels and stops the execution queue."""
    qm = _get_configured_queue_manager()
    qm.stop_queue()
    return jsonify({"status": "stopped", "is_running": False, "is_paused": False})


@skills_queue_api_bp.route("/api/skills/queue/auto_repeat", methods=["POST"])
def set_queue_auto_repeat():
    """Configures recurring periodic polling for export tasks."""
    data = request.json or {}
    enabled = bool(data.get("enabled", False))
    interval_seconds = int(data.get("interval_seconds", 300))
    qm = _get_configured_queue_manager()
    res = qm.set_auto_repeat(enabled, interval_seconds=interval_seconds)
    return jsonify({"status": "ok", **res})


@skills_queue_api_bp.route("/api/skills/<skill_id>/pending_cases", methods=["GET"])
def get_skill_pending_cases(skill_id: str):
    """Finds pending case folders ready for processing by a given export skill."""
    target_base = DashboardState.config.target_base_dir if DashboardState.config else "./Cases"
    extractor = DashboardState.processor.llm_extractor if DashboardState.processor else None
    engine = _get_skill_manager().get_skill_engine(skill_id, vision_extractor=extractor)
    if isinstance(engine, ExportEngine):
        pending = engine.find_pending_cases(target_base)
    else:
        pending = []
    return jsonify({"skill_id": skill_id, "count": len(pending), "cases": pending})


@skills_queue_api_bp.route("/api/skills/<skill_id>/run_batch", methods=["POST"])
def run_skill_batch(skill_id: str):
    """Enqueues all pending case folders for an export skill and starts the queue."""
    target_base = DashboardState.config.target_base_dir if DashboardState.config else "./Cases"
    extractor = DashboardState.processor.llm_extractor if DashboardState.processor else None
    engine = _get_skill_manager().get_skill_engine(skill_id, vision_extractor=extractor)
    if not isinstance(engine, ExportEngine):
        return jsonify({"error": "Batch case run only supported for export skills"}), 400

    pending = engine.find_pending_cases(target_base)
    if not pending:
        return jsonify({"status": "no_pending_cases", "queued_count": 0, "cases": []})

    qm = _get_configured_queue_manager()
    queued_items = []
    for c in pending:
        item = qm.add_to_queue(
            skill_id,
            {"folder_name": c["folder_name"], "folder_path": c["folder_path"]},
        )
        queued_items.append(item.to_dict())
    qm.start_queue()
    return jsonify(
        {
            "status": "queued_and_started",
            "queued_count": len(pending),
            "cases": [c["folder_name"] for c in pending],
        }
    )
