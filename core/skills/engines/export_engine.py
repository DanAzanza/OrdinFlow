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
from pathlib import Path
from typing import Any, cast

from core.skills.base import BaseSkill
from core.skills.grounder import SoMGrounder
from core.skills.models import SkillTask, TaskProgress, TaskResult
from core.skills.shield import input_shield
from core.utils import is_sensitive_credential_text, sanitize_safe_path

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


def _paste_text_via_clipboard(text: str, press_enter: bool = False) -> bool:
    """Instantly pastes text via Windows Clipboard (Ctrl+V), avoiding layout/character typing lags."""
    if sys.platform != "win32":
        _type_unicode_text(text, press_enter=press_enter)
        return True

    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        CF_UNICODETEXT = 13
        GMEM_MOVEABLE = 0x0002

        encoded = text.encode("utf-16le") + b"\x00\x00"

        h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(encoded))
        if not h_mem:
            _type_unicode_text(text, press_enter=press_enter)
            return False

        ptr = kernel32.GlobalLock(h_mem)
        if not ptr:
            kernel32.GlobalFree(h_mem)
            _type_unicode_text(text, press_enter=press_enter)
            return False

        ctypes.memmove(ptr, encoded, len(encoded))
        kernel32.GlobalUnlock(h_mem)

        if not user32.OpenClipboard(0):
            kernel32.GlobalFree(h_mem)
            _type_unicode_text(text, press_enter=press_enter)
            return False

        user32.EmptyClipboard()
        user32.SetClipboardData(CF_UNICODETEXT, h_mem)
        user32.CloseClipboard()

        # Send Ctrl+V
        KEYEVENTF_KEYUP = 0x0002
        VK_CONTROL = 0x11
        VK_V = 0x56

        user32.keybd_event(VK_CONTROL, 0, 0, 0)
        user32.keybd_event(VK_V, 0, 0, 0)
        time.sleep(0.03)
        user32.keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0)
        user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)

        if press_enter:
            time.sleep(0.05)
            user32.keybd_event(0x0D, 0, 0, 0)
            user32.keybd_event(0x0D, 0, KEYEVENTF_KEYUP, 0)

        return True
    except Exception as e:
        logger.debug("[ExportEngine] Clipboard paste failed, falling back to keystrokes: %s", e)
        _type_unicode_text(text, press_enter=press_enter)
        return False



