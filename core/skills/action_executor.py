"""Desktop Input and Window Action Executors for OrdinFlow RPA Skills.

Dispatches concrete UI interaction primitives: Focus Window, Mouse Clicks,
Unicode Typing, File Path Pasting, and Smart Element Waiting.
"""

from __future__ import annotations

import ctypes
import logging
import os
import re
import sys
import time
from collections.abc import Callable, Mapping
from typing import Any

from core.skills.shield import input_shield
from core.skills.text_helpers import paste_text_via_clipboard, type_unicode_text
from core.skills.window_manager import ensure_window_ready, handle_known_dialog_popups, save_failure_screenshot
from core.utils import is_sensitive_credential_text, sanitize_safe_path

logger = logging.getLogger(__name__)


def execute_focus_window(
    step: Mapping[str, Any],
    context: Mapping[str, Any],
    default_target_window: str | None,
    launch_skill_id: str,
    executable_path: str,
    default_maximize: bool,
    substitute_fn: Callable[[str, Mapping[str, Any]], str],
    execute_skill_fn: Callable[..., bool],
    is_cancelled_fn: Callable[[], bool],
) -> bool:
    """Activates and readies the target application window."""
    win_pattern = substitute_fn(str(step.get("window_title") or default_target_window or ""), context)
    launch_skill = str(step.get("launch_skill_id") or launch_skill_id or "")
    exe_path = str(step.get("executable_path") or executable_path or "")
    maximize = bool(step.get("maximize_window", default_maximize))

    ready = ensure_window_ready(
        win_pattern=win_pattern,
        context=context,
        launch_skill_id=launch_skill,
        exe_path=exe_path,
        maximize=maximize,
        execute_skill_fn=execute_skill_fn,
        is_cancelled_fn=is_cancelled_fn,
    )
    if not ready and win_pattern:
        logger.warning("[ActionExecutor] Window '%s' could not be found or launched.", win_pattern)
    return ready


def send_native_click(x: int, y: int, button: str = "left", double: bool = False) -> bool:
    """Dispatches physical mouse clicks to Windows OS desktop coordinates with 64-bit safety."""
    if sys.platform != "win32":
        return False
    try:
        u32 = ctypes.windll.user32
        u32.SetCursorPos(int(x), int(y))
        if button == "right":
            u32.mouse_event(0x0008, 0, 0, 0, 0)
            u32.mouse_event(0x0010, 0, 0, 0, 0)
        elif double:
            u32.mouse_event(0x0002, 0, 0, 0, 0)
            u32.mouse_event(0x0004, 0, 0, 0, 0)
            time.sleep(0.05)
            u32.mouse_event(0x0002, 0, 0, 0, 0)
            u32.mouse_event(0x0004, 0, 0, 0, 0)
        else:
            u32.mouse_event(0x0002, 0, 0, 0, 0)
            u32.mouse_event(0x0004, 0, 0, 0, 0)
        return True
    except Exception as e:
        logger.debug("[ActionExecutor] send_native_click error: %s", e)
        return False


def execute_mouse_click(
    step: Mapping[str, Any],
    step_id: str,
    action_type: str,
    context: Mapping[str, Any],
    target_window: str | None,
    substitute_fn: Callable[[str, Mapping[str, Any]], str],
    locate_fn: Callable[[dict[str, Any], str | None], tuple[int, int] | None],
    wait_for_queue_fn: Callable[..., bool],
    sleep_fn: Callable[[float], bool],
) -> bool:
    """Locates target coordinates and executes native mouse click, double click, or right click."""
    locator = step.get("locator", {})
    win = substitute_fn(str(step.get("window_title") or target_window or ""), context)
    max_retries = max(int(step.get("max_retries", 3)), 1)
    retry_delay_s = float(step.get("retry_delay_s", 0.35))
    coords = None

    for attempt in range(1, max_retries + 1):
        if not wait_for_queue_fn():
            return False
        coords = locate_fn(locator, win)
        if coords is not None:
            break
        if win:
            handle_known_dialog_popups(win)
        if attempt < max_retries:
            if not sleep_fn(retry_delay_s):
                return False

    if coords is None:
        if not wait_for_queue_fn():
            return False
        logger.error("  [!] Target not found for action %s: %s", action_type, locator)
        save_failure_screenshot(step_id, str(step.get("description", "")), win)
        return False

    with input_shield():
        if action_type == "DOUBLE_CLICK":
            send_native_click(coords[0], coords[1], double=True)
        elif action_type == "RIGHT_CLICK":
            send_native_click(coords[0], coords[1], button="right")
        else:
            send_native_click(coords[0], coords[1])

    return True


