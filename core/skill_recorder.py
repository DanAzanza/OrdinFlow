from __future__ import annotations

import ctypes
import logging
import re
import sys
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
    if sys.platform == "win32" and hasattr(ctypes, "windll"):
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


_MODIFIER_KEYS: dict[Any, str] = {}
if PYNPUT_AVAILABLE and keyboard is not None:
    _MODIFIER_KEYS = {
        keyboard.Key.ctrl: "ctrl",
        keyboard.Key.ctrl_l: "ctrl",
        keyboard.Key.ctrl_r: "ctrl",
        keyboard.Key.alt: "alt",
        keyboard.Key.alt_l: "alt",
        keyboard.Key.alt_r: "alt",
        keyboard.Key.shift: "shift",
        keyboard.Key.shift_l: "shift",
        keyboard.Key.shift_r: "shift",
        keyboard.Key.cmd: "win",
        keyboard.Key.cmd_l: "win",
        keyboard.Key.cmd_r: "win",
    }


def _get_modifier_name(key: Any) -> str | None:
    """Returns canonical modifier name ('ctrl', 'alt', 'shift', 'win') or None."""
    if key in _MODIFIER_KEYS:
        return _MODIFIER_KEYS[key]
    if hasattr(key, "name") and key.name:
        key_str = str(key.name).lower()
    elif isinstance(key, str):
        key_str = key.lower()
    else:
        return None

    if "alt_gr" in key_str:
        return None
    if "ctrl" in key_str or "control" in key_str:
        return "ctrl"
    if "alt" in key_str or "menu" in key_str:
        return "alt"
    if "shift" in key_str:
        return "shift"
    if "cmd" in key_str or "win" in key_str or "super" in key_str:
        return "win"
    return None


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

        self.steps: list[dict[str, Any]] = []
        self.current_window: str = ""
        self.start_time: float = 0.0
        self.last_event_time: float = 0.0
        self.last_click_time: float = 0.0
        self.last_action_desc: str = "Ready"
        self.last_click_coords: tuple[int, int] = (0, 0)

        self._keyboard_buffer: list[str] = []
        self._active_modifiers: set[str] = set()
        self._active_hotkey_keys: set[str] = set()
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

            if not PYNPUT_AVAILABLE or keyboard is None or mouse is None:
                raise RuntimeError("The module 'pynput' is not installed.")

            self.is_recording = True
            self.skill_name = skill_name or "New Recorded Skill"
            self.skill_id = (
                "rdp_rec_" + re.sub(r"\W+", "_", self.skill_name.lower()).strip("_") + f"_{int(time.time())}"
            )
            self.steps = []
            self.current_window = ""
            self.start_time = time.time()
            self.last_event_time = 0.0
            self.last_click_time = 0.0
            self.last_click_coords = (0, 0)
            self.last_action_desc = "Recording started..."
            self._keyboard_buffer = []
            self._active_modifiers = set()
            self._active_hotkey_keys = set()

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
            self._keyboard_listener = keyboard.Listener(
                on_press=self._on_key_press,
                on_release=self._on_key_release,
            )  # type: ignore[union-attr]
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
            self._active_modifiers.clear()
            self._active_hotkey_keys.clear()
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

    def _flush_keyboard_buffer(self, press_enter: bool = False):
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
                    "press_enter": press_enter,
                }
            )
            self.last_action_desc = f"Captured text: '{typed_text}'"

    def _add_step(self, step: dict[str, Any]):
        step["id"] = f"step_{len(self.steps) + 1}"
        self.steps.append(step)

    def _on_mouse_click(self, x: int, y: int, button: Any, pressed: bool):
        if not self.is_recording or not pressed:
            return

        if mouse is not None and button != mouse.Button.left:  # type: ignore[union-attr]
            return
        if mouse is None and button != "left":
            return

        with self._lock:
            try:
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
            except Exception as e:
                logger.error("[SkillRecorder] Error handling mouse click: %s", e, exc_info=True)

    def _on_key_release(self, key: Any) -> None:
        if not self.is_recording:
            return
        with self._lock:
            mod_name = _get_modifier_name(key)
            if mod_name:
                self._active_modifiers.discard(mod_name)
            if hasattr(key, "char") and key.char:
                char_val = key.char
                if 1 <= ord(char_val) <= 26:
                    char_val = chr(ord(char_val) + ord("a") - 1)
                self._active_hotkey_keys.discard(char_val.lower())
            elif hasattr(key, "name") and key.name:
                self._active_hotkey_keys.discard(key.name.lower())
            elif isinstance(key, str):
                self._active_hotkey_keys.discard(key.lower())

    def _on_key_press(self, key: Any) -> None:
        if not self.is_recording:
            return

        with self._lock:
            try:
                # 1. Track modifier keys
                mod_name = _get_modifier_name(key)
                if mod_name:
                    self._active_modifiers.add(mod_name)
                    return

                # 2. Check for AltGr on Windows
                is_altgr = getattr(key, "name", None) == "alt_gr"
                if is_altgr:
                    return

                # 3. Detect non-modifier key character and name
                char_val = ""
                key_name = ""
                if hasattr(key, "char") and key.char is not None:
                    # Windows control character normalization (\x01 - \x1a -> a - z)
                    if 1 <= ord(key.char) <= 26:
                        char_val = chr(ord(key.char) + ord("a") - 1)
                    else:
                        char_val = key.char
                elif hasattr(key, "name") and key.name:
                    key_name = key.name.lower()

                # 4. Check if this is an active hotkey combination (Ctrl, Alt, or Win active)
                ctrl_or_alt = bool(self._active_modifiers.intersection({"ctrl", "alt", "win"}))

                # Handle AltGr printable characters (e.g. @, \, ~, [, ], {, }, €) on QWERTZ / European layouts
                is_printable_altgr = (
                    ctrl_or_alt
                    and bool(char_val)
                    and ord(char_val) >= 32
                    and char_val not in "abcdefghijklmnopqrstuvwxyz"
                )

                if ctrl_or_alt and not is_printable_altgr:
                    target_key = char_val.lower() if char_val else key_name
                    if not target_key:
                        return

                    # Debounce auto-repeat
                    if target_key in self._active_hotkey_keys:
                        return
                    self._active_hotkey_keys.add(target_key)

                    # Flush buffer before recording hotkey
                    self._flush_keyboard_buffer()

                    # Build canonical keys list: [ctrl, alt, shift, win, <key>]
                    keys_list: list[str] = []
                    for mod in ("ctrl", "alt", "shift", "win"):
                        if mod in self._active_modifiers:
                            keys_list.append(mod)
                    if target_key not in keys_list:
                        keys_list.append(target_key)

                    desc = f"Press hotkey: {' + '.join(k.upper() for k in keys_list)}"
                    self._add_step(
                        {
                            "id": "step_tmp",
                            "description": desc,
                            "action_type": "HOTKEY",
                            "keys": keys_list,
                            "delay_ms": 500,
                        }
                    )
                    self.last_action_desc = desc
                    return

                # 5. Regular text entry handling
                if char_val:
                    self._keyboard_buffer.append(char_val)
                elif key == keyboard.Key.space:  # type: ignore[union-attr]
                    self._keyboard_buffer.append(" ")
                elif key == keyboard.Key.backspace:  # type: ignore[union-attr]
                    if self._keyboard_buffer:
                        self._keyboard_buffer.pop()
                elif keyboard is not None and key in (keyboard.Key.enter, keyboard.Key.tab):
                    self._flush_keyboard_buffer(press_enter=(key == keyboard.Key.enter))
            except Exception as e:
                logger.debug("Keyboard event handling failed: %s", e, exc_info=True)

    def _synthesize_skill(self) -> dict[str, Any]:
        """Cleans up and post-processes recorded steps into a complete Skill definition."""
        self._flush_keyboard_buffer()

        # Remove accidental stop recording button clicks on the OrdinFlow dashboard if recorded at the end
        if self.steps:
            last = self.steps[-1]
            last_desc = str(last.get("description", "")).lower()
            last_prompt = str((last.get("locator") or {}).get("prompt", "")).lower()
            if any(k in last_desc or k in last_prompt for k in ["stop", "aufnahme", "recorder"]):
                self.steps.pop()

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
            "description": f"Automatically recorded skill ({len(cleaned_steps)} actions).",
            "target_window": self.target_window or "Remote Desktop*",
            "rdp_path_prefix": self.rdp_path_prefix,
            "document_types": self.document_types,
            "enabled": True,
            "steps": cleaned_steps,
        }
        return skill_obj
