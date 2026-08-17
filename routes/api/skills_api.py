import base64
import json
import logging
import os
import re
import time
from io import BytesIO
from typing import Any

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


def _get_skill_manager() -> SkillManager:
    global _SKILL_MANAGER
    if _SKILL_MANAGER is None:
        base_dir = (
            DashboardState.config.base_dir if DashboardState.config else os.getcwd()
        )
        skills_dir = os.path.join(base_dir, "settings", "skills")
        _SKILL_MANAGER = SkillManager(skills_dir=skills_dir)
    return _SKILL_MANAGER


def _handle_queue_import(item: dict[str, Any]) -> bool:
    if not DashboardState.processor:
        return True

    from main import process_existing_files

    processor = DashboardState.processor
    skill_obj = _get_skill_manager().get_skill(item["skill_id"])
    allowed_exts = (
        skill_obj.get("allowed_extensions") if skill_obj else None
    )

    if DashboardState.file_queue is not None:
        process_existing_files(
            processor,
            DashboardState.file_queue,
            allowed_extensions=allowed_exts,
        )

        # Wait until all queued and actively processing files finish
        while True:
            with processor.processing_lock:
                busy_files_count = len(processor.processing_files)
            queue_count = (
                DashboardState.file_queue.qsize()
                if hasattr(DashboardState.file_queue, "qsize")
                else 0
            )

            if busy_files_count == 0 and queue_count == 0:
                break

            time.sleep(0.5)
    else:
        import queue

        temp_q: queue.Queue = queue.Queue()
        process_existing_files(
            processor,
            temp_q,
            allowed_extensions=allowed_exts,
        )
        while not temp_q.empty():
            fp = temp_q.get()
            if fp:
                try:
                    processor.process_and_route_file(fp)
                except Exception as e:
                    logger.error(
                        "[SkillQueueManager] Error processing file %s: %s",
                        fp,
                        e,
                    )
                finally:
                    temp_q.task_done()

    return True


def _handle_queue_export(item: dict[str, Any]) -> bool:
    extractor = (
        DashboardState.processor.llm_extractor
        if DashboardState.processor
        else None
    )
    executor = SkillExecutor(
        _get_skill_manager(), vision_extractor=extractor
    )
    context = item.get("context", {})
    folder_name = context.get("folder_name")
    target_base = (
        DashboardState.config.target_base_dir
        if DashboardState.config
        else "./Cases"
    )

    if folder_name:
        folder_path = os.path.abspath(
            os.path.join(target_base, folder_name)
        )
        return executor.execute_skill_for_folder(
            item["skill_id"], folder_path, context
        )
    else:
        # Batch execution: find and process all pending approved folders
        pending = executor.find_pending_cases_for_skill(
            item["skill_id"], target_base
        )
        if not pending:
            logger.info(
                "[SkillQueueManager] No pending cases for export skill %s",
                item["skill_id"],
            )
            return True

        all_ok = True
        for c in pending:
            parsed = _parse_folder_name(c["folder_name"])
            c_ctx = dict(parsed)
            c_ctx["folder_name"] = c["folder_name"]
            c_ctx["folder_path"] = c["folder_path"]
            person = parsed.get("Person", "") or parsed.get("person", "")
            if person and "," in person:
                parts = person.split(",", 1)
                c_ctx.setdefault("Nachname", parts[0].strip())
                c_ctx.setdefault("Vorname", parts[1].strip())
            elif person:
                c_ctx.setdefault("Nachname", person.strip())

            if not executor.execute_skill_for_folder(
                item["skill_id"], c["folder_path"], c_ctx
            ):
                all_ok = False
        return all_ok


def _get_configured_queue_manager():
    qm = get_skill_queue_manager(_get_skill_manager())
    qm.set_handlers(
        import_handler=_handle_queue_import,
        export_handler=_handle_queue_export,
    )
    return qm


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

    qm = _get_configured_queue_manager()
    item = qm.add_to_queue(skill_id, context)
    qm.start_queue()
    return jsonify({"status": "queued_and_started", "skill_id": skill_id, "item": item})


@skills_api_bp.route("/api/skills/<skill_id>/pending_cases", methods=["GET"])
def get_skill_pending_cases(skill_id: str):
    target_base = (
        DashboardState.config.target_base_dir
        if DashboardState.config
        else "./Cases"
    )
    extractor = (
        DashboardState.processor.llm_extractor
        if DashboardState.processor
        else None
    )
    executor = SkillExecutor(_get_skill_manager(), vision_extractor=extractor)
    pending = executor.find_pending_cases_for_skill(skill_id, target_base)
    return jsonify({"skill_id": skill_id, "count": len(pending), "cases": pending})


