"""OS Window lifecycle, activation, maximize, freeze recovery, and modal popup handling for RPA skills."""

from __future__ import annotations

import ctypes
import logging
import sys
import time
from collections.abc import Callable, Mapping
from typing import Any

from core.skills.grounder import SoMGrounder

import os
import re
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore[assignment]


def save_failure_screenshot(step_id: str, desc: str = "", window_title: str | None = None) -> str | None:
    """Captures and saves a diagnostic screenshot when a skill step fails."""
    try:
        screen = SoMGrounder.capture_screen(window_title)
        if screen is None:
            screen = SoMGrounder.capture_screen(None)
        if screen is not None:
            base_dir = str(Path(__file__).resolve().parents[2])
            fail_dir = os.path.join(base_dir, "scratch", "rpa_failures")
            os.makedirs(fail_dir, exist_ok=True)
            sanitized_step = re.sub(r"[^\w\-_\.]", "_", step_id)
            filename = f"failure_{int(time.time())}_{sanitized_step}.png"
            target_path = os.path.join(fail_dir, filename)
            screen.save(target_path)
            logger.info("[WindowManager] Saved failure screenshot to: %s", target_path)
            return target_path
    except Exception as e:
        logger.debug("[WindowManager] Could not save failure screenshot: %s", e)
    return None


def maximize_target_window(win_pattern: str) -> None:
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
            hwnd = found_hwnd[0]
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            current_tid = kernel32.GetCurrentThreadId()
            target_tid = user32.GetWindowThreadProcessId(hwnd, None)
            if current_tid != target_tid:
                user32.AttachThreadInput(current_tid, target_tid, True)
            user32.ShowWindow(hwnd, 3)  # SW_MAXIMIZE
            user32.SetForegroundWindow(hwnd)
            user32.BringWindowToTop(hwnd)
            user32.SetFocus(hwnd)
            if current_tid != target_tid:
                user32.AttachThreadInput(current_tid, target_tid, False)
            time.sleep(0.2)
    except Exception as e:
        logger.debug("[WindowManager] Maximize window error: %s", e)


def ensure_window_ready(
    win_pattern: str,
    context: Mapping[str, Any],
    launch_skill_id: str = "",
    exe_path: str = "",
    maximize: bool = False,
    execute_skill_fn: Callable[[str, dict[str, Any]], bool] | None = None,
    is_cancelled_fn: Callable[[], bool] | None = None,
) -> bool:
    """Checks if target window is available; if not, triggers launch skill or executable and maximizes."""
    if is_cancelled_fn and is_cancelled_fn():
        return False

    screen = SoMGrounder.capture_screen(win_pattern) if win_pattern else None
    if screen is not None:
        if maximize and sys.platform == "win32":
            maximize_target_window(win_pattern)
        return True

    # Window not found -> try launch skill or executable
    if launch_skill_id and execute_skill_fn:
        logger.info("[WindowManager] Window '%s' not found. Triggering launch skill: '%s'", win_pattern, launch_skill_id)
        if not execute_skill_fn(str(launch_skill_id), dict(context)):
            logger.warning("[WindowManager] Launch skill '%s' failed.", launch_skill_id)
            return False
    elif exe_path:
        logger.info("[WindowManager] Window '%s' not found. Launching executable: '%s'", win_pattern, exe_path)
        try:
            if os.path.exists(str(exe_path)):
                subprocess.Popen([str(exe_path)])
            else:
                subprocess.Popen(f'"{exe_path}"', shell=True)
        except Exception as e:
            logger.error("[WindowManager] Failed to launch executable '%s': %s", exe_path, e)
            return False

    # Wait up to 10s for the window to appear (interruptible in 0.1s slices)
    for tick in range(100):
        if is_cancelled_fn and is_cancelled_fn():
            return False
        time.sleep(0.1)
        if (tick + 1) % 5 == 0:
            screen = SoMGrounder.capture_screen(win_pattern)
            if screen is not None:
                if maximize and sys.platform == "win32":
                    maximize_target_window(win_pattern)
                return True

    return False


def check_hung_app_and_recover(
    win_pattern: str,
    context: Mapping[str, Any],
    recover_enabled: bool = False,
    ensure_ready_fn: Callable[..., bool] | None = None,
) -> bool:
    """Checks if target window is hung/unresponsive and restarts it if configured."""
    if sys.platform != "win32" or not win_pattern or not recover_enabled:
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
                logger.warning("[WindowManager] Detected hung/unresponsive window '%s' (HWND %s). Terminating process...", win_pattern, hwnd)
                pid = ctypes.c_ulong()
                ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value:
                    import subprocess

                    subprocess.run(["taskkill", "/F", "/PID", str(pid.value)], check=False, capture_output=True)
                    time.sleep(1.0)
                    if ensure_ready_fn:
                        return ensure_ready_fn(win_pattern, context, maximize=True)
    except Exception as e:
        logger.debug("[WindowManager] Hung app check error: %s", e)
    return False


def handle_known_dialog_popups(window_title: str | None = None) -> bool:
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
            # Dialog triggers indicating overwrite/confirmation popup
            if any(k in t_lower for k in ("überschreiben", "overwrite", "bereits vorhanden", "already exists", "ersetzen", "replace")):
                popup_detected = True
            # Confirmation buttons
            if t_lower in ("ja", "yes", "ok", "überschreiben", "overwrite", "replace", "fortfahren", "weiter"):
                xs = [float(p[0]) for p in box]
                ys = [float(p[1]) for p in box]
                confirm_btn_coords = (int(sum(xs) / len(xs)), int(sum(ys) / len(ys)))

        if popup_detected and confirm_btn_coords and sys.platform == "win32":
            logger.info("[WindowManager] Detected blocking dialog popup. Auto-clicking confirmation at %s", confirm_btn_coords)
            ctypes.windll.user32.SetCursorPos(confirm_btn_coords[0], confirm_btn_coords[1])
            time.sleep(0.05)
            ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
            ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)
            time.sleep(0.3)
            return True
    except Exception as e:
        logger.debug("[WindowManager] Dialog auto-recovery check error: %s", e)
    return False
