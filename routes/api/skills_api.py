import base64
import ctypes
import json
import logging
import os
import re
import sys
import time
from io import BytesIO
from typing import Any

import yaml
from flask import Blueprint, jsonify, request

from core.skills import (
    SkillManager,
    SkillQueueManager,
    SoMGrounder,
    get_skill_manager,
    get_skill_queue_manager,
)
from core.skills.engines.export_engine import ExportEngine
from core.skills.models import TaskProgress
from core.skills.synthesizer import SkillSynthesizer
from routes.api.documents_api import (
    _is_within_base,
    _parse_folder_name,
)
from routes.state import DashboardState

skills_api_bp = Blueprint("api_skills", __name__)

logger = logging.getLogger(__name__)


def _get_skill_manager() -> SkillManager:
    return get_skill_manager()


def _get_configured_queue_manager() -> SkillQueueManager:
    return get_skill_queue_manager(_get_skill_manager())


@skills_api_bp.route("/api/skills", methods=["GET"])
def get_skills():
    skills = _get_skill_manager().list_skills()
    return jsonify({"skills": skills})


@skills_api_bp.route("/api/skills", methods=["POST"])
def save_skill():
    data = request.json
    if not isinstance(data, dict):
        return jsonify({"error": "Invalid JSON payload"}), 400

    mgr = _get_skill_manager()
    original_name = str(
        data.pop("original_name", None) or data.pop("old_name", None) or data.pop("original_id", None) or ""
    ).strip()
    name = str(data.get("name") or data.get("id") or "").strip()
    if not name:
        name = "Untitled Skill"
        data["name"] = name

    is_valid, err_msg = mgr.validate_name(name)
    if not is_valid:
        return jsonify({"error": err_msg}), 400

    try:
        if original_name and original_name != name:
            saved_name = mgr.rename_skill(original_name, name, data)
        else:
            saved_name = mgr.save_skill(data)
        return jsonify({"status": "ok", "skill_id": saved_name, "name": saved_name})
    except Exception as e:
        logger.error("[SkillsAPI] Error saving skill: %s", e)
        return jsonify({"error": str(e)}), 400


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
    return jsonify({"status": "queued_and_started", "skill_id": skill_id, "item": item.to_dict()})


@skills_api_bp.route("/api/skills/<skill_id>/pending_cases", methods=["GET"])
def get_skill_pending_cases(skill_id: str):
    target_base = DashboardState.config.target_base_dir if DashboardState.config else "./Cases"
    extractor = DashboardState.processor.llm_extractor if DashboardState.processor else None
    engine = _get_skill_manager().get_skill_engine(skill_id, vision_extractor=extractor)
    if isinstance(engine, ExportEngine):
        pending = engine.find_pending_cases(target_base)
    else:
        pending = []
    return jsonify({"skill_id": skill_id, "count": len(pending), "cases": pending})


@skills_api_bp.route("/api/skills/<skill_id>/run_batch", methods=["POST"])
def run_skill_batch(skill_id: str):
    target_base = DashboardState.config.target_base_dir if DashboardState.config else "./Cases"
    extractor = DashboardState.processor.llm_extractor if DashboardState.processor else None
    engine = _get_skill_manager().get_skill_engine(skill_id, vision_extractor=extractor)
    if not isinstance(engine, ExportEngine):
        return jsonify({"status": "error", "message": "Batch case run only supported for export skills"}), 400

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