@skills_api_bp.route("/api/skills/<skill_id>/run_batch", methods=["POST"])
def run_skill_batch(skill_id: str):
    target_base = (
        DashboardState.config.target_base_dir
        if DashboardState.config
        else "./Cases"
    )
    extractor = (
        DashboardState.processor.llm_extractor
        if DashboardState.processor
        else None
    )
    executor = SkillExecutor(_get_skill_manager(), vision_extractor=extractor)
    pending = executor.find_pending_cases_for_skill(skill_id, target_base)

    if not pending:
        return jsonify({"status": "no_pending_cases", "queued_count": 0, "cases": []})

    qm = _get_configured_queue_manager()
    queued_items = []
    for c in pending:
        item = qm.add_to_queue(
            skill_id,
            {"folder_name": c["folder_name"], "folder_path": c["folder_path"]},
        )
        queued_items.append(item)
    qm.start_queue()
    return jsonify(
        {
            "status": "queued_and_started",
            "queued_count": len(pending),
            "cases": [c["folder_name"] for c in pending],
        }
    )


@skills_api_bp.route("/api/skills/refine_step", methods=["POST"])
def refine_step():
    data = request.json or {}
    instruction = str(data.get("instruction", "")).strip()
    existing_step = data.get("step")
    if not isinstance(existing_step, dict):
        existing_step = {}

    if not instruction:
        return jsonify({"error": "Instruction is required"}), 400

    step_id = str(existing_step.get("id") or "step_1")
    refined: dict[str, Any] = dict(existing_step)
    refined["id"] = step_id

    # 1. Try LLM parsing if available
    llm_success = False
    if DashboardState.processor and DashboardState.processor.llm_extractor:
        try:
            prompt = (
                f"You configure robotic UI automation steps. Convert this user instruction into a step JSON.\n"
                f"Instruction: \"{instruction}\"\n"
                f"Current step: {json.dumps(existing_step)}\n\n"
                f"Schema:\n"
                f"- description: string (summary in English)\n"
                f"- action_type: \"CLICK\" | \"DOUBLE_CLICK\" | \"TYPE_TEXT\" | \"TYPE_FILE_PATH\" | \"VERIFY_SCREEN\" | \"FOCUS_WINDOW\" | \"CALL_SKILL\"\n"
                f"- target: string (element name to locate on screen if click/verify)\n"
                f"- text: string (text or placeholder if typing)\n"
                f"- press_enter: boolean (true if enter should be pressed)\n"
                f"- window_title: string (if FOCUS_WINDOW)\n"
                f"- skill_id: string (if CALL_SKILL)\n"
                f"Return ONLY valid JSON matching this schema."
            )
            extracted = DashboardState.processor.llm_extractor.extract_fields_from_text(prompt, {})
            if isinstance(extracted, dict) and extracted.get("action_type"):
                refined.update(extracted)
                if extracted.get("target"):
                    refined["locator"] = {"type": "auto", "prompt": str(extracted["target"])}
                llm_success = True
        except Exception as e:
            logger.debug("[refine_step] LLM extraction fallback: %s", e)

    if not llm_success:
        lower = instruction.lower()
        refined["description"] = instruction[:60]
        press_enter = any(k in lower for k in ["enter", "drücke enter", "press enter", "bestätig", "submit"])
        refined["press_enter"] = press_enter

        if any(k in lower for k in ["datei", "file", "pfad", "path", "upload", "hochladen", "pdf"]):
            refined["action_type"] = "TYPE_FILE_PATH"
            refined["file_path"] = "{document_fullpath}"
        elif any(k in lower for k in ["tipp", "type", "schreib", "eingeben", "enter text", "text"]):
            refined["action_type"] = "TYPE_TEXT"
            m = re.search(r"\{[^{}]+\}", instruction)
            if m:
                refined["text"] = m.group(0)
            else:
                quotes = re.findall(r"['\"]([^'\"]+)['\"]", instruction)
                refined["text"] = quotes[0] if quotes else instruction
        elif any(k in lower for k in ["doppelklick", "double click"]):
            refined["action_type"] = "DOUBLE_CLICK"
            target = re.sub(r"(?i)^(doppelklick auf|double click on|klicke doppelt auf)\s*", "", instruction).strip("\"' ")
            refined["locator"] = {"type": "auto", "prompt": target or instruction}
        elif any(k in lower for k in ["prüf", "warten", "verify", "check", "erscheint", "sichtbar", "wenn nicht", "falls nicht", "if not"]):
            refined["action_type"] = "VERIFY_SCREEN"
            # Split if condition exists
            parts = re.split(r"(?i)\s*(?:wenn nicht|falls nicht|if not)\s*,?\s*", instruction, maxsplit=1)
            target_part = parts[0]
            target = re.sub(r"(?i)^(prüfe ob|warten auf|verify|check if|suche nach|finde)\s*", "", target_part).strip("\"' ")
            refined["locator"] = {"type": "auto", "prompt": target or target_part}

            if len(parts) > 1:
                fallback_part = parts[1].lower()
                if any(k in fallback_part for k in ["anlegen", "create", "routine", "skill", "ausführen", "starte"]):
                    refined["on_failure_action"] = "run_skill"
                    clean_slug = re.sub(r"[^a-z0-9_]+", "_", fallback_part).strip("_")
                    refined["on_failure_skill"] = clean_slug or "create_patient"
                elif any(k in fallback_part for k in ["pause", "fragen", "warn", "ton", "alert"]):
                    refined["on_failure_action"] = "pause_prompt"
                elif any(k in fallback_part for k in ["überspring", "skip", "abbrech"]):
                    refined["on_failure_action"] = "skip"
        elif any(k in lower for k in ["fenster", "window", "fokus", "focus"]):
            refined["action_type"] = "FOCUS_WINDOW"
            refined["window_title"] = "Remote Desktop*"
        elif any(k in lower for k in ["subskill", "sub-skill", "sub skill", "routine"]):
            refined["action_type"] = "CALL_SKILL"
            m = re.search(r"[\w_]+", instruction)
            refined["skill_id"] = m.group(0) if m else "sub_skill"
        else:
            refined["action_type"] = "CLICK"
            target = re.sub(r"(?i)^(klicke auf|klick auf|click on|klicke|click)\s*", "", instruction).strip("\"' ")
            refined["locator"] = {"type": "auto", "prompt": target or instruction}

    return jsonify({"status": "ok", "step": refined})


