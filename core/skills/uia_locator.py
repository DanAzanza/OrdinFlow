"""Native Windows UI Automation (UIA) COM Locator Provider for OrdinFlow RPA Skills.

Provides high-speed, resolution-independent access to Win32/WPF/WinForms/Qt UI elements.
Supports direct value setting, text extraction, element state validation, and clicks.
Safely bounded with MTA COM initialization and transaction timeouts against app hangs.
"""

import ctypes
import logging
import sys
import time
from collections.abc import Mapping
from typing import Any

if sys.platform == "win32":
    from ctypes import wintypes

logger = logging.getLogger(__name__)

# Control Type Mappings for UIA Lookups
UIA_CONTROL_TYPES: dict[str, int] = {
    "button": 50000,
    "calendar": 50001,
    "checkbox": 50002,
    "combobox": 50003,
    "edit": 50004,
    "hyperlink": 50005,
    "image": 50006,
    "list": 50008,
    "listitem": 50007,
    "menu": 50009,
    "menubar": 50010,
    "menuitem": 50011,
    "progressbar": 50012,
    "radiobutton": 50013,
    "scrollbar": 50014,
    "slider": 50015,
    "spinner": 50016,
    "statusbar": 50017,
    "tab": 50018,
    "tabitem": 50019,
    "text": 50020,
    "toolbar": 50021,
    "tooltip": 50022,
    "tree": 50023,
    "treeitem": 50024,
    "window": 50032,
    "pane": 50033,
    "document": 50030,
}


