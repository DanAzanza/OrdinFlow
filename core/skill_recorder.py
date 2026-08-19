from __future__ import annotations

import ctypes
import logging
import re
import threading
import time
from typing import Any

from PIL import Image, ImageGrab

try:
    from pynput import keyboard, mouse  # type: ignore[import-untyped]

    PYNPUT_AVAILABLE = True
except Exception:
    PYNPUT_AVAILABLE = False
    keyboard = None  # type: ignore[assignment]
    mouse = None  # type: ignore[assignment]


logger = logging.getLogger(__name__)

try:
    from rapidocr_onnxruntime import RapidOCR  # type: ignore[import-untyped]

    rapid_ocr = RapidOCR()
except Exception:
    rapid_ocr = None


def get_active_window_title() -> str:
    """Returns the window title of the currently active foreground window on Windows."""
    if hasattr(ctypes, "windll"):
        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()  # type: ignore[attr-defined]
            if hwnd:
                length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)  # type: ignore[attr-defined]
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)  # type: ignore[attr-defined]
                    return buff.value
        except (AttributeError, OSError, RuntimeError, ValueError):
            logger.debug("Unable to read active window title", exc_info=True)
    return "Remote Desktop*"


def ocr_snippet(image: Image.Image) -> str:
    """Performs quick OCR on a cropped PIL image snippet to extract element label."""
    if not rapid_ocr:
        return ""
    try:
        import numpy as np

        img_np = np.array(image.convert("RGB"))
        result, _ = rapid_ocr(img_np)
        if result:
            texts = [res[1] for res in result if res[1] and len(res[1].strip()) > 1]
            if texts:
                # Return longest or most meaningful text string
                return max(texts, key=len).strip()
    except (ValueError, TypeError, AttributeError, OSError):
        logger.debug("OCR snippet extraction failed", exc_info=True)
    return ""


