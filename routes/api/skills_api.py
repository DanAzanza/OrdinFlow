"""Skills API aggregator and authoring/recorder/execution endpoints."""

from __future__ import annotations

import ctypes
import json
import logging
from pathlib import Path
import re
import sys
import time
from typing import Any

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
from core.utils import is_within_allowed_roots, sanitize_safe_path
from routes.api.skills_crud_api import skills_crud_api_bp
from routes.api.skills_queue_api import skills_queue_api_bp
from routes.state import DashboardState

skills_api_bp = Blueprint("api_skills", __name__)
skills_api_bp.register_blueprint(skills_crud_api_bp)
skills_api_bp.register_blueprint(skills_queue_api_bp)

logger = logging.getLogger(__name__)


def _get_skill_manager() -> SkillManager:
    return get_skill_manager()


def _get_configured_queue_manager() -> SkillQueueManager:
    return get_skill_queue_manager(_get_skill_manager())


@skills_api_bp.route("/api/skills/refine_step", methods=["POST"])
def refine_step():
    """Natural-language conversion of user instructions into structured action step JSON."""
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
            instruction_lower = instruction.lower()
            split_idx = -1
            match_len = 0
            for marker in ("wenn nicht", "falls nicht", "if not"):
                idx = instruction_lower.find(marker)
                if idx != -1:
                    split_idx = idx
                    match_len = len(marker)
                    break

            if split_idx != -1:
                target_part = instruction[:split_idx].rstrip(" ,")
                fallback_part = instruction[split_idx + match_len:].lstrip(" :")
                parts = [target_part, fallback_part]
            else:
                parts = [instruction]
                target_part = instruction

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
    """Generates structured automation skills from recording steps and natural language."""
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
        logger.error("[synthesize_skill] Failed to synthesize skill: %s", e, exc_info=True)
        return jsonify({"error": "Failed to synthesize skill"}), 500


@skills_api_bp.route("/api/skills/ai_modify", methods=["POST"])
def ai_modify_skill():
    """Uses LLM copilot to iteratively adjust skill configuration."""
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
        logger.error("[ai_modify_skill] Failed to modify skill: %s", e, exc_info=True)
        return jsonify({"error": "Failed to modify skill"}), 500


@skills_api_bp.route("/api/skills/recorder/start", methods=["POST"])
def start_skill_recorder():
    """Starts the interactive desktop macro recorder."""
    from core.skill_recorder import SkillRecorder

    data = request.json or {}
    skill_name = data.get("skill_name", "New Recorded Skill")
    recorder = SkillRecorder.get_instance()
    try:
        res = recorder.start_recording(skill_name=skill_name)
        return jsonify(res)
    except (OSError, RuntimeError, ValueError, TypeError) as e:
        logger.warning("[start_skill_recorder] Error starting recorder: %s", e)
        return jsonify({"error": "Failed to start skill recorder"}), 400


@skills_api_bp.route("/api/skills/recorder/stop", methods=["POST"])
def stop_skill_recorder():
    """Stops the macro recorder and returns captured actions."""
    from core.skill_recorder import SkillRecorder

    recorder = SkillRecorder.get_instance()
    skill_obj = recorder.stop_recording()
    return jsonify({"status": "stopped", "skill": skill_obj})


@skills_api_bp.route("/api/skills/recorder/status", methods=["GET"])
def status_skill_recorder():
    """Returns recording status and captured step counts."""
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
        except Exception as e:
            logger.debug("[skills_api] Failed to get cursor position: %s", e)

    screen = SoMGrounder.capture_screen(window_title)
    if not screen:
        return jsonify({"error": "Screen could not be captured"}), 500

    ocr_text = ""
    try:
        from core.image_processing import run_rapid_ocr
        import numpy as np

        img_np = np.array(screen)
        res = run_rapid_ocr(img_np)
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

    raw_doc_path = str(test_context.get("document_fullpath", "") or "").strip()
    is_safe_doc, clean_doc = sanitize_safe_path(raw_doc_path)
    doc_path = ""
    if is_safe_doc and clean_doc:
        resolved_doc = Path(clean_doc).resolve()
        if resolved_doc.is_file() and is_within_allowed_roots(resolved_doc):
            doc_path = str(resolved_doc)
    if raw_doc_path and not doc_path:
        return jsonify({"error": f"Provided document path is invalid, unauthorized, or does not exist: {raw_doc_path}"}), 400

    # If the skill definition requires a source document but none was provided
    requires_doc = False
    all_actions: list[dict[str, Any]] = []
    for task in skill_def.get("tasks", []):
        if isinstance(task, dict):
            all_actions.extend(task.get("actions", []))
    for act in skill_def.get("steps", []) + skill_def.get("actions", []):
        if isinstance(act, dict):
            all_actions.append(act)

    for act in all_actions:
        act_type = str(act.get("action_type") or act.get("type", "")).upper()
        cmd = str(act.get("command", "") or act.get("script", "") or act.get("file_path", ""))
        if act_type == "TYPE_FILE_PATH" or "{document_fullpath}" in cmd:
            requires_doc = True
            break

    if requires_doc and not doc_path:
        return jsonify({"error": "This skill requires a valid document ('document_fullpath') in context. Execution aborted without mock data."}), 400

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
            "error": "An error occurred during skill test execution",
            "duration_seconds": duration_s,
            "progress_log": progress_log,
        }), 500


__all__ = [
    "skills_api_bp",
    "skills_crud_api_bp",
    "skills_queue_api_bp",
]