@skills_api_bp.route("/api/skills/refine_step", methods=["POST"])
def refine_step():
    data = request.json or {}
    instruction = str(data.get("instruction", "")).strip()
    existing_step = data.get("action") or data.get("step")
    if not isinstance(existing_step, dict):
        existing_step = {}

    if not instruction:
        return jsonify({"error": "Instruction is required"}), 400

    step_id = str(existing_step.get("id") or "act_1")
    refined: dict[str, Any] = dict(existing_step)
    refined["id"] = step_id

    # 1. Try LLM parsing if available
    llm_success = False
    if DashboardState.processor and DashboardState.processor.llm_extractor:
        try:
            prompt = (
                f"You configure robotic UI automation steps. Convert this user instruction into a step JSON.\n"
                f'Instruction: "{instruction}"\n'
                f"Current step: {json.dumps(existing_step)}\n\n"
                f"Schema:\n"
                f"- description: string (summary in English)\n"
                f'- action_type: "CLICK" | "DOUBLE_CLICK" | "TYPE_TEXT" | "TYPE_FILE_PATH" | "VERIFY_SCREEN" | "FOCUS_WINDOW" | "CALL_SKILL"\n'
                f"- target: string (element name to locate on screen if click/verify)\n"
                f"- text: string (text or placeholder if typing)\n"
                f"- press_enter: boolean (true if enter should be pressed)\n"
                f"- window_title: string (if FOCUS_WINDOW)\n"
                f"- skill_id: string (if CALL_SKILL)\n"
                f"Return ONLY valid JSON matching this schema."
            )
            extracted = DashboardState.processor.llm_extractor.call_vision_api_json({"messages": [{"role": "user", "content": prompt}]})
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
            target = re.sub(r"(?i)^(doppelklick auf|double click on|klicke doppelt auf)\s*", "", instruction).strip(
                "\"' "
            )
            refined["locator"] = {"type": "auto", "prompt": target or instruction}
        elif any(
            k in lower
            for k in [
                "prüf",
                "warten",
                "verify",
                "check",
                "erscheint",
                "sichtbar",
                "wenn nicht",
                "falls nicht",
                "if not",
            ]
        ):
            refined["action_type"] = "VERIFY_SCREEN"
            parts = re.split(r"(?i)\s*(?:wenn nicht|falls nicht|if not)\s*,?\s*", instruction, maxsplit=1)
            target_part = parts[0]
            target = re.sub(r"(?i)^(prüfe ob|warten auf|verify|check if|suche nach|finde)\s*", "", target_part).strip(
                "\"' "
            )
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

    return jsonify({"status": "ok", "action": refined, "step": refined})


@skills_api_bp.route("/api/skills/synthesize", methods=["POST"])
def synthesize_skill():
    data = request.json or {}
    raw_steps = data.get("steps") or []
    user_instruction = str(data.get("user_instruction") or "").strip()
    existing_doc_types = data.get("existing_doc_types")

    try:
        synthesis = SkillSynthesizer.synthesize(
            raw_steps=raw_steps,
            user_instruction=user_instruction,
            existing_doc_types=existing_doc_types,
        )
        return jsonify({"status": "ok", "synthesis": synthesis})
    except Exception as e:
        logger.error("[synthesize_skill] Failed to synthesize skill: %s", e)
        return jsonify({"error": str(e)}), 500


@skills_api_bp.route("/api/skills/ai_modify", methods=["POST"])
def ai_modify_skill():
    data = request.json or {}
    existing_skill = data.get("skill") or {}
    user_instruction = str(data.get("instruction") or "").strip()
    history = data.get("history")

    if not user_instruction:
        return jsonify({"error": "Instruction is required"}), 400

    try:
        updated, reply = SkillSynthesizer.modify_skill(
            existing_skill=existing_skill,
            user_instruction=user_instruction,
            history=history if isinstance(history, list) else None,
        )
        return jsonify({"status": "ok", "skill": updated, "reply": reply})
    except Exception as e:
        logger.error("[ai_modify_skill] Failed to modify skill: %s", e)
        return jsonify({"error": str(e)}), 500


@skills_api_bp.route("/api/skills/to_yaml", methods=["POST"])
def skill_to_yaml():
    data = request.json or {}
    skill_data = data.get("skill") or data
    try:
        yaml_str = yaml.safe_dump(skill_data, allow_unicode=True, sort_keys=False)
        return jsonify({"status": "ok", "yaml": yaml_str})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@skills_api_bp.route("/api/skills/from_yaml", methods=["POST"])
def skill_from_yaml():
    data = request.json or {}
    yaml_str = str(data.get("yaml") or "")
    try:
        parsed = yaml.safe_load(yaml_str)
        if not isinstance(parsed, dict):
            return jsonify({"error": "YAML must represent a mapping/dictionary"}), 400
        return jsonify({"status": "ok", "skill": parsed})
    except Exception as e:
        return jsonify({"error": f"Invalid YAML syntax: {e}"}), 400