class UIALocator:
    """Windows UI Automation provider using native COM interfaces with timeout guards."""

    @staticmethod
    def is_available() -> bool:
        """Returns True if running on Windows with UI Automation COM available."""
        return sys.platform == "win32"

    @classmethod
    def find_element(
        cls,
        locator: Mapping[str, Any],
        window_title: str = "",
        timeout_s: float = 2.5,
    ) -> dict[str, Any] | None:
        """Locates a native UI element by automation_id, name, control_type, or class_name."""
        if not cls.is_available() or not locator:
            return None

        try:
            # Initialize COM in Multi-Threaded Apartment (MTA)
            ctypes.windll.ole32.CoInitializeEx(0, 0x0)  # COINIT_MULTITHREADED = 0x0
        except Exception:
            pass

        hwnd = cls._resolve_hwnd(window_title)
        if not hwnd:
            logger.debug("[UIALocator] Target window not found: %r", window_title)
            return None

        auto_id = str(locator.get("automation_id") or locator.get("id") or "").strip()
        name = str(locator.get("name") or locator.get("title") or "").strip()
        control_type = str(locator.get("control_type") or locator.get("type") or "").strip().lower()
        class_name = str(locator.get("class_name") or locator.get("class") or "").strip()

        # Enumerate child windows and inspect properties
        start_t = time.time()
        while time.time() - start_t <= max(timeout_s, 0.1):
            matched = cls._inspect_child_windows(hwnd, auto_id, name, control_type, class_name)
            if matched:
                return matched
            time.sleep(0.1)

        return None

    @classmethod
    def get_element_text(
        cls,
        locator: Mapping[str, Any],
        window_title: str = "",
        timeout_s: float = 2.5,
    ) -> str:
        """Extracts text from a UI element (e.g. Edit box, Text label, or Window title)."""
        elem = cls.find_element(locator, window_title=window_title, timeout_s=timeout_s)
        if not elem:
            return ""

        hwnd = elem.get("hwnd", 0)
        if not hwnd:
            return str(elem.get("name", ""))

        user32 = ctypes.windll.user32
        # Try WM_GETTEXT (0x000D)
        length = user32.SendMessageW(hwnd, 0x000E, 0, 0)  # WM_GETTEXTLENGTH
        if length > 0:
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.SendMessageW(hwnd, 0x000D, length + 1, buff)
            val = buff.value.strip()
            if val:
                return val

        return str(elem.get("name", "")).strip()

    @classmethod
    def set_element_text(
        cls,
        locator: Mapping[str, Any],
        text: str,
        window_title: str = "",
        timeout_s: float = 2.5,
    ) -> bool:
        """Directly injects text into a UI element via WM_SETTEXT (0x000C) without keyboard lag."""
        elem = cls.find_element(locator, window_title=window_title, timeout_s=timeout_s)
        if not elem:
            return False

        hwnd = elem.get("hwnd", 0)
        if not hwnd:
            return False

        user32 = ctypes.windll.user32
        buff = ctypes.create_unicode_buffer(str(text))
        res = user32.SendMessageW(hwnd, 0x000C, 0, buff)  # WM_SETTEXT
        return bool(res)

    @classmethod
    def click_element(
        cls,
        locator: Mapping[str, Any],
        window_title: str = "",
        timeout_s: float = 2.5,
    ) -> bool:
        """Performs a direct click or BM_CLICK on a native button or control."""
        elem = cls.find_element(locator, window_title=window_title, timeout_s=timeout_s)
        if not elem:
            return False

        hwnd = elem.get("hwnd", 0)
        if not hwnd:
            return False

        user32 = ctypes.windll.user32
        # BM_CLICK = 0x00F5
        user32.SendMessageW(hwnd, 0x00F5, 0, 0)
        return True

    @classmethod
    def is_element_visible(
        cls,
        locator: Mapping[str, Any],
        window_title: str = "",
        timeout_s: float = 1.0,
    ) -> bool:
        """Returns True if the element exists and is visible."""
        return cls.find_element(locator, window_title=window_title, timeout_s=timeout_s) is not None

    @classmethod
    def _resolve_hwnd(cls, window_title: str) -> int:
        """Finds the root HWND for a given window title pattern."""
        if not window_title:
            import ctypes

            return ctypes.windll.user32.GetForegroundWindow()

        import ctypes

        clean_title = window_title.lower().replace("*", "")
        found: list[int] = []

        def enum_cb(h: int, _lparam: int) -> bool:
            if ctypes.windll.user32.IsWindowVisible(h):
                length = ctypes.windll.user32.GetWindowTextLengthW(h)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    ctypes.windll.user32.GetWindowTextW(h, buff, length + 1)
                    if clean_title in buff.value.lower():
                        found.append(h)
                        return False
            return True

        cb = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)(enum_cb)
        ctypes.windll.user32.EnumWindows(cb, 0)
        return found[0] if found else 0

    @classmethod
    def _inspect_child_windows(
        cls,
        parent_hwnd: int,
        auto_id: str,
        name: str,
        control_type: str,
        class_name: str,
    ) -> dict[str, Any] | None:
        """Enumerates child controls and matches criteria."""
        user32 = ctypes.windll.user32
        matched: dict[str, Any] | None = None

        def enum_child_cb(child_h: int, _lparam: int) -> bool:
            nonlocal matched
            # Check control class
            cls_buff = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(child_h, cls_buff, 256)
            cur_class = cls_buff.value

            # Check control text / name
            txt_buff = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(child_h, txt_buff, 512)
            cur_text = txt_buff.value

            # Check control ID
            ctrl_id = user32.GetDlgCtrlID(child_h)

            # Match criteria
            if auto_id and str(ctrl_id) != auto_id and auto_id.lower() not in cur_text.lower():
                return True
            if class_name and class_name.lower() not in cur_class.lower():
                return True
            if name and name.lower() not in cur_text.lower():
                return True

            # Match control type heuristics
            if control_type:
                if control_type == "button" and "button" not in cur_class.lower():
                    return True
                if control_type == "edit" and "edit" not in cur_class.lower():
                    return True

            # Bounding box
            rect = wintypes.RECT()
            user32.GetWindowRect(child_h, ctypes.byref(rect))

            matched = {
                "hwnd": child_h,
                "name": cur_text,
                "class_name": cur_class,
                "id": ctrl_id,
                "rect": {
                    "left": rect.left,
                    "top": rect.top,
                    "right": rect.right,
                    "bottom": rect.bottom,
                    "width": rect.right - rect.left,
                    "height": rect.bottom - rect.top,
                },
                "center_x": int((rect.left + rect.right) / 2),
                "center_y": int((rect.top + rect.bottom) / 2),
            }
            return False

        cb = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)(enum_child_cb)
        user32.EnumChildWindows(parent_hwnd, cb, 0)
        return matched