@skills_api_bp.route("/api/skills/approve_and_run", methods=["POST"])
def approve_and_run_skill():
    data = request.json or {}
    skill_id = data.get("skill_id")
    folder_name = data.get("folder_name")

    if not skill_id or not folder_name:
        return jsonify({"error": "skill_id and folder_name required"}), 400

    target_base = (
        DashboardState.config.target_base_dir
        if DashboardState.config
        else "./Cases"
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
    context["folder_name"] = folder_name
    context["folder_path"] = folder_path
    person = parsed_meta.get("Person", "") or parsed_meta.get("person", "")
    if person and "," in person:
        parts = person.split(",", 1)
        context.setdefault("Nachname", parts[0].strip())
        context.setdefault("Vorname", parts[1].strip())
    elif person:
        context.setdefault("Nachname", person.strip())

    qm = _get_configured_queue_manager()
    item = qm.add_to_queue(skill_id, context)
    qm.start_queue()

    return jsonify(
        {
            "status": "approved_and_started",
            "skill_id": skill_id,
            "folder_name": folder_name,
            "queue_item": item,
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
    skill_name = data.get("skill_name", "New Recorded Skill")
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
    qm = _get_configured_queue_manager()
    return jsonify(qm.get_queue_state())


@skills_api_bp.route("/api/skills/queue/add", methods=["POST"])
def add_to_skill_queue():
    data = request.json or {}
    skill_id = data.get("skill_id")
    context = data.get("context", {})
    if not skill_id:
        return jsonify({"error": "skill_id required"}), 400

    qm = _get_configured_queue_manager()
    item = qm.add_to_queue(skill_id, context)
    return jsonify({"status": "ok", "item": item})


@skills_api_bp.route("/api/skills/queue/remove", methods=["POST"])
def remove_from_skill_queue():
    data = request.json or {}
    queue_id = data.get("queue_id")
    if not queue_id:
        return jsonify({"error": "queue_id required"}), 400

    qm = _get_configured_queue_manager()
    success = qm.remove_from_queue(queue_id)
    if success:
        return jsonify({"status": "ok"})
    return jsonify({"error": "Item not found or currently running"}), 400


@skills_api_bp.route("/api/skills/queue/clear", methods=["POST"])
def clear_skill_queue():
    qm = _get_configured_queue_manager()
    qm.clear_queue()
    return jsonify({"status": "ok"})


@skills_api_bp.route("/api/skills/queue/reorder", methods=["POST"])
def reorder_skill_queue():
    data = request.json or {}
    item_ids = data.get("item_ids", [])
    if not isinstance(item_ids, list):
        return jsonify({"error": "item_ids array required"}), 400

    qm = _get_configured_queue_manager()
    qm.reorder_queue(item_ids)
    return jsonify({"status": "ok"})


@skills_api_bp.route("/api/skills/queue/start", methods=["POST"])
def start_skill_queue():
    qm = _get_configured_queue_manager()
    qm.start_queue()
    return jsonify({"status": "started", "is_running": True})


@skills_api_bp.route("/api/skills/queue/stop", methods=["POST"])
def stop_skill_queue():
    qm = _get_configured_queue_manager()
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
    DashboardState.config.document_types = (
        DashboardState.config.get_document_types_for_skill(import_skill_id)
    )
    return jsonify(
        {"status": "ok", "document_types": DashboardState.config.document_types}
    )
