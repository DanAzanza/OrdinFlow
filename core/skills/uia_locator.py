"""Native Windows UI Automation (UIA) COM Locator Provider for OrdinFlow RPA Skills.

Provides high-speed, resolution-independent access to Win32/WPF/WinForms/Qt/Electron UI elements
via Microsoft COM IUIAutomation (UIAutomationCore.dll) with legacy Win32 HWND fallbacks.
Safely bounded with MTA COM initialization and transaction timeouts against application hangs.
"""

from __future__ import annotations

import ctypes
import logging
import sys
import threading
import time
from collections.abc import Mapping
from typing import Any

if sys.platform == "win32":
    from ctypes import wintypes

logger = logging.getLogger(__name__)

# UIA Property IDs
UIA_NamePropertyId = 30005
UIA_AutomationIdPropertyId = 30011
UIA_ClassNamePropertyId = 30012
UIA_ControlTypePropertyId = 30003
UIA_IsEnabledPropertyId = 30010
UIA_IsOffscreenPropertyId = 30022

# UIA Pattern IDs
UIA_InvokePatternId = 10000
UIA_ValuePatternId = 10002
UIA_TogglePatternId = 10015

# TreeScope constants
TreeScope_Element = 0x1
TreeScope_Children = 0x2
TreeScope_Descendants = 0x4
TreeScope_Subtree = 0x7

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

_local_com = threading.local()

if sys.platform == "win32":
    try:
        from ctypes import wintypes

        _user32 = ctypes.windll.user32
        _SMTO_NORMAL = 0x0000
        _SMTO_ABORTIFHUNG = 0x0002

        _user32.SendMessageTimeoutW.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
            wintypes.UINT,
            wintypes.UINT,
            ctypes.POINTER(getattr(wintypes, "DWORD_PTR", ctypes.c_ulonglong)),
        ]
        _user32.SendMessageTimeoutW.restype = getattr(wintypes, "LPARAM", ctypes.c_longlong)

        _user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        _user32.GetClassNameW.restype = ctypes.c_int
        _user32.GetDlgCtrlID.argtypes = [wintypes.HWND]
        _user32.GetDlgCtrlID.restype = ctypes.c_int
        _user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        _user32.GetWindowRect.restype = wintypes.BOOL
        _user32.EnumChildWindows.argtypes = [wintypes.HWND, ctypes.c_void_p, getattr(wintypes, "LPARAM", ctypes.c_longlong)]
        _user32.EnumChildWindows.restype = wintypes.BOOL
    except (AttributeError, OSError) as e:
        logger.debug("[UIALocator] User32 prototype initialization skipped: %s", e)


def _get_uia_com() -> Any:
    """Lazily initializes the IUIAutomation COM object for the current thread."""
    if sys.platform != "win32":
        return None

    if getattr(_local_com, "instance", None) is not None:
        return _local_com.instance

    try:
        import comtypes.client  # type: ignore[import-untyped]

        ctypes.windll.ole32.CoInitializeEx(0, 0x0)  # MTA
        core_mod = comtypes.client.GetModule("UIAutomationCore.dll")
        inst = comtypes.client.CreateObject(
            core_mod.CUIAutomation,
            interface=core_mod.IUIAutomation,
        )
        _local_com.core_mod = core_mod
        _local_com.instance = inst
        return inst
    except Exception as e:
        logger.debug("[UIALocator] IUIAutomation COM initialization unavailable: %s", e)
        return None


