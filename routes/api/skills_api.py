import base64
import logging
import os
import threading
import time
from io import BytesIO

from flask import Blueprint, jsonify, request

from core.skills_engine import (
    SkillExecutor,
    SkillManager,
    SoMGrounder,
    get_skill_queue_manager,
)
from routes.api.documents_api import (
    _is_within_base,
    _parse_folder_name,
)
from routes.state import DashboardState

skills_api_bp = Blueprint("api_skills", __name__)

logger = logging.getLogger(__name__)

_SKILL_MANAGER = None


def _get_skill_manager():
    global _SKILL_MANAGER
    if _SKILL_MANAGER is None:
        base_dir = (
            DashboardState.config.base_dir if DashboardState.config else os.getcwd()
        )
        skills_dir = os.path.join(base_dir, "settings", "skills")
        _SKILL_MANAGER = SkillManager(skills_dir=skills_dir)
    return _SKILL_MANAGER


@skills_api_bp.route("/api/skills", methods=["GET"])
def get_skills():
    skills = _get_skill_manager().list_skills()
    return jsonify({"skills": skills})


@skills_api_bp.route("/api/skills", methods=["POST"])
def save_skill():
    data = request.json
    if not isinstance(data, dict):
        return jsonify({"error": "Invalid JSON payload"}), 400

    skill_id = _get_skill_manager().save_skill(data)
    return jsonify({"status": "ok", "skill_id": skill_id})


@skills_api_bp.route("/api/skills/<skill_id>", methods=["DELETE"])
def delete_skill(skill_id: str):
    success = _get_skill_manager().delete_skill(skill_id)
    if success:
        return jsonify({"status": "ok"})
    return jsonify({"error": "Skill not found"}), 404


@skills_api_bp.route("/api/skills/<skill_id>/duplicate", methods=["POST"])
def duplicate_skill(skill_id: str):
    new_skill = _get_skill_manager().duplicate_skill(skill_id)
    if new_skill:
        return jsonify({"status": "ok", "skill": new_skill})
    return jsonify({"error": "Could not duplicate skill"}), 400


@skills_api_bp.route("/api/skills/run", methods=["POST"])
def run_skill():
    data = request.json or {}
    skill_id = data.get("skill_id")
    context = data.get("context", {})

    if not skill_id:
        return jsonify({"error": "skill_id required"}), 400

    extractor = (
        DashboardState.processor.llm_extractor if DashboardState.processor else None
    )

    executor = SkillExecutor(_get_skill_manager(), vision_extractor=extractor)

    def _run():
        executor.execute_skill(skill_id, context)

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"status": "started", "skill_id": skill_id})


@skills_api_bp.route("/api/skills/approve_and_run", methods=["POST"])
def approve_and_run_skill():
    data = request.json or {}
    skill_id = data.get("skill_id")
    folder_name = data.get("folder_name")

    if not skill_id or not folder_name:
        return jsonify({"error": "skill_id and folder_name required"}), 400

    target_base = (
        DashboardState.config.target_base_dir if DashboardState.config else "./Cases"
    )
    folder_path = os.path.abspath(os.path.join(target_base, folder_name))

    if not _is_within_base(folder_path, target_base) or not os.path.exists(folder_path):
        return jsonify({"error": "Folder not found or invalid path"}), 404

    approved_marker = os.path.join(folder_path, ".approved")
    try:
        with open(approved_marker, "w", encoding="utf-8") as f:
            f.write(f"Approved at {time.ctime()} for skill {skill_id}\n")
    except OSError as e:
        logger.warning("[API] Error writing approved marker: %s", e)

    parsed_meta = _parse_folder_name(folder_name)
    context = dict(parsed_meta)
    person = parsed_meta.get("Person", "") or parsed_meta.get("person", "")
    if person and "," in person:
        parts = person.split(",", 1)
        context.setdefault("Nachname", parts[0].strip())
        context.setdefault("Vorname", parts[1].strip())
    elif person:
        context.setdefault("Nachname", person.strip())

    extractor = (
        DashboardState.processor.llm_extractor if DashboardState.processor else None
    )

    executor = SkillExecutor(_get_skill_manager(), vision_extractor=extractor)

    def _run():
        executor.execute_skill_for_folder(skill_id, folder_path, context)

    threading.Thread(target=_run, daemon=True).start()
    return jsonify(
        {
            "status": "approved_and_started",
            "skill_id": skill_id,
            "folder_name": folder_name,
        }
    )


