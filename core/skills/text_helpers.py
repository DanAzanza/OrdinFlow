"""Text, keyboard, clipboard, and placeholder formatting helpers for RPA skills."""

from __future__ import annotations

import ctypes
import logging
import re
import sys
import time

logger = logging.getLogger(__name__)


def type_unicode_text(text: str, press_enter: bool = False) -> None:
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


def paste_text_via_clipboard(text: str, press_enter: bool = False) -> bool:
    """Instantly pastes text via Windows Clipboard (Ctrl+V), avoiding layout/character typing lags."""
    if sys.platform != "win32":
        type_unicode_text(text, press_enter=press_enter)
        return True

    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        CF_UNICODETEXT = 13
        GMEM_MOVEABLE = 0x0002

        encoded = text.encode("utf-16le") + b"\x00\x00"

        h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(encoded))
        if not h_mem:
            type_unicode_text(text, press_enter=press_enter)
            return False

        ptr = kernel32.GlobalLock(h_mem)
        if not ptr:
            kernel32.GlobalFree(h_mem)
            type_unicode_text(text, press_enter=press_enter)
            return False

        ctypes.memmove(ptr, encoded, len(encoded))
        kernel32.GlobalUnlock(h_mem)

        if not user32.OpenClipboard(0):
            kernel32.GlobalFree(h_mem)
            type_unicode_text(text, press_enter=press_enter)
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
        logger.debug("[paste_text_via_clipboard] Clipboard paste failed, falling back to keystrokes: %s", e)
        type_unicode_text(text, press_enter=press_enter)
        return False


def apply_string_modifier(val: str, modifier: str) -> str:
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
    if mod in ("filename", "basename", "stem", "ext", "extension", "parent", "folder"):
        from pathlib import PurePath, PureWindowsPath

        p = PureWindowsPath(val) if ("\\" in val or ":" in val) else PurePath(val)
        if mod == "filename":
            return p.name
        if mod in ("basename", "stem"):
            return p.stem
        if mod in ("ext", "extension"):
            return p.suffix
        if mod in ("parent", "folder"):
            return str(p.parent)
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