def _apply_string_modifier(val: str, modifier: str) -> str:
    """Applies string formatting modifiers to placeholder values."""
    mod = modifier.strip().lower()
    if not val:
        return ""

    if mod == "upper":
        return val.upper()
    if mod == "lower":
        return val.lower()
    if mod == "capitalize":
        return val.capitalize()
    if mod == "title":
        return val.title()
    if mod in ("nodots", "digits_only"):
        return re.sub(r"\D", "", val)
    if mod in ("slug", "clean_filename"):
        s = val.replace("ä", "ae").replace("Ä", "Ae")
        s = s.replace("ö", "oe").replace("Ö", "Oe")
        s = s.replace("ü", "ue").replace("Ü", "Ue")
        s = s.replace("ß", "ss")
        return re.sub(r"[^a-zA-Z0-9_-]", "_", s)
    if mod == "filename":
        return Path(val).name
    if mod in ("basename", "stem"):
        return Path(val).stem
    if mod in ("ext", "extension"):
        return Path(val).suffix
    if mod in ("parent", "folder"):
        return str(Path(val).parent)
    if mod.startswith("format:"):
        fmt = modifier.strip()[7:]
        clean_d = val.strip().replace("/", ".").replace("-", ".")
        parts = clean_d.split(".")
        try:
            if len(parts) == 3:
                if len(parts[0]) == 4:  # YYYY.MM.DD
                    y, m, d = parts[0], parts[1].zfill(2), parts[2].zfill(2)
                else:  # DD.MM.YYYY
                    d, m, y = parts[0].zfill(2), parts[1].zfill(2), parts[2]
                if fmt == "YYYYMMDD":
                    return f"{y}{m}{d}"
                if fmt == "DDMMYYYY":
                    return f"{d}{m}{y}"
                if fmt == "DD.MM.YYYY":
                    return f"{d}.{m}.{y}"
                if fmt == "DD-MM-YYYY":
                    return f"{d}-{m}-{y}"
                if fmt == "YYYY-MM-DD":
                    return f"{y}-{m}-{d}"
                if fmt == "DD.MM.YY":
                    return f"{d}.{m}.{y[-2:]}"
        except Exception:
            pass

    return val


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
        raw_tasks = definition.get("tasks")
        raw_steps = definition.get("steps")

        actions: list[dict[str, Any]] = []
        if isinstance(raw_tasks, list) and raw_tasks:
            for t in raw_tasks:
                if isinstance(t, dict):
                    t_actions = t.get("actions", [])
                    if isinstance(t_actions, list):
                        for a in t_actions:
                            if isinstance(a, dict):
                                actions.append(a)
        elif isinstance(raw_steps, list):
            actions = [s for s in raw_steps if isinstance(s, dict)]

        self.steps: list[dict[str, Any]] = actions
        self.actions: list[dict[str, Any]] = actions
        self.tasks: list[dict[str, Any]] = [t for t in raw_tasks if isinstance(t, dict)] if isinstance(raw_tasks, list) else []
        self.target_window = definition.get("target_window")
        if not self.target_window:
            for s in self.steps:
                if s.get("action_type") == "FOCUS_WINDOW" and s.get("window_title"):
                    self.target_window = s.get("window_title")
                    break
        self.rdp_prefix = definition.get("rdp_path_prefix", "")
        self.launch_skill_id = definition.get("launch_skill_id", "")
        self.executable_path = definition.get("executable_path", "")
        self.maximize_window = bool(definition.get("maximize_window", False))
        self.recover_hung_process = bool(definition.get("recover_hung_process", False))

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
        """Dynamically substitutes placeholders with optional modifiers (e.g. {Nachname|upper})."""
        if not isinstance(text, str) or "{" not in text:
            return text

        # Derived dynamic properties from document_fullpath
        fullpath = str(context.get("document_fullpath", "") or "")
        derived = dict(context)

        # Derive path-related variables
        if fullpath:
            p = Path(fullpath)
            derived.setdefault("document_filename", p.name)
            derived.setdefault("filename", p.name)
            derived.setdefault("document_basename", p.stem)
            derived.setdefault("basename", p.stem)
            derived.setdefault("document_extension", p.suffix)
            derived.setdefault("extension", p.suffix)
            derived.setdefault("document_parent", str(p.parent))
            derived.setdefault("case_folder", str(p.parent))
            derived.setdefault("target_folder", str(p.parent))

        # Derive dynamic datetime variables if not provided
        now = time.localtime()
        derived.setdefault("Datum", time.strftime("%Y-%m-%d", now))
        derived.setdefault("date", time.strftime("%Y-%m-%d", now))
        derived.setdefault("Jahr", time.strftime("%Y", now))
        derived.setdefault("year", time.strftime("%Y", now))
        derived.setdefault("Monat", time.strftime("%m", now))
        derived.setdefault("month", time.strftime("%m", now))
        derived.setdefault("Tag", time.strftime("%d", now))
        derived.setdefault("day", time.strftime("%d", now))
        derived.setdefault("Zeit", time.strftime("%H-%M-%S", now))
        derived.setdefault("time", time.strftime("%H-%M-%S", now))

        def replace_match(match: re.Match) -> str:
            raw_expr = match.group(1).strip()
            if "|" in raw_expr:
                parts = raw_expr.split("|", 1)
                key = parts[0].strip()
                modifier = parts[1].strip()
            else:
                key = raw_expr
                modifier = ""

            val = derived.get(key)
            str_val = str(val) if val is not None else ""
            if modifier:
                return _apply_string_modifier(str_val, modifier)
            return str_val

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

        # 2. Set-of-Mark (SoM) Grounding via VLM with High-Res Quadrant Tiling
        if (loc_type in ("auto", "smart", "som_vlm")) and self.vision_extractor and search_term:
            tiles = SoMGrounder.generate_quadrant_tiles(screen)
            for tile_img, off_x, off_y in tiles:
                som_img, candidates = SoMGrounder.generate_som_overlay(tile_img)
                if not candidates:
                    continue

                buf = BytesIO()
                som_img.save(buf, format="JPEG", quality=85)
                b64_som = base64.b64encode(buf.getvalue()).decode("utf-8")

                ground_prompt = (
                    f"Interactive UI elements are marked with red badges `[1]`, `[2]`, ... in this image.\n"
                    f"Which element number best matches: '{search_term}'?\n"
                    f"Reply ONLY with the exact number in square brackets, e.g. `[14]`. If no element matches, reply `NONE`."
                )
                payload = {"messages": [{"role": "user", "content": ground_prompt, "images": [b64_som]}]}

                resp = self.vision_extractor.call_vision_api(payload)
                if resp and "NONE" not in resp:
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
                            local_cx = int(raw_cx) if isinstance(raw_cx, (int, float)) else 0
                            local_cy = int(raw_cy) if isinstance(raw_cy, (int, float)) else 0
                            return off_x + local_cx + offset_x, off_y + local_cy + offset_y

        logger.warning("[ExportEngine] Locator could not be resolved: %s", locator)
        return None

    def _handle_known_dialog_popups(self, window_title: str | None = None) -> bool:
        """Inspects whether an unexpected overwrite/confirmation modal popup is blocking the flow and resolves it."""
        try:
            from core.extraction_pipeline import _get_rapid_ocr

            engine = _get_rapid_ocr()
            if not engine:
                return False
            screen = SoMGrounder.capture_screen(window_title)
            if not screen:
                return False
            img_np = np.array(screen) if np is not None else None
            if img_np is None:
                return False
            res, _ = engine(img_np)
            if not res:
                return False

            popup_detected = False
            confirm_btn_coords = None
            for line in res:
                box, text, _ = line
                t_lower = text.lower().strip()
                if any(k in t_lower for k in ["überschreiben", "bereits vorhanden", "already exists", "ersetzen", "replace"]):
                    popup_detected = True
                if t_lower in ["ja", "yes", "überschreiben", "replace", "ok", "fortfahren"]:
                    xs = [float(p[0]) for p in box]
                    ys = [float(p[1]) for p in box]
                    confirm_btn_coords = (int(sum(xs) / len(xs)), int(sum(ys) / len(ys)))

            if popup_detected and confirm_btn_coords and sys.platform == "win32":
                logger.info("[ExportEngine] Auto-Recovery: Detected confirmation/overwrite modal popup, clicking confirm at %s", confirm_btn_coords)
                with input_shield():
                    ctypes.windll.user32.SetCursorPos(confirm_btn_coords[0], confirm_btn_coords[1])
                    ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
                    ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)
                time.sleep(0.3)
                return True
        except Exception as e:
            logger.debug("[ExportEngine] Dialog auto-recovery check error: %s", e)
        return False

    def _maximize_window(self, win_pattern: str) -> None:
        """Maximizes the target window via Win32 ShowWindow(SW_MAXIMIZE = 3)."""
        if sys.platform != "win32" or not win_pattern:
            return
        try:
            found_hwnd: list[int] = []

            def enum_proc(h: int, _lparam: int) -> bool:
                length = ctypes.windll.user32.GetWindowTextLengthW(h)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    ctypes.windll.user32.GetWindowTextW(h, buff, length + 1)
                    if win_pattern.lower().replace("*", "") in buff.value.lower():
                        found_hwnd.append(h)
                return True

            cb = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)(enum_proc)
            ctypes.windll.user32.EnumWindows(cb, 0)
            if found_hwnd:
                ctypes.windll.user32.ShowWindow(found_hwnd[0], 3)  # SW_MAXIMIZE
                time.sleep(0.2)
        except Exception as e:
            logger.debug("[ExportEngine] Maximize window error: %s", e)

    def _ensure_window_ready(
        self,
        win_pattern: str,
        context: Mapping[str, Any],
        launch_skill_id: str = "",
        exe_path: str = "",
        maximize: bool = False,
    ) -> bool:
        """Checks if target window is available; if not, triggers launch skill or executable and maximizes."""
        screen = SoMGrounder.capture_screen(win_pattern) if win_pattern else None
        if screen is not None:
            if maximize and sys.platform == "win32":
                self._maximize_window(win_pattern)
            return True

        # Window not found -> try launch skill or executable
        launch_skill = launch_skill_id or self.launch_skill_id
        executable = exe_path or self.executable_path

        if launch_skill:
            logger.info("[ExportEngine] Window '%s' not found. Triggering launch skill: '%s'", win_pattern, launch_skill)
            if not self.execute_skill(str(launch_skill), dict(context)):
                logger.warning("[ExportEngine] Launch skill '%s' failed.", launch_skill)
                return False
        elif executable:
            logger.info("[ExportEngine] Window '%s' not found. Launching executable: '%s'", win_pattern, executable)
            try:
                import subprocess

                subprocess.Popen(str(executable), shell=True)
            except Exception as e:
                logger.error("[ExportEngine] Failed to launch executable '%s': %s", executable, e)
                return False

        # Wait up to 10s for the window to appear
        for _ in range(20):
            time.sleep(0.5)
            screen = SoMGrounder.capture_screen(win_pattern)
            if screen is not None:
                if maximize and sys.platform == "win32":
                    self._maximize_window(win_pattern)
                return True

        return False

    def _check_hung_app_and_recover(self, win_pattern: str, context: Mapping[str, Any]) -> bool:
        """Checks if target window is hung/unresponsive and restarts it if configured."""
        if sys.platform != "win32" or not win_pattern or not self.recover_hung_process:
            return False
        try:
            found_hwnd: list[int] = []

            def enum_proc(h: int, _lparam: int) -> bool:
                length = ctypes.windll.user32.GetWindowTextLengthW(h)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    ctypes.windll.user32.GetWindowTextW(h, buff, length + 1)
                    if win_pattern.lower().replace("*", "") in buff.value.lower():
                        found_hwnd.append(h)
                return True

            cb = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)(enum_proc)
            ctypes.windll.user32.EnumWindows(cb, 0)
            if found_hwnd:
                hwnd = found_hwnd[0]
                is_hung = bool(ctypes.windll.user32.IsHungAppWindow(hwnd))
                if is_hung:
                    logger.warning("[ExportEngine] Detected hung/unresponsive window '%s' (HWND %s). Terminating process...", win_pattern, hwnd)
                    pid = ctypes.c_ulong()
                    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    if pid.value:
                        import subprocess

                        subprocess.run(["taskkill", "/F", "/PID", str(pid.value)], check=False, capture_output=True)
                        time.sleep(1.0)
                        return self._ensure_window_ready(win_pattern, context, maximize=True)
        except Exception as e:
            logger.debug("[ExportEngine] Hung app check error: %s", e)
        return False

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

    def execute_actions(
        self,
        context: dict[str, Any],
        reporter: Callable[[TaskProgress], None] | None = None,
        depth: int = 0,
    ) -> bool:
        """Executes the defined actions sequentially with input shield protection."""
        if depth > 5:
            logger.error("[ExportEngine] Maximum recursion depth reached for CALL_SKILL: %s", self.id)
            return False

        if not self.enabled:
            logger.warning("[ExportEngine] Skill '%s' is disabled.", self.id)
            return False

        actions = self.actions or self.steps
        logger.info("[*] Executing RPA skill '%s' (%d actions)...", self.name, len(actions))
        act_idx = 0
        step_map = {str(s.get("id")): idx for idx, s in enumerate(actions) if s.get("id")}
        total_actions = len(actions)

        while act_idx < len(actions):
            step = actions[act_idx]
            step_id = step.get("id", f"act_{act_idx}")
            action_type = step.get("action_type", "NONE")
            desc = step.get("description", action_type)

            if not self._wait_for_queue(reporter, f"Paused before Action {act_idx + 1}/{total_actions}: {desc}"):
                logger.info("[ExportEngine] Execution stopped by user request.")
                return False

            if reporter:
                pct = round((act_idx / max(total_actions, 1)) * 100, 1)
                reporter(
                    TaskProgress(
                        current=act_idx + 1,
                        total=total_actions,
                        message=f"Action {act_idx + 1}/{total_actions}: {desc}",
                        percent=pct,
                    )
                )

            logger.info("  [Action %d/%d] %s: %s", act_idx + 1, total_actions, step_id, desc)

            # 1. FOCUS_WINDOW
            if action_type == "FOCUS_WINDOW":
                win_pattern = self._substitute_placeholders(step.get("window_title", self.target_window or ""), context)
                launch_skill = str(step.get("launch_skill_id") or self.launch_skill_id or "")
                exe_path = str(step.get("executable_path") or self.executable_path or "")
                maximize = bool(step.get("maximize_window", self.maximize_window))

                ready = self._ensure_window_ready(
                    win_pattern=win_pattern,
                    context=context,
                    launch_skill_id=launch_skill,
                    exe_path=exe_path,
                    maximize=maximize,
                )
                if not ready and win_pattern:
                    logger.warning(
                        "[ExportEngine] Window '%s' could not be found or launched in step '%s'.",
                        win_pattern,
                        step_id,
                    )

            # 2. CLICK / DOUBLE_CLICK / RIGHT_CLICK
            elif action_type in ("CLICK", "DOUBLE_CLICK", "RIGHT_CLICK"):
                locator = step.get("locator", {})
                win = self._substitute_placeholders(step.get("window_title", self.target_window or ""), context)
                max_retries = max(int(step.get("max_retries", 3)), 1)
                retry_delay_s = float(step.get("retry_delay_s", 0.35))
                coords = None
                for attempt in range(1, max_retries + 1):
                    coords = self._locate_target(locator, win)
                    if coords is not None:
                        break
                    # Attempt auto-dialog resolution if modal is blocking
                    self._handle_known_dialog_popups(win)
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
                is_secret = bool(step.get("is_secret", False)) or is_sensitive_credential_text(raw_text, step.get("description", ""))
                if is_secret:
                    logger.info("  [Action %s] TYPE_TEXT: [PROTECTED SENSITIVE CREDENTIAL MASKED]", step_id)
                with input_shield():
                    _type_unicode_text(text_to_type, press_enter=press_enter)

            # 4. TYPE_FILE_PATH (Instant Clipboard Paste + Security Gate)
            elif action_type == "TYPE_FILE_PATH":
                raw_path = str(step.get("file_path", context.get("document_fullpath", "")))
                sub_path = self._substitute_placeholders(raw_path, context)
                is_safe, clean_path = sanitize_safe_path(sub_path)
                if not is_safe:
                    logger.error("[Security] Aborted TYPE_FILE_PATH due to directory traversal pattern: %r", sub_path)
                    self._save_failure_screenshot(step_id, f"Security Block: {sub_path}", self.target_window)
                    return False

                final_path = os.path.abspath(clean_path)
                if self.rdp_prefix and final_path.startswith("C:"):
                    final_path = self.rdp_prefix + final_path[2:]

                press_enter = bool(step.get("press_enter", True))
                with input_shield():
                    _paste_text_via_clipboard(final_path, press_enter=press_enter)

            # 5. WAIT_FOR_ELEMENT (Dynamic Waiting / Smart Polling)
            elif action_type == "WAIT_FOR_ELEMENT":
                locator = step.get("locator", {})
                win = self._substitute_placeholders(step.get("window_title", self.target_window or ""), context)
                timeout_s = float(step.get("timeout_s", step.get("duration_s", 5.0)))
                poll_interval_s = float(step.get("poll_interval_s", 0.25))
                start_t = time.time()
                found = False
                while (time.time() - start_t) <= timeout_s:
                    coords = self._locate_target(locator, win)
                    if coords is not None:
                        found = True
                        break
                    self._handle_known_dialog_popups(win)
                    time.sleep(poll_interval_s)

                if not found:
                    logger.warning("[ExportEngine] WAIT_FOR_ELEMENT timed out after %.1fs for %s", timeout_s, locator)
                    on_fail = step.get("on_failure", "stop")
                    if on_fail == "stop":
                        self._save_failure_screenshot(step_id, f"Wait Timeout: {locator}", win)
                        return False

            # 6. VERIFY_SCREEN (Conditional Branching)
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
                        act_idx = step_map[on_succ]
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
                        act_idx = step_map[on_fail]
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

            act_idx += 1

        if reporter:
            reporter(
                TaskProgress(
                    current=total_actions,
                    total=total_actions,
                    message=f"Completed {self.name}",
                    percent=100.0,
                )
            )

        return True

    execute_steps = execute_actions

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
                # Dynamically parse folder name metadata
                parts = folder_name.split("__")
                parsed_meta: dict[str, str] = {}
                folder_struct = []
                if self.skill_manager and hasattr(self.skill_manager, "config") and self.skill_manager.config:
                    folder_struct = getattr(self.skill_manager.config, "folder_structure", [])

                if folder_struct and isinstance(folder_struct, list):
                    for idx, key in enumerate(folder_struct):
                        if idx < len(parts):
                            parsed_meta[key] = parts[idx].strip()
                else:
                    for idx, part in enumerate(parts):
                        parsed_meta[f"part_{idx}"] = part.strip()

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
        orig_actions = self.actions
        orig_window = self.target_window
        orig_rdp = self.rdp_prefix
        orig_id = self.id
        orig_name = self.name
        try:
            self.id = str(skill_def.get("id", skill_id))
            self.name = str(skill_def.get("name", self.id))
            raw_tasks = skill_def.get("tasks")
            raw_steps = skill_def.get("steps")
            actions: list[dict[str, Any]] = []
            if isinstance(raw_tasks, list) and raw_tasks:
                for t in raw_tasks:
                    if isinstance(t, dict):
                        t_actions = t.get("actions", [])
                        if isinstance(t_actions, list):
                            for a in t_actions:
                                if isinstance(a, dict):
                                    actions.append(a)
            elif isinstance(raw_steps, list):
                actions = [s for s in raw_steps if isinstance(s, dict)]
            self.steps = actions
            self.actions = actions
            self.target_window = skill_def.get("target_window")
            self.rdp_prefix = skill_def.get("rdp_path_prefix", "")
            return self.execute_actions(context or {}, depth=depth)
        finally:
            self.steps = orig_steps
            self.actions = orig_actions
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