@skills_api_bp.route("/api/skills/screenshot_preview", methods=["POST"])
def screenshot_preview():
    data = request.json or {}
    window_title = data.get("window_title")

    screen = SoMGrounder.capture_screen(window_title)
    if not screen:
        return jsonify({"error": "Could not capture screenshot"}), 500

    buf = BytesIO()
    screen.save(buf, format="JPEG", quality=75)
    b64_str = base64.b64encode(buf.getvalue()).decode("utf-8")
    return jsonify({"image": f"data:image/jpeg;base64,{b64_str}"})


@skills_api_bp.route("/api/skills/recorder/start", methods=["POST"])
def start_skill_recorder():
    from core.skill_recorder import SkillRecorder

    data = request.json or {}
    skill_name = data.get("skill_name", "Neuer Aufgezeichneter Skill")
    recorder = SkillRecorder.get_instance()
    try:
        res = recorder.start_recording(skill_name=skill_name)
        return jsonify(res)
    except (OSError, RuntimeError, ValueError, TypeError) as e:
        return jsonify({"error": str(e)}), 400


@skills_api_bp.route("/api/skills/recorder/stop", methods=["POST"])
def stop_skill_recorder():
    from core.skill_recorder import SkillRecorder

    recorder = SkillRecorder.get_instance()
    skill_obj = recorder.stop_recording()
    return jsonify({"status": "stopped", "skill": skill_obj})


@skills_api_bp.route("/api/skills/recorder/status", methods=["GET"])
def status_skill_recorder():
    from core.skill_recorder import SkillRecorder

    recorder = SkillRecorder.get_instance()
    return jsonify(recorder.get_status())


# ── Skill Queue Endpoints ──


@skills_api_bp.route("/api/skills/queue", methods=["GET"])
def get_skill_queue():
    qm = get_skill_queue_manager(_get_skill_manager())
    return jsonify(qm.get_queue_state())


@skills_api_bp.route("/api/skills/queue/add", methods=["POST"])
def add_to_skill_queue():
    data = request.json or {}
    skill_id = data.get("skill_id")
    context = data.get("context", {})
    if not skill_id:
        return jsonify({"error": "skill_id required"}), 400

    qm = get_skill_queue_manager(_get_skill_manager())
    item = qm.add_to_queue(skill_id, context)
    return jsonify({"status": "ok", "item": item})


@skills_api_bp.route("/api/skills/queue/remove", methods=["POST"])
def remove_from_skill_queue():
    data = request.json or {}
    queue_id = data.get("queue_id")
    if not queue_id:
        return jsonify({"error": "queue_id required"}), 400

    qm = get_skill_queue_manager(_get_skill_manager())
    success = qm.remove_from_queue(queue_id)
    if success:
        return jsonify({"status": "ok"})
    return jsonify({"error": "Item not found or currently running"}), 400


@skills_api_bp.route("/api/skills/queue/reorder", methods=["POST"])
def reorder_skill_queue():
    data = request.json or {}
    item_ids = data.get("item_ids", [])
    if not isinstance(item_ids, list):
        return jsonify({"error": "item_ids array required"}), 400

    qm = get_skill_queue_manager(_get_skill_manager())
    qm.reorder_queue(item_ids)
    return jsonify({"status": "ok"})


@skills_api_bp.route("/api/skills/queue/start", methods=["POST"])
def start_skill_queue():
    qm = get_skill_queue_manager(_get_skill_manager())
    qm.start_queue()
    return jsonify({"status": "started", "is_running": True})


@skills_api_bp.route("/api/skills/queue/stop", methods=["POST"])
def stop_skill_queue():
    qm = get_skill_queue_manager(_get_skill_manager())
    qm.stop_queue()
    return jsonify({"status": "stopped", "is_running": False})


# ── Per-Skill Document Types Endpoints ──


@skills_api_bp.route("/api/skills/<import_skill_id>/documents", methods=["GET"])
def get_skill_document_types(import_skill_id: str):
    if not DashboardState.config:
        return jsonify({"error": "Config not available"}), 503
    doc_types = DashboardState.config.get_document_types_for_skill(import_skill_id)
    return jsonify({"document_types": doc_types})


@skills_api_bp.route("/api/skills/<import_skill_id>/documents", methods=["PUT"])
def save_skill_document_types(import_skill_id: str):
    if not DashboardState.config:
        return jsonify({"error": "Config not available"}), 503
    data = request.json or {}
    doc_types = data.get("document_types", {})
    if not isinstance(doc_types, dict):
        return jsonify({"error": "document_types dict required"}), 400

    DashboardState.config.save_document_types_for_skill(import_skill_id, doc_types)
    # Also update in-memory config if it's the active import skill
    DashboardState.config.document_types = (
        DashboardState.config.get_document_types_for_skill(import_skill_id)
    )
    return jsonify(
        {"status": "ok", "document_types": DashboardState.config.document_types}
    )