class SkillRecorder:
    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self.is_recording: bool = False
        self.skill_name: str = "New Recorded Skill"
        self.skill_id: str = ""
        self.target_window: str = "Remote Desktop*"
        self.rdp_path_prefix: str = "\\\\tsclient\\C"
        self.document_types: list[str] = ["*"]
        self.upload_mode: str = "single_file"

        self.steps: list[dict[str, Any]] = []
        self.current_window: str = ""
        self.start_time: float = 0.0
        self.last_event_time: float = 0.0
        self.last_action_desc: str = "Ready"
        self.last_click_coords: tuple = (0, 0)

        self._keyboard_buffer: list[str] = []
        self._mouse_listener: Any | None = None
        self._keyboard_listener: Any | None = None

    @classmethod
    def get_instance(cls) -> SkillRecorder:
        with cls._lock:
            if cls._instance is None:
                cls._instance = SkillRecorder()
            return cls._instance

    def start_recording(self, skill_name: str = "New Recorded Skill") -> dict[str, Any]:
        with self._lock:
            if self.is_recording:
                return {"status": "already_recording", "step_count": len(self.steps)}

            if not PYNPUT_AVAILABLE:
                raise RuntimeError("The module 'pynput' is not installed.")

            self.is_recording = True
            self.skill_name = skill_name or "New Recorded Skill"
            self.skill_id = (
                "rdp_rec_" + re.sub(r"\W+", "_", self.skill_name.lower()).strip("_") + f"_{int(time.time())}"
            )
            self.steps = []
            self.current_window = ""
            self.start_time = time.time()
            self.last_action_desc = "Recording started..."
            self._keyboard_buffer = []

            # Initial active window check
            win = get_active_window_title()
            if win:
                self.current_window = win
                self.target_window = win
                self._add_step(
                    {
                        "id": f"step_{len(self.steps) + 1}",
                        "description": f"Focus window: {win}",
                        "action_type": "FOCUS_WINDOW",
                        "window_title": win,
                    }
                )

            # Start pynput listeners
            self._mouse_listener = mouse.Listener(on_click=self._on_mouse_click)  # type: ignore[union-attr]
            self._keyboard_listener = keyboard.Listener(on_press=self._on_key_press)  # type: ignore[union-attr]
            self._mouse_listener.start()
            self._keyboard_listener.start()

            return {
                "status": "recording_started",
                "skill_id": self.skill_id,
                "skill_name": self.skill_name,
            }

    def stop_recording(self) -> dict[str, Any]:
        with self._lock:
            if not self.is_recording:
                return self._synthesize_skill()

            self.is_recording = False
            self.last_action_desc = "Recording stopped."

            # Flush listeners
            if self._mouse_listener:
                try:
                    self._mouse_listener.stop()
                except (AttributeError, OSError, RuntimeError):
                    logger.debug("Stopping mouse listener failed", exc_info=True)
                self._mouse_listener = None

            if self._keyboard_listener:
                try:
                    self._keyboard_listener.stop()
                except (AttributeError, OSError, RuntimeError):
                    logger.debug("Stopping keyboard listener failed", exc_info=True)
                self._keyboard_listener = None

            self._flush_keyboard_buffer()
            return self._synthesize_skill()

    def get_status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "is_recording": self.is_recording,
                "skill_id": self.skill_id,
                "skill_name": self.skill_name,
                "step_count": len(self.steps) + (1 if self._keyboard_buffer else 0),
                "elapsed_seconds": round(time.time() - self.start_time, 1) if self.is_recording else 0.0,
                "last_action": self.last_action_desc,
            }

    def _flush_keyboard_buffer(self):
        if not self._keyboard_buffer:
            return
        typed_text = "".join(self._keyboard_buffer).strip()
        self._keyboard_buffer = []
        if typed_text:
            self._add_step(
                {
                    "id": f"step_{len(self.steps) + 1}",
                    "description": f"Type text: '{typed_text}'",
                    "action_type": "TYPE_TEXT",
                    "text": typed_text,
                }
            )
            self.last_action_desc = f"Captured text: '{typed_text}'"

    def _add_step(self, step: dict[str, Any]):
        step["id"] = f"step_{len(self.steps) + 1}"
        self.steps.append(step)

    def _on_mouse_click(self, x: int, y: int, button: Any, pressed: bool):
        if not self.is_recording or not pressed:
            return

        if button != mouse.Button.left:  # type: ignore[union-attr]
            return

        now = time.time()
        # Flush keyboard buffer before handling mouse click
        self._flush_keyboard_buffer()

        # Check window focus change
        active_win = get_active_window_title()
        if active_win and active_win != self.current_window:
            self.current_window = active_win
            self._add_step(
                {
                    "id": "step_tmp",
                    "description": f"Focus window: {active_win}",
                    "action_type": "FOCUS_WINDOW",
                    "window_title": active_win,
                }
            )

        # Check for double click (same position within 450ms)
        is_double_click = (
            (now - self.last_click_time < 0.45)
            and (abs(x - self.last_click_coords[0]) < 10)
            and (abs(y - self.last_click_coords[1]) < 10)
        )

        self.last_click_time = now
        self.last_click_coords = (x, y)

        if is_double_click and self.steps and self.steps[-1].get("action_type") == "CLICK":
            # Convert previous click to DOUBLE_CLICK
            self.steps[-1]["action_type"] = "DOUBLE_CLICK"
            self.steps[-1]["description"] = self.steps[-1]["description"].replace("Click", "Double click")
            self.last_action_desc = "Double click captured"
            return

        # Capture cropped screenshot around click for OCR
        ocr_text = ""
        try:
            crop_box = (max(0, x - 90), max(0, y - 25), x + 90, y + 25)
            snippet = ImageGrab.grab(bbox=crop_box)
            ocr_text = ocr_snippet(snippet)
        except (AttributeError, OSError, RuntimeError, ValueError):
            logger.debug("OCR capture during click failed", exc_info=True)

        if ocr_text:
            locator = {"type": "ocr_contains", "prompt": ocr_text}
            desc = f"Click on '{ocr_text}'"
        else:
            locator = {"type": "som_vlm", "prompt": f"Element at pos ({x}, {y})"}
            desc = f"Click at position ({x}, {y})"

        time_diff = now - (self.last_event_time or now)
        self.last_event_time = now
        calculated_delay = max(500, min(10000, int(time_diff * 1000))) if time_diff > 0.8 else 500

        self._add_step(
            {
                "id": "step_tmp",
                "description": desc,
                "action_type": "CLICK",
                "locator": locator,
                "delay_ms": calculated_delay,
            }
        )
        self.last_action_desc = desc

    def _on_key_press(self, key: Any):
        if not self.is_recording:
            return

        try:
            if hasattr(key, "char") and key.char:
                self._keyboard_buffer.append(key.char)
            elif key == keyboard.Key.space:  # type: ignore[union-attr]
                self._keyboard_buffer.append(" ")
            elif key == keyboard.Key.backspace:  # type: ignore[union-attr]
                if self._keyboard_buffer:
                    self._keyboard_buffer.pop()
            elif key in (keyboard.Key.enter, keyboard.Key.tab):  # type: ignore[union-attr]
                self._flush_keyboard_buffer()
        except (AttributeError, ValueError):
            logger.debug("Keyboard event handling failed", exc_info=True)

    def _synthesize_skill(self) -> dict[str, Any]:
        """Cleans up and post-processes recorded steps into a complete Skill definition."""
        self._flush_keyboard_buffer()

        # Re-index steps
        cleaned_steps = []
        for idx, s in enumerate(self.steps):
            s_copy = dict(s)
            s_copy["id"] = f"step_{idx + 1}"
            cleaned_steps.append(s_copy)

        if not cleaned_steps:
            cleaned_steps = [
                {
                    "id": "step_1",
                    "description": "Focus window",
                    "action_type": "FOCUS_WINDOW",
                    "window_title": self.target_window or "Remote Desktop*",
                }
            ]

        skill_obj = {
            "id": self.skill_id or f"rdp_recorded_{int(time.time())}",
            "name": self.skill_name or "New Recorded Skill",
            "description": f"Automatically recorded workflow ({len(cleaned_steps)} steps).",
            "target_window": self.target_window or "Remote Desktop*",
            "rdp_path_prefix": self.rdp_path_prefix,
            "document_types": self.document_types,
            "upload_mode": self.upload_mode,
            "enabled": True,
            "steps": cleaned_steps,
        }
        return skill_obj