@skills_api_bp.route("/api/skills/<skill_id>/yaml", methods=["GET", "POST"])
def skill_yaml_file(skill_id: str):
    mgr = _get_skill_manager()
    clean_name = mgr.sanitize_name(skill_id)
    filepath = os.path.join(mgr.skills_dir, f"{clean_name}.yaml")

    if request.method == "GET":
        if os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                return jsonify({"status": "ok", "yaml": content})
            except Exception as e:
                return jsonify({"error": str(e)}), 500
        else:
            skill = mgr.get_skill(skill_id)
            if skill:
                return jsonify({"status": "ok", "yaml": yaml.safe_dump(skill, allow_unicode=True, sort_keys=False)})
            return jsonify({"error": "Skill not found"}), 404

    # POST: Save raw YAML directly
    data = request.json or {}
    yaml_str = str(data.get("yaml") or "")
    if not yaml_str.strip():
        return jsonify({"error": "Empty YAML content"}), 400

    try:
        parsed = yaml.safe_load(yaml_str)
        if not isinstance(parsed, dict):
            return jsonify({"error": "YAML must represent a dictionary"}), 400
        name = str(parsed.get("name") or skill_id).strip()
        parsed["name"] = name
        parsed["id"] = name
        saved_name = mgr.save_skill(parsed)
        return jsonify({"status": "ok", "skill_id": saved_name, "name": saved_name, "skill": parsed})
    except Exception as e:
        return jsonify({"error": f"YAML validation error: {e}"}), 400


@skills_api_bp.route("/api/skills/approve_and_run", methods=["POST"])
def approve_and_run_skill():
    data = request.json or {}
    skill_id = data.get("skill_id")
    folder_name = data.get("folder_name")

    if not skill_id or not folder_name:
        return jsonify({"error": "skill_id and folder_name required"}), 400

    target_base = DashboardState.config.target_base_dir if DashboardState.config else "./Cases"
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
            "queue_item": item.to_dict(),
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


@skills_api_bp.route("/api/skills/pick_element", methods=["POST"])
def pick_element_live():
    """Captures live screen context at the active cursor position to pick element text and coordinates."""
    data = request.json or {}
    window_title = data.get("window_title")

    delay_s = float(data.get("delay_seconds", 0.5))
    if delay_s > 0:
        time.sleep(delay_s)

    cur_x, cur_y = 0, 0
    if sys.platform == "win32":
        try:
            pt = ctypes.wintypes.POINT()  # type: ignore[attr-defined]
            ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))  # type: ignore[union-attr]
            cur_x, cur_y = pt.x, pt.y
        except Exception:
            pass

    screen = SoMGrounder.capture_screen(window_title)
    if not screen:
        return jsonify({"error": "Screen could not be captured"}), 500

    ocr_text = ""
    try:
        from core.extraction_pipeline import _get_rapid_ocr
        import numpy as np

        engine = _get_rapid_ocr()
        if engine:
            img_np = np.array(screen)
            res, _ = engine(img_np)
            if res:
                best_dist = float("inf")
                best_text = ""
                for line in res:
                    box, text, _ = line
                    t = text.strip()
                    if not t:
                        continue
                    xs = [float(p[0]) for p in box]
                    ys = [float(p[1]) for p in box]
                    bx = sum(xs) / len(xs)
                    by = sum(ys) / len(ys)
                    dist = ((bx - cur_x) ** 2 + (by - cur_y) ** 2) ** 0.5
                    if dist < best_dist and dist < 250:
                        best_dist = dist
                        best_text = t

                ocr_text = best_text
    except Exception as e:
        logger.debug("[pick_element_live] RapidOCR snippet error: %s", e)

    return jsonify({
        "status": "ok",
        "cursor": [cur_x, cur_y],
        "ocr_text": ocr_text,
        "locator": {
            "type": "ocr_contains" if ocr_text else "smart",
            "prompt": ocr_text or f"Element at ({cur_x}, {cur_y})",
            "offset": [0, 0],
        },
    })


