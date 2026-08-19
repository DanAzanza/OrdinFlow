"""Robotic Process Automation (RPA) Export Skill Engine."""

from __future__ import annotations

import base64
import ctypes
import json
import logging
import os
import re
import sys
import time
from collections.abc import Callable, Mapping
from io import BytesIO
from typing import Any, cast

from core.skills.base import BaseSkill
from core.skills.grounder import SoMGrounder
from core.skills.models import SkillTask, TaskProgress, TaskResult
from core.skills.shield import input_shield

logger = logging.getLogger(__name__)

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore[assignment]


def _type_unicode_text(text: str, press_enter: bool = False) -> None:
    """Types unicode characters reliably on Windows using KEYEVENTF_UNICODE."""
    if sys.platform != "win32":
        return

    keybd_event = ctypes.windll.user32.keybd_event  # type: ignore[union-attr]
    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_UNICODE = 0x0004

    for char in text:
        code = ord(char)
        keybd_event(0, code, KEYEVENTF_UNICODE, 0)
        keybd_event(0, code, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0)
        time.sleep(0.008)

    if press_enter:
        time.sleep(0.05)
        keybd_event(0x0D, 0, 0, 0)
        keybd_event(0x0D, 0, KEYEVENTF_KEYUP, 0)


class ExportEngine(BaseSkill):
    """Executes step-by-step RPA desktop UI and RDP automations."""

    def __init__(
        self,
        definition_or_manager: dict[str, Any] | Any = None,
        skill_manager: Any = None,
        vision_extractor: Any = None,
    ):
        if isinstance(definition_or_manager, dict):
            definition = definition_or_manager
            mgr = skill_manager
            vext = vision_extractor
        else:
            mgr = definition_or_manager
            definition = {"id": "export_engine", "name": "Export Engine", "type": "export"}
            vext = skill_manager

        super().__init__(definition)
        self.skill_manager = mgr
        self.vision_extractor = vext
        raw_steps = definition.get("steps")
        self.steps: list[dict[str, Any]] = (
            [s for s in raw_steps if isinstance(s, dict)] if isinstance(raw_steps, list) else []
        )
        self.target_window = definition.get("target_window")
        self.rdp_prefix = definition.get("rdp_path_prefix", "")

    def _save_failure_screenshot(self, step_id: str, desc: str = "", window_title: str | None = None) -> str | None:
        """Captures and saves a diagnostic screenshot when a skill step fails."""
        try:
            screen = SoMGrounder.capture_screen(window_title)
            if screen is None:
                screen = SoMGrounder.capture_screen(None)
            if screen is not None:
                base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
                fail_dir = os.path.join(base_dir, "scratch", "rpa_failures")
                os.makedirs(fail_dir, exist_ok=True)
                sanitized_step = re.sub(r"[^\w\-_\.]", "_", step_id)
                filename = f"failure_{int(time.time())}_{sanitized_step}.png"
                target_path = os.path.join(fail_dir, filename)
                screen.save(target_path)
                logger.info("[ExportEngine] Saved failure screenshot to: %s", target_path)
                return target_path
        except Exception as e:
            logger.debug("[ExportEngine] Could not save failure screenshot: %s", e)
        return None

    def _substitute_placeholders(self, text: str, context: Mapping[str, Any]) -> str:
        """Dynamically substitutes placeholders such as {FieldName} from context without synthetic fallbacks."""
        if not isinstance(text, str) or "{" not in text:
            return text

        def replace_match(match: re.Match) -> str:
            key = match.group(1).strip()
            val = context.get(key)
            return str(val) if val is not None else ""

        return re.sub(r"\{([^{}]+)\}", replace_match, text)

    def _locate_target(self, locator: dict[str, Any], window_title: str | None = None) -> tuple[int, int] | None:
        """Determines the (x, y) pixel coordinates for a locator with auto-adaptive OCR & VLM fallback."""
        loc_type = str(locator.get("type", "auto"))
        loc_val = str(locator.get("value", "") or locator.get("prompt", "") or locator.get("target", ""))
        prompt = str(locator.get("prompt", "") or locator.get("value", "") or locator.get("target", ""))
        search_term = prompt or loc_val

        screen = SoMGrounder.capture_screen(window_title)
        if not screen:
            logger.error("[ExportEngine] Screenshot could not be captured.")
            return None

        # 1. Fast OCR Exact/Contains Match (RapidOCR)
        if loc_type in ("auto", "smart", "ocr_exact", "ocr_contains") and search_term:
            from core.extraction_pipeline import _get_rapid_ocr

            engine = _get_rapid_ocr()
            if engine is not None:
                try:
                    img_np = np.array(screen) if np is not None else None
                    if img_np is not None:
                        res, _ = engine(img_np)
                        if res:
                            # Pass 1: Exact match
                            for line in res:
                                box, text, _ = line
                                t = text.strip()
                                if not t:
                                    continue
                                if search_term.lower() == t.lower():
                                    xs = [float(p[0]) for p in box]
                                    ys = [float(p[1]) for p in box]
                                    cx = int(sum(xs) / len(xs))
                                    cy = int(sum(ys) / len(ys))
                                    offset = cast(list[int], locator.get("offset", [0, 0]))
                                    return cx + offset[0], cy + offset[1]

                            # Pass 2: Contains match
                            for line in res:
                                box, text, _ = line
                                t = text.strip()
                                if not t:
                                    continue
                                if search_term.lower() in t.lower() or t.lower() in search_term.lower():
                                    xs = [float(p[0]) for p in box]
                                    ys = [float(p[1]) for p in box]
                                    cx = int(sum(xs) / len(xs))
                                    cy = int(sum(ys) / len(ys))
                                    offset = cast(list[int], locator.get("offset", [0, 0]))
                                    return cx + offset[0], cy + offset[1]
                except Exception as e:
                    logger.warning("[ExportEngine] RapidOCR Locator error: %s", e)

        # 2. Set-of-Mark (SoM) Grounding via VLM
        if (loc_type in ("auto", "smart", "som_vlm")) and self.vision_extractor and search_term:
            som_img, candidates = SoMGrounder.generate_som_overlay(screen)
            buf = BytesIO()
            som_img.save(buf, format="JPEG", quality=85)
            b64_som = base64.b64encode(buf.getvalue()).decode("utf-8")

            ground_prompt = (
                f"Interactive UI elements are marked with red badges `[1]`, `[2]`, ... in this image.\n"
                f"Which element number best matches: '{search_term}'?\n"
                f"Reply ONLY with the exact number in square brackets, e.g. `[14]`."
            )
            payload = {"messages": [{"role": "user", "content": ground_prompt, "images": [b64_som]}]}

            resp = self.vision_extractor.call_vision_api(payload)
            if resp:
                match = re.search(r"\[(\d+)\]", resp)
                if match:
                    elem_id = int(match.group(1))
                    if elem_id in candidates:
                        target = candidates[elem_id]
                        offset_raw = locator.get("offset")
                        offset_x, offset_y = 0, 0
                        if isinstance(offset_raw, (list, tuple)) and len(offset_raw) >= 2:
                            ox, oy = offset_raw[0], offset_raw[1]
                            if isinstance(ox, (int, float)):
                                offset_x = int(ox)
                            if isinstance(oy, (int, float)):
                                offset_y = int(oy)
                        raw_cx = target.get("center_x")
                        raw_cy = target.get("center_y")
                        cx = int(raw_cx) if isinstance(raw_cx, (int, float)) else 0
                        cy = int(raw_cy) if isinstance(raw_cy, (int, float)) else 0
                        return cx + offset_x, cy + offset_y

        logger.warning("[ExportEngine] Locator could not be resolved: %s", locator)
        return None

    def _wait_for_queue(
        self,
        reporter: Callable[[TaskProgress], None] | None = None,
        paused_msg: str = "Execution paused...",
    ) -> bool:
        """Blocks while SkillQueueManager is paused. Returns False if execution was stopped."""
        try:
            from core.skills.queue import get_skill_queue_manager

            qm = get_skill_queue_manager()
            if not qm.is_running and not qm.is_paused:
                return True
            if qm.is_stopped:
                return False
            was_paused = False
            while qm.is_paused and not qm.is_stopped:
                if not was_paused and reporter:
                    reporter(TaskProgress(message=f"⏸️ {paused_msg}"))
                    was_paused = True
                qm.wait_if_paused()
            return not qm.is_stopped
        except Exception:
            return True

    def execute_steps(
        self,
        context: dict[str, Any],
        reporter: Callable[[TaskProgress], None] | None = None,
        depth: int = 0,
    ) -> bool:
        """Executes the defined steps sequentially with input shield protection."""
        if depth > 5:
            logger.error("[ExportEngine] Maximum recursion depth reached for CALL_SKILL: %s", self.id)
            return False

        if not self.enabled:
            logger.warning("[ExportEngine] Skill '%s' is disabled.", self.id)
            return False

        logger.info("[*] Executing RPA skill '%s' (%d steps)...", self.name, len(self.steps))
        step_idx = 0
        step_map = {str(s.get("id")): idx for idx, s in enumerate(self.steps) if s.get("id")}
        total_steps = len(self.steps)

        while step_idx < len(self.steps):
            step = self.steps[step_idx]
            step_id = step.get("id", f"step_{step_idx}")
            action_type = step.get("action_type", "NONE")
            desc = step.get("description", action_type)

            if not self._wait_for_queue(reporter, f"Paused before Step {step_idx + 1}/{total_steps}: {desc}"):
                logger.info("[ExportEngine] Execution stopped by user request.")
                return False

            if reporter:
                pct = round((step_idx / max(total_steps, 1)) * 100, 1)
                reporter(
                    TaskProgress(
                        current=step_idx + 1,
                        total=total_steps,
                        message=f"Step {step_idx + 1}/{total_steps}: {desc}",
                        percent=pct,
                    )
                )

            logger.info("  [Step %d/%d] %s: %s", step_idx + 1, total_steps, step_id, desc)

            # 1. FOCUS_WINDOW
            if action_type == "FOCUS_WINDOW":
                win_pattern = self._substitute_placeholders(step.get("window_title", self.target_window or ""), context)
                max_retries = int(step.get("max_retries", 5))
                retry_delay_s = float(step.get("retry_delay_s", 1.0))
                screen = None
                for attempt in range(1, max_retries + 1):
                    screen = SoMGrounder.capture_screen(win_pattern)
                    if screen is not None:
                        break
                    if attempt < max_retries:
                        time.sleep(retry_delay_s)
                if screen is None and win_pattern:
                    logger.warning(
                        "[ExportEngine] Window '%s' could not be found or focused in step '%s'.",
                        win_pattern,
                        step_id,
                    )

            # 2. CLICK / DOUBLE_CLICK / RIGHT_CLICK
            elif action_type in ("CLICK", "DOUBLE_CLICK", "RIGHT_CLICK"):
                locator = step.get("locator", {})
                win = self._substitute_placeholders(step.get("window_title", self.target_window or ""), context)
                max_retries = int(step.get("max_retries", 1))
                retry_delay_s = float(step.get("retry_delay_s", 1.0))
                coords = None
                for attempt in range(1, max_retries + 1):
                    coords = self._locate_target(locator, win)
                    if coords is not None:
                        break
                    if attempt < max_retries:
                        time.sleep(retry_delay_s)

                if coords is None:
                    logger.error("  [!] Target not found for action %s: %s", action_type, locator)
                    self._save_failure_screenshot(step_id, desc, win)
                    return False

                with input_shield():
                    if sys.platform == "win32":
                        ctypes.windll.user32.SetCursorPos(coords[0], coords[1])
                        if action_type == "CLICK":
                            ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
                            ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)
                        elif action_type == "DOUBLE_CLICK":
                            ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
                            ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)
                            time.sleep(0.05)
                            ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
                            ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)
                        elif action_type == "RIGHT_CLICK":
                            ctypes.windll.user32.mouse_event(0x0008, 0, 0, 0, 0)
                            ctypes.windll.user32.mouse_event(0x0010, 0, 0, 0, 0)

            # 3. TYPE_TEXT
            elif action_type == "TYPE_TEXT":
                raw_text = str(step.get("text", ""))
                text_to_type = self._substitute_placeholders(raw_text, context)
                press_enter = bool(step.get("press_enter", False))
                with input_shield():
                    _type_unicode_text(text_to_type, press_enter=press_enter)

            # 4. TYPE_FILE_PATH
            elif action_type == "TYPE_FILE_PATH":
                raw_path = str(step.get("file_path", context.get("document_fullpath", "")))
                sub_path = self._substitute_placeholders(raw_path, context)
                final_path = os.path.abspath(sub_path)
                if self.rdp_prefix and final_path.startswith("C:"):
                    final_path = self.rdp_prefix + final_path[2:]

                press_enter = bool(step.get("press_enter", True))
                with input_shield():
                    _type_unicode_text(final_path, press_enter=press_enter)

            # 5. VERIFY_SCREEN (Conditional Branching)
            elif action_type == "VERIFY_SCREEN":
                locator = step.get("locator", {})
                win = self._substitute_placeholders(step.get("window_title", self.target_window or ""), context)
                max_retries = int(step.get("max_retries", 1))
                retry_delay_s = float(step.get("retry_delay_s", 1.0))
                coords = None
                for attempt in range(1, max_retries + 1):
                    coords = self._locate_target(locator, win)
                    if coords is not None:
                        break
                    if attempt < max_retries:
                        time.sleep(retry_delay_s)
                success = coords is not None

                if success:
                    on_succ = step.get("on_success", "continue")
                    if on_succ == "stop_success":
                        return True
                    elif on_succ in step_map:
                        step_idx = step_map[on_succ]
                        continue
                else:
                    on_fail = step.get("on_failure", "stop")
                    on_fail_action = step.get("on_failure_action")
                    if on_fail_action == "run_skill" or on_fail == "run_skill":
                        sub_skill = str(step.get("on_failure_skill", ""))
                        if sub_skill:
                            self.execute_skill(sub_skill, context, depth=depth + 1)
                    elif on_fail == "stop" and not on_fail_action:
                        return False
                    elif on_fail == "continue" or on_fail_action == "continue":
                        pass
                    elif on_fail in step_map:
                        step_idx = step_map[on_fail]
                        continue

            # 6. CALL_SKILL
            elif action_type == "CALL_SKILL":
                sub_id = str(step.get("skill_id", ""))
                if sub_id:
                    if not self.execute_skill(sub_id, context, depth=depth + 1):
                        return False

            # 7. HOTKEY
            elif action_type == "HOTKEY":
                keys = step.get("keys", [])
                if isinstance(keys, str):
                    keys = [k.strip() for k in keys.split("+")]
                if keys and sys.platform == "win32":
                    with input_shield():
                        _vk_map: dict[str, int] = {
                            "ctrl": 0x11,
                            "control": 0x11,
                            "alt": 0x12,
                            "shift": 0x10,
                            "enter": 0x0D,
                            "return": 0x0D,
                            "tab": 0x09,
                            "esc": 0x1B,
                            "escape": 0x1B,
                            "space": 0x20,
                            "backspace": 0x08,
                            "f1": 0x70,
                            "f2": 0x71,
                            "f3": 0x72,
                            "f4": 0x73,
                            "f5": 0x74,
                            "f6": 0x75,
                            "f7": 0x76,
                            "f8": 0x77,
                            "f9": 0x78,
                            "f10": 0x79,
                            "f11": 0x7A,
                            "f12": 0x7B,
                        }
                        vk_list: list[int] = []
                        for k in keys:
                            k_lower = k.lower()
                            if k_lower in _vk_map:
                                vk_list.append(_vk_map[k_lower])
                            elif len(k) == 1:
                                vk_list.append(ord(k.upper()))

                        for vk in vk_list:
                            ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
                        time.sleep(0.05)
                        for vk in reversed(vk_list):
                            ctypes.windll.user32.keybd_event(vk, 0, 2, 0)

            # 8. SLEEP / DELAY
            elif action_type == "SLEEP":
                duration_s = float(step.get("duration_s", step.get("delay_ms", 1000) / 1000.0))
                time.sleep(duration_s)

            # Optional post-step delay
            delay_ms = int(step.get("delay_ms", 300))
            if delay_ms > 0:
                time.sleep(delay_ms / 1000.0)

            step_idx += 1

        if reporter:
            reporter(
                TaskProgress(
                    current=total_steps,
                    total=total_steps,
                    message=f"Completed {self.name}",
                    percent=100.0,
                )
            )

        return True

    def execute(
        self,
        task: SkillTask,
        reporter: Callable[[TaskProgress], None] | None = None,
    ) -> TaskResult:
        context = dict(task.context or {})
        folder_name = context.get("folder_name")
        folder_path = context.get("folder_path")

        from routes.state import DashboardState

        target_base = DashboardState.config.target_base_dir if DashboardState.config else "./Cases"

        try:
            if folder_path or folder_name:
                resolved_folder = (
                    str(folder_path) if folder_path else os.path.abspath(os.path.join(target_base, str(folder_name)))
                )
                success = self.execute_skill_for_folder(resolved_folder, context, reporter)
                return TaskResult(
                    success=success,
                    data={"folder_path": resolved_folder, "status": "completed" if success else "failed"},
                )
            else:
                # Batch execution: find all approved cases
                pending = self.find_pending_cases(target_base)
                if not pending:
                    if reporter:
                        reporter(
                            TaskProgress(
                                current=0,
                                total=0,
                                message="No pending approved cases found for export.",
                                percent=100.0,
                            )
                        )
                    return TaskResult(
                        success=True,
                        data={"pending_count": 0, "message": "No pending cases"},
                    )

                all_ok = True
                for idx, c in enumerate(pending, 1):
                    c_ctx = dict(c.get("parsed_metadata") or {})
                    c_ctx["folder_name"] = c["folder_name"]
                    c_ctx["folder_path"] = c["folder_path"]

                    if not self.execute_skill_for_folder(c["folder_path"], c_ctx, reporter):
                        all_ok = False

                return TaskResult(
                    success=all_ok,
                    data={"total_cases": len(pending), "status": "completed" if all_ok else "partial_failure"},
                )
        except Exception as e:
            logger.error("[ExportEngine] Execution error: %s", e, exc_info=True)
            return TaskResult(success=False, error=str(e))

    def filter_matching_files(self, folder_path: str, allowed_types: list[str] | None = None) -> list[dict[str, Any]]:
        """Filters PDF files in a case folder according to the skill's allowed document types and loads metadata."""
        matching_files: list[dict[str, Any]] = []
        if not os.path.exists(folder_path) or not os.path.isdir(folder_path):
            return matching_files

        if not allowed_types or "*" in allowed_types or "ALL" in [t.upper() for t in allowed_types]:
            allowed_types_clean = None
        else:
            allowed_types_clean = [t.strip().lower() for t in allowed_types if t.strip()]

        for fname in sorted(os.listdir(folder_path)):
            if fname.lower().endswith(".pdf"):
                full_path = os.path.join(folder_path, fname)
                meta_path = full_path + ".meta"
                doc_type = "UNKNOWN"
                meta_data: dict[str, Any] = {}

                if os.path.exists(meta_path):
                    try:
                        with open(meta_path, encoding="utf-8") as f:
                            loaded = json.load(f)
                            if isinstance(loaded, dict):
                                meta_data = loaded
                                doc_type = (
                                    loaded.get("Document")
                                    or loaded.get("Dokument")
                                    or loaded.get("document_type")
                                    or "UNKNOWN"
                                )
                    except (json.JSONDecodeError, OSError):
                        pass

                if doc_type == "UNKNOWN" and "__" in fname:
                    parts = fname.split("__")
                    if len(parts) >= 2:
                        doc_type = parts[0]

                if allowed_types_clean is None or doc_type.lower() in allowed_types_clean:
                    executed_skills = meta_data.get("executed_skills", [])
                    if not isinstance(executed_skills, list):
                        executed_skills = []
                    matching_files.append(
                        {
                            "filename": fname,
                            "fullpath": full_path,
                            "document_type": doc_type,
                            "meta": meta_data,
                            "executed_skills": executed_skills,
                        }
                    )

        return matching_files

    def find_pending_cases(self, target_base_dir: str) -> list[dict[str, Any]]:
        """Finds all approved case folders with unprocessed files."""
        if not os.path.exists(target_base_dir) or not self.enabled:
            return []

        allowed_types = self.definition.get("document_types", ["*"])
        pending_cases: list[dict[str, Any]] = []

        for folder_name in sorted(os.listdir(target_base_dir)):
            folder_path = os.path.join(target_base_dir, folder_name)
            if not os.path.isdir(folder_path):
                continue
            if not os.path.exists(os.path.join(folder_path, ".approved")):
                continue

            matching = self.filter_matching_files(folder_path, allowed_types)
            unprocessed_files = [f for f in matching if self.id not in f.get("executed_skills", [])]

            if unprocessed_files:
                # Parse folder name metadata
                parts = folder_name.split("__")
                parsed_meta: dict[str, str] = {}
                if len(parts) >= 4:
                    parsed_meta["Datum"] = parts[0]
                    parsed_meta["Dokument"] = parts[1]
                    parsed_meta["Empfaenger"] = parts[2]
                    parsed_meta["Person"] = parts[3]
                    if "," in parts[3]:
                        p_parts = parts[3].split(",", 1)
                        parsed_meta["Nachname"] = p_parts[0].strip()
                        parsed_meta["Vorname"] = p_parts[1].strip()
                    else:
                        parsed_meta["Nachname"] = parts[3].strip()

                pending_cases.append(
                    {
                        "folder_name": folder_name,
                        "folder_path": folder_path,
                        "matching_files": unprocessed_files,
                        "unprocessed_count": len(unprocessed_files),
                        "parsed_metadata": parsed_meta,
                    }
                )

        return pending_cases

    def execute_skill_for_folder(
        self,
        folder_path: str,
        context: dict[str, Any] | None = None,
        reporter: Callable[[TaskProgress], None] | None = None,
    ) -> bool:
        """Executes the export steps for an approved folder and marks files as executed."""
        allowed_types = self.definition.get("document_types", ["*"])
        all_matching = self.filter_matching_files(folder_path, allowed_types)
        matching_files = [f for f in all_matching if self.id not in f.get("executed_skills", [])]

        if not matching_files:
            return True

        base_ctx = dict(context or {})
        base_ctx["folder_path"] = folder_path
        base_ctx["matching_files"] = [f["fullpath"] for f in matching_files]

        primary_file = matching_files[0]
        for k, v in primary_file.get("meta", {}).items():
            if k not in base_ctx:
                base_ctx[k] = v

        base_ctx["document_fullpath"] = primary_file["fullpath"]
        base_ctx["document_type"] = primary_file["document_type"]
        base_ctx["filename"] = primary_file["filename"]

        if self.execute_steps(base_ctx, reporter=reporter):
            self.mark_file_executed(primary_file["fullpath"])
            return True
        return False

    def mark_file_executed(self, filepath: str) -> bool:
        """Updates the .meta sidecar file with this skill ID."""
        meta_path = filepath + ".meta"
        data: dict[str, Any] = {}
        if os.path.exists(meta_path):
            try:
                with open(meta_path, encoding="utf-8") as f:
                    data = json.load(f) or {}
            except (json.JSONDecodeError, OSError):
                data = {}

        executed = data.get("executed_skills", [])
        if not isinstance(executed, list):
            executed = []
        if self.id not in executed:
            executed.append(self.id)
        data["executed_skills"] = executed

        history = data.get("skill_execution_history", {})
        if not isinstance(history, dict):
            history = {}
        history[self.id] = time.time()
        data["skill_execution_history"] = history

        try:
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info("[ExportEngine] Marked '%s' as executed by '%s'", filepath, self.id)
            return True
        except OSError as e:
            logger.error("[ExportEngine] Failed writing marker to %s: %s", meta_path, e)
            return False

    def execute_skill(self, skill_id: str, context: dict[str, Any] | None = None, depth: int = 0) -> bool:
        """Executes a skill by ID using the appropriate engine."""
        if depth > 5:
            return False
        if not self.skill_manager:
            return False
        skill_def = self.skill_manager.get_skill(skill_id)
        if not skill_def or not skill_def.get("enabled", True):
            return False

        orig_steps = self.steps
        orig_window = self.target_window
        orig_rdp = self.rdp_prefix
        orig_id = self.id
        orig_name = self.name
        try:
            self.id = str(skill_def.get("id", skill_id))
            self.name = str(skill_def.get("name", self.id))
            raw_s = skill_def.get("steps")
            self.steps = [s for s in raw_s if isinstance(s, dict)] if isinstance(raw_s, list) else []
            self.target_window = skill_def.get("target_window")
            self.rdp_prefix = skill_def.get("rdp_path_prefix", "")
            return self.execute_steps(context or {}, depth=depth)
        finally:
            self.steps = orig_steps
            self.target_window = orig_window
            self.rdp_prefix = orig_rdp
            self.id = orig_id
            self.name = orig_name

    def find_pending_cases_for_skill(self, skill_id: str, target_base_dir: str) -> list[dict[str, Any]]:
        """Finds pending cases for any skill ID."""
        if self.id == skill_id:
            return self.find_pending_cases(target_base_dir)
        if self.skill_manager:
            engine = self.skill_manager.get_skill_engine(skill_id, self.vision_extractor)
            if isinstance(engine, ExportEngine):
                return engine.find_pending_cases(target_base_dir)
        return []

    def mark_file_skill_executed(self, filepath: str, skill_id: str) -> bool:
        """Marks a file with any specified skill ID."""
        meta_path = filepath + ".meta"
        data: dict[str, Any] = {}
        if os.path.exists(meta_path):
            try:
                with open(meta_path, encoding="utf-8") as f:
                    data = json.load(f) or {}
            except (json.JSONDecodeError, OSError):
                data = {}

        executed = data.get("executed_skills", [])
        if not isinstance(executed, list):
            executed = []
        if skill_id not in executed:
            executed.append(skill_id)
        data["executed_skills"] = executed

        history = data.get("skill_execution_history", {})
        if not isinstance(history, dict):
            history = {}
        history[skill_id] = time.time()
        data["skill_execution_history"] = history

        try:
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except OSError as e:
            logger.debug("[ExportEngine] Could not write metadata sidecar %s: %s", meta_path, e)
            return False