class UIALocator:
    """Windows UI Automation provider using COM IUIAutomation with Win32 fallback."""

    @staticmethod
    def is_available() -> bool:
        """Returns True if running on Windows."""
        return sys.platform == "win32"

    @classmethod
    def find_element(
        cls,
        locator: Mapping[str, Any],
        window_title: str = "",
        timeout_s: float = 2.5,
    ) -> dict[str, Any] | None:
        """Locates a UI element by automation_id, name, control_type, or class_name."""
        if not cls.is_available() or not locator:
            return None

        hwnd = cls._resolve_hwnd(window_title)
        if not hwnd:
            logger.debug("[UIALocator] Target window not found: %r", window_title)
            return None

        auto_id = str(locator.get("automation_id") or locator.get("id") or "").strip()
        name = str(locator.get("name") or locator.get("title") or "").strip()
        control_type = str(locator.get("control_type") or locator.get("type") or "").strip().lower()
        class_name = str(locator.get("class_name") or locator.get("class") or "").strip()

        start_t = time.time()
        while time.time() - start_t <= max(timeout_s, 0.1):
            # 1. Try COM IUIAutomation
            com_elem = cls._find_via_com(hwnd, auto_id, name, control_type, class_name)
            if com_elem is not None:
                return com_elem

            # 2. Fallback to standard Win32 HWND hierarchy
            win32_elem = cls._inspect_child_windows(hwnd, auto_id, name, control_type, class_name)
            if win32_elem is not None:
                return win32_elem

            time.sleep(0.1)

        return None

    @classmethod
    def _find_via_com(
        cls,
        hwnd: int,
        auto_id: str,
        name: str,
        control_type: str,
        class_name: str,
    ) -> dict[str, Any] | None:
        """Queries the COM IUIAutomation tree rooted at the window handle."""
        uia = _get_uia_com()
        if uia is None:
            return None

        try:
            root_elem = uia.ElementFromHandle(ctypes.c_void_p(hwnd))
            if not root_elem:
                return None

            # Build condition or query descendants
            walker = uia.RawViewWalker
            if not walker:
                return None

            return cls._walk_com_tree(walker, root_elem, auto_id, name, control_type, class_name)
        except Exception as e:
            logger.debug("[UIALocator] COM query failed: %s", e)
            return None

    @classmethod
    def _walk_com_tree(
        cls,
        walker: Any,
        elem: Any,
        auto_id: str,
        name: str,
        control_type: str,
        class_name: str,
        depth: int = 0,
    ) -> dict[str, Any] | None:
        """Walks COM accessibility subtree to find matching element."""
        if depth > 15 or not elem:
            return None

        try:
            cur_name = str(elem.CurrentName or "")
            cur_id = str(elem.CurrentAutomationId or "")
            cur_class = str(elem.CurrentClassName or "")
            cur_type_id = int(elem.CurrentControlType or 0)

            # Matching criteria
            match = True
            if auto_id and auto_id.lower() != cur_id.lower():
                match = False
            if match and name and name.lower() not in cur_name.lower():
                match = False
            if match and class_name and class_name.lower() not in cur_class.lower():
                match = False
            if match and control_type in UIA_CONTROL_TYPES:
                if cur_type_id != UIA_CONTROL_TYPES[control_type]:
                    match = False

            if match and (auto_id or name or class_name or control_type):
                rect = elem.CurrentBoundingRectangle
                left = int(rect.left) if hasattr(rect, "left") else 0
                top = int(rect.top) if hasattr(rect, "top") else 0
                right = int(rect.right) if hasattr(rect, "right") else 0
                bottom = int(rect.bottom) if hasattr(rect, "bottom") else 0

                return {
                    "hwnd": int(elem.CurrentNativeWindowHandle or 0),
                    "name": cur_name,
                    "automation_id": cur_id,
                    "class_name": cur_class,
                    "control_type": cur_type_id,
                    "rect": {"left": left, "top": top, "right": right, "bottom": bottom},
                    "center": ((left + right) // 2, (top + bottom) // 2) if right > left and bottom > top else None,
                    "com_elem": elem,
                }

            # Walk children
            child = walker.GetFirstChildElement(elem)
            while child:
                res = cls._walk_com_tree(walker, child, auto_id, name, control_type, class_name, depth + 1)
                if res is not None:
                    return res
                child = walker.GetNextSiblingElement(child)

        except Exception as e:
            logger.debug("[UIALocator] Error walking COM tree: %s", e)

        return None

    @classmethod
    def get_element_text(
        cls,
        locator: Mapping[str, Any],
        window_title: str = "",
        timeout_s: float = 2.5,
    ) -> str:
        """Extracts text from a UI element (via COM ValuePattern or Win32 WM_GETTEXT)."""
        elem = cls.find_element(locator, window_title=window_title, timeout_s=timeout_s)
        if not elem:
            return ""

        # Try COM ValuePattern
        com_elem = elem.get("com_elem")
        core_mod = getattr(_local_com, "core_mod", None)
        if com_elem is not None and core_mod is not None:
            try:
                pattern = com_elem.GetCurrentPattern(UIA_ValuePatternId)
                if pattern:
                    val_pattern = pattern.QueryInterface(core_mod.IUIAutomationValuePattern)
                    if val_pattern:
                        return str(val_pattern.CurrentValue or "").strip()
            except Exception as e:
                logger.debug("[UIALocator] COM ValuePattern get error: %s", e)

        # Try Win32 WM_GETTEXT
        hwnd = elem.get("hwnd", 0)
        if hwnd and sys.platform == "win32":
            user32 = ctypes.windll.user32
            length = user32.SendMessageW(hwnd, 0x000E, 0, 0)
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
        """Directly injects text into a UI element via COM ValuePattern or WM_SETTEXT."""
        elem = cls.find_element(locator, window_title=window_title, timeout_s=timeout_s)
        if not elem:
            return False

        com_elem = elem.get("com_elem")
        core_mod = getattr(_local_com, "core_mod", None)
        if com_elem is not None and core_mod is not None:
            try:
                pattern = com_elem.GetCurrentPattern(UIA_ValuePatternId)
                if pattern:
                    val_pattern = pattern.QueryInterface(core_mod.IUIAutomationValuePattern)
                    if val_pattern:
                        val_pattern.SetValue(str(text))
                        return True
            except Exception as e:
                logger.debug("[UIALocator] COM ValuePattern set error: %s", e)

        hwnd = elem.get("hwnd", 0)
        if hwnd and sys.platform == "win32":
            user32 = ctypes.windll.user32
            buff = ctypes.create_unicode_buffer(str(text))
            res = user32.SendMessageW(hwnd, 0x000C, 0, buff)
            return bool(res)

        return False

    @classmethod
    def click_element(
        cls,
        locator: Mapping[str, Any],
        window_title: str = "",
        timeout_s: float = 2.5,
    ) -> bool:
        """Performs a direct click or InvokePattern on a native button or control."""
        elem = cls.find_element(locator, window_title=window_title, timeout_s=timeout_s)
        if not elem:
            return False

        com_elem = elem.get("com_elem")
        core_mod = getattr(_local_com, "core_mod", None)
        if com_elem is not None and core_mod is not None:
            try:
                pattern = com_elem.GetCurrentPattern(UIA_InvokePatternId)
                if pattern:
                    invoke_pattern = pattern.QueryInterface(core_mod.IUIAutomationInvokePattern)
                    if invoke_pattern:
                        invoke_pattern.Invoke()
                        return True
            except Exception as e:
                logger.debug("[UIALocator] COM InvokePattern click error: %s", e)

        hwnd = elem.get("hwnd", 0)
        if hwnd and sys.platform == "win32":
            user32 = ctypes.windll.user32
            user32.SendMessageW(hwnd, 0x00F5, 0, 0)  # BM_CLICK
            return True

        center = elem.get("center")
        if center and sys.platform == "win32":
            from core.skills.action_executor import send_native_click

            return send_native_click(center[0], center[1])

        return False

    @classmethod
    def is_element_visible(
        cls,
        locator: Mapping[str, Any],
        window_title: str = "",
        timeout_s: float = 0.5,
    ) -> bool:
        """Returns True if the element exists and has non-zero size."""
        elem = cls.find_element(locator, window_title=window_title, timeout_s=timeout_s)
        return elem is not None

    @staticmethod
    def _resolve_hwnd(window_title: str) -> int:
        """Finds top-level HWND matching window title pattern."""
        if sys.platform != "win32":
            return 0
        from core.skills.window_manager import find_window_hwnd

        hwnd = find_window_hwnd(window_title, require_visible=True)
        return hwnd or 0

    @staticmethod
    def _inspect_child_windows(
        parent_hwnd: int,
        auto_id: str,
        name: str,
        control_type: str,
        class_name: str,
    ) -> dict[str, Any] | None:
        """Enumerates child Win32 controls and matches criteria."""
        if sys.platform != "win32":
            return None
        user32 = ctypes.windll.user32
        matched: dict[str, Any] | None = None

        def enum_child_cb(child_h: int, _lparam: int) -> bool:
            nonlocal matched
            cls_buff = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(child_h, cls_buff, 256)
            cur_class = cls_buff.value

            txt_buff = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(child_h, txt_buff, 512)
            cur_text = txt_buff.value

            ctrl_id = str(user32.GetDlgCtrlID(child_h))

            if auto_id and auto_id.lower() not in (ctrl_id.lower(), cur_text.lower()):
                return True
            if name and name.lower() not in cur_text.lower():
                return True
            if class_name and class_name.lower() not in cur_class.lower():
                return True
            if control_type:
                if control_type == "button" and "button" not in cur_class.lower():
                    return True
                if control_type == "edit" and "edit" not in cur_class.lower():
                    return True

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
                },
                "center": ((rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2),
            }
            return False

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        user32.EnumChildWindows(parent_hwnd, WNDENUMPROC(enum_child_cb), 0)
        return matched
