"""OS Window lifecycle, activation, maximize, freeze recovery, and modal popup handling for RPA skills."""

from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from core.skills.grounder import SoMGrounder

logger = logging.getLogger(__name__)

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore[assignment]

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    user32 = getattr(ctypes.windll, "user32", None)
    kernel32 = getattr(ctypes.windll, "kernel32", None)

    if user32:
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextLengthW.restype = ctypes.c_int
        user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetWindowTextW.restype = ctypes.c_int
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.EnumWindows.argtypes = [ctypes.c_void_p, wintypes.LPARAM]
        user32.EnumWindows.restype = wintypes.BOOL
        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.ShowWindow.restype = wintypes.BOOL
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        user32.SetForegroundWindow.restype = wintypes.BOOL
        user32.BringWindowToTop.argtypes = [wintypes.HWND]
        user32.BringWindowToTop.restype = wintypes.BOOL
        user32.SetFocus.argtypes = [wintypes.HWND]
        user32.SetFocus.restype = wintypes.HWND
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
        user32.AttachThreadInput.restype = wintypes.BOOL
        user32.IsHungAppWindow.argtypes = [wintypes.HWND]
        user32.IsHungAppWindow.restype = wintypes.BOOL
        user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
        user32.SetCursorPos.restype = wintypes.BOOL


def find_window_hwnd(title_pattern: str, require_visible: bool = True) -> int | None:
    """Finds an HWND by window title substring or pattern on Windows."""
    if sys.platform != "win32" or not title_pattern:
        return None
    try:
        clean_pat = title_pattern.lower().replace("*", "").strip()
        found: list[int] = []

        def enum_proc(h_val: int, _lparam: int) -> bool:
            if require_visible and not ctypes.windll.user32.IsWindowVisible(h_val):
                return True
            length = ctypes.windll.user32.GetWindowTextLengthW(h_val)
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                ctypes.windll.user32.GetWindowTextW(h_val, buff, length + 1)
                title = buff.value.strip()
                if clean_pat in title.lower():
                    found.append(h_val)
                    return False
            return True

        wnd_enum_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)(enum_proc)
        ctypes.windll.user32.EnumWindows(wnd_enum_proc, 0)
        return found[0] if found else None
    except Exception as e:
        logger.debug("[WindowManager] find_window_hwnd error: %s", e)
        return None


def activate_window(hwnd: int, show_cmd: int = 9) -> bool:
    """Brings the target window to foreground and attaches thread input."""
    if sys.platform != "win32" or not hwnd:
        return False
    try:
        u32 = ctypes.windll.user32
        k32 = ctypes.windll.kernel32
        current_tid = k32.GetCurrentThreadId()
        target_tid = u32.GetWindowThreadProcessId(hwnd, None)
        if current_tid != target_tid:
            u32.AttachThreadInput(current_tid, target_tid, True)
        u32.ShowWindow(hwnd, show_cmd)
        u32.SetForegroundWindow(hwnd)
        u32.BringWindowToTop(hwnd)
        u32.SetFocus(hwnd)
        if current_tid != target_tid:
            u32.AttachThreadInput(current_tid, target_tid, False)
        return True
    except Exception as e:
        logger.debug("[WindowManager] activate_window error: %s", e)
        return False


def get_active_window_title() -> str:
    """Returns the window title of the currently active foreground window on Windows."""
    if sys.platform == "win32":
        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            if hwnd:
                length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
                    return buff.value
        except (AttributeError, OSError, RuntimeError, ValueError):
            pass
    return "Remote Desktop*"


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
    hwnd = find_window_hwnd(win_pattern)
    if hwnd:
        activate_window(hwnd, show_cmd=3)  # SW_MAXIMIZE
        time.sleep(0.2)


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
        hwnd = find_window_hwnd(win_pattern, require_visible=False)
        if hwnd:
            is_hung = bool(ctypes.windll.user32.IsHungAppWindow(hwnd))
            if is_hung:
                logger.warning("[WindowManager] Detected hung/unresponsive window '%s' (HWND %s). Terminating process...", win_pattern, hwnd)
                pid = ctypes.c_ulong()
                ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value:
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
        from core.image_processing import run_rapid_ocr

        screen = SoMGrounder.capture_screen(window_title)
        if not screen:
            return False
        img_np = np.array(screen) if np is not None else None
        if img_np is None:
            return False
        res = run_rapid_ocr(img_np)
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
            from core.skills.action_executor import send_native_click

            send_native_click(confirm_btn_coords[0], confirm_btn_coords[1])
            time.sleep(0.3)
            return True
    except Exception as e:
        logger.debug("[WindowManager] Dialog auto-recovery check error: %s", e)
    return False