def execute_type_text(
    step: Mapping[str, Any],
    step_id: str,
    action_type: str,
    context: Mapping[str, Any],
    substitute_fn: Callable[[str, Mapping[str, Any]], str],
) -> bool:
    """Injects Unicode text or clipboard content into the focused control."""
    raw_text = str(step.get("text", "") or step.get("content", ""))
    text_to_type = substitute_fn(raw_text, context)

    # Fail-fast check: If raw text contains dynamic variable placeholders but resolves to empty string
    if "{" in raw_text and not text_to_type.strip():
        logger.error("  [!] %s aborted: Placeholder in %r resolved to empty string.", action_type, raw_text)
        return False

    press_enter = bool(step.get("press_enter", False))
    use_clipboard = bool(
        step.get("use_clipboard", False)
        or action_type == "PASTE_CLIPBOARD"
        or ("\\" in text_to_type or "/" in text_to_type or len(text_to_type) > 15)
    )
    is_secret = bool(step.get("is_secret", False)) or is_sensitive_credential_text(raw_text, str(step.get("description", "")))
    if is_secret:
        logger.info("  [Action %s] %s: [PROTECTED SENSITIVE CREDENTIAL MASKED]", step_id, action_type)

    with input_shield():
        if use_clipboard and sys.platform == "win32":
            paste_text_via_clipboard(text_to_type, press_enter=press_enter)
        else:
            type_unicode_text(text_to_type, press_enter=press_enter)

    return True


def execute_type_file_path(
    step: Mapping[str, Any],
    step_id: str,
    context: Mapping[str, Any],
    target_window: str | None,
    rdp_prefix: str,
    substitute_fn: Callable[[str, Mapping[str, Any]], str],
) -> bool:
    """Validates file path existence and pasts it into the target file dialog."""
    raw_path = str(step.get("file_path", context.get("document_fullpath", "") or ""))
    sub_path = substitute_fn(raw_path, context).strip()
    if not sub_path:
        logger.error("  [!] TYPE_FILE_PATH aborted: Target file path is empty or unresolved.")
        return False

    is_safe, clean_path = sanitize_safe_path(sub_path)
    if not is_safe or not clean_path.strip():
        logger.error("[Security] Aborted TYPE_FILE_PATH due to invalid/unsafe path: %r", sub_path)
        save_failure_screenshot(step_id, f"Security Block: {sub_path}", target_window)
        return False

    final_path = os.path.abspath(clean_path)
    if not os.path.exists(final_path):
        logger.error("  [!] TYPE_FILE_PATH aborted: Target file does not exist on disk: %s", final_path)
        save_failure_screenshot(step_id, f"Missing File: {final_path}", target_window)
        return False

    if rdp_prefix and re.match(r"^[a-zA-Z]:", final_path):
        drive_letter = final_path[0].upper()
        prefix = rdp_prefix.rstrip("\\/")
        final_path = f"{prefix}\\{drive_letter}{final_path[2:]}"

    press_enter = bool(step.get("press_enter", True))
    with input_shield():
        paste_text_via_clipboard(final_path, press_enter=press_enter)

    return True


def execute_wait_for_element(
    step: Mapping[str, Any],
    context: Mapping[str, Any],
    target_window: str | None,
    substitute_fn: Callable[[str, Mapping[str, Any]], str],
    locate_fn: Callable[[dict[str, Any], str | None], tuple[int, int] | None],
    wait_for_queue_fn: Callable[..., bool],
    sleep_fn: Callable[[float], bool],
) -> bool:
    """Polls for an element on screen until timeout."""
    locator = step.get("locator", {})
    win = substitute_fn(str(step.get("window_title") or target_window or ""), context)
    timeout_s = float(step.get("timeout_s", step.get("duration_s", 5.0)))
    poll_interval_s = float(step.get("poll_interval_s", 0.25))
    start_t = time.time()
    found = False

    while (time.time() - start_t) <= timeout_s:
        if not wait_for_queue_fn():
            return False
        coords = locate_fn(locator, win)
        if coords is not None:
            found = True
            break
        handle_known_dialog_popups(win)
        if not sleep_fn(poll_interval_s):
            return False

    return found