@skills_api_bp.route("/api/skills/test_run", methods=["POST"])
def test_run_skill():
    """Executes a test run of the provided skill with mock/provided context."""
    data = request.json or {}
    skill_def = data.get("skill")
    if not isinstance(skill_def, dict):
        return jsonify({"error": "Valid skill definition is required"}), 400

    test_context = data.get("context") or {}
    if not isinstance(test_context, dict):
        test_context = {}

    test_context.setdefault("document_fullpath", "C:\\OrdinFlowTest\\Cases\\Test_Patient_2026\\Fußscan.pdf")
    test_context.setdefault("Nachname", "Mustermann")
    test_context.setdefault("Vorname", "Max")
    test_context.setdefault("Datum", time.strftime("%Y-%m-%d"))
    test_context.setdefault("Fallnummer", "F-2026-001")
    test_context.setdefault("category", "Fußscan")

    mgr = _get_skill_manager()
    vext = DashboardState.processor.llm_extractor if DashboardState.processor else None
    engine = ExportEngine(skill_def, skill_manager=mgr, vision_extractor=vext)

    progress_log: list[dict[str, Any]] = []

    def test_reporter(progress: TaskProgress):
        progress_log.append(progress.to_dict())

    start_t = time.time()
    try:
        success = engine.execute_actions(context=test_context, reporter=test_reporter)
        duration_s = round(time.time() - start_t, 2)
        return jsonify({
            "status": "ok" if success else "failed",
            "success": success,
            "duration_seconds": duration_s,
            "total_actions": len(engine.actions),
            "progress_log": progress_log,
        })
    except Exception as e:
        logger.error("[test_run_skill] Test run exception: %s", e, exc_info=True)
        duration_s = round(time.time() - start_t, 2)
        return jsonify({
            "status": "error",
            "success": False,
            "error": str(e),
            "duration_seconds": duration_s,
            "progress_log": progress_log,
        }), 500


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
    return jsonify({"status": "ok", "item": item.to_dict()})


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
    success = qm.start_queue()
    return jsonify(
        {"status": "started" if success else "empty_or_failed", "is_running": qm.is_running, "is_paused": qm.is_paused}
    )


@skills_api_bp.route("/api/skills/queue/pause", methods=["POST"])
def pause_skill_queue():
    qm = _get_configured_queue_manager()
    success = qm.pause_queue()
    return jsonify(
        {"status": "paused" if success else "not_running", "is_paused": qm.is_paused, "is_running": qm.is_running}
    )


@skills_api_bp.route("/api/skills/queue/resume", methods=["POST"])
def resume_skill_queue():
    qm = _get_configured_queue_manager()
    success = qm.resume_queue()
    return jsonify(
        {"status": "resumed" if success else "failed", "is_paused": qm.is_paused, "is_running": qm.is_running}
    )


@skills_api_bp.route("/api/skills/queue/stop", methods=["POST"])
def stop_skill_queue():
    qm = _get_configured_queue_manager()
    qm.stop_queue()
    return jsonify({"status": "stopped", "is_running": False, "is_paused": False})


@skills_api_bp.route("/api/skills/queue/auto_repeat", methods=["POST"])
def set_queue_auto_repeat():
    data = request.json or {}
    enabled = bool(data.get("enabled", False))
    interval_seconds = int(data.get("interval_seconds", 300))
    qm = _get_configured_queue_manager()
    res = qm.set_auto_repeat(enabled, interval_seconds=interval_seconds)
    return jsonify({"status": "ok", **res})


# ── Per-Skill Document Types Endpoints ──


@skills_api_bp.route("/api/skills/<import_skill_id>/documents", methods=["GET"])
def get_skill_document_types(import_skill_id: str):
    mgr = _get_skill_manager()
    doc_types = mgr.get_document_types_for_skill(import_skill_id)
    return jsonify({"document_types": doc_types})


@skills_api_bp.route("/api/skills/<import_skill_id>/documents", methods=["PUT"])
def save_skill_document_types(import_skill_id: str):
    mgr = _get_skill_manager()
    data = request.json or {}
    doc_types = data.get("document_types", {})
    if not isinstance(doc_types, dict):
        return jsonify({"error": "document_types dict required"}), 400

    mgr.save_document_types_for_skill(import_skill_id, doc_types)
    if DashboardState.config:
        DashboardState.config.document_types = doc_types
    return jsonify({"status": "ok", "document_types": doc_types})
