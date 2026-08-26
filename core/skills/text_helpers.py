"""Text, keyboard, clipboard, and placeholder formatting helpers for RPA skills."""

from __future__ import annotations

import ctypes
import logging
import re
import sys
import time
from collections.abc import Mapping
from typing import Any

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


def _open_clipboard_with_retry(user32: Any, retries: int = 5, delay: float = 0.01) -> bool:
    """Attempts to open clipboard with retry backoff to handle transient locks."""
    for _ in range(retries):
        if user32.OpenClipboard(0):
            return True
        time.sleep(delay)
    return False


def _get_clipboard_unicode(user32: Any, kernel32: Any) -> str | None:
    """Safely extracts unicode text from clipboard if present."""
    CF_UNICODETEXT = 13
    if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
        return None
    user32.GetClipboardData.restype = ctypes.c_void_p
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]

    h_data = user32.GetClipboardData(CF_UNICODETEXT)
    if not h_data:
        return None
    ptr = kernel32.GlobalLock(h_data)
    if not ptr:
        return None
    try:
        return str(ctypes.wstring_at(ptr))
    finally:
        kernel32.GlobalUnlock(h_data)


def _set_clipboard_unicode(user32: Any, kernel32: Any, text: str) -> bool:
    """Sets unicode text to clipboard memory buffer."""
    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002
    encoded = text.encode("utf-16le") + b"\x00\x00"

    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    user32.SetClipboardData.restype = ctypes.c_void_p
    user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]

    h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(encoded))
    if not h_mem:
        return False
    ptr = kernel32.GlobalLock(h_mem)
    if not ptr:
        kernel32.GlobalFree(h_mem)
        return False
    ctypes.memmove(ptr, encoded, len(encoded))
    kernel32.GlobalUnlock(h_mem)
    user32.EmptyClipboard()
    user32.SetClipboardData(CF_UNICODETEXT, h_mem)
    return True


def paste_text_via_clipboard(text: str, press_enter: bool = False) -> bool:
    """Instantly pastes text via Windows Clipboard (Ctrl+V), avoiding layout/character typing lags."""
    if sys.platform != "win32":
        type_unicode_text(text, press_enter=press_enter)
        return True

    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        # 1. Read existing clipboard text to restore afterwards
        prev_text: str | None = None
        if _open_clipboard_with_retry(user32):
            try:
                prev_text = _get_clipboard_unicode(user32, kernel32)
            finally:
                user32.CloseClipboard()

        # 2. Set new text to clipboard
        if not _open_clipboard_with_retry(user32):
            type_unicode_text(text, press_enter=press_enter)
            return False

        try:
            if not _set_clipboard_unicode(user32, kernel32, text):
                type_unicode_text(text, press_enter=press_enter)
                return False
        finally:
            user32.CloseClipboard()

        # 3. Send Ctrl+V
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

        # 4. Mandatory yield delay (80ms) so target app processes WM_PASTE before clipboard restoration
        time.sleep(0.08)

        # 5. Restore previous clipboard text if available
        if prev_text is not None and _open_clipboard_with_retry(user32):
            try:
                _set_clipboard_unicode(user32, kernel32, prev_text)
            finally:
                user32.CloseClipboard()

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


def substitute_placeholders(text: str, context: Mapping[str, Any]) -> str:
    """Dynamically substitutes placeholders with optional modifiers (e.g. {Nachname|upper})."""
    if not isinstance(text, str) or "{" not in text:
        return text

    # Derived dynamic properties from document_fullpath
    fullpath = str(context.get("document_fullpath", "") or "")
    derived: dict[str, Any] = {}

    # First copy all context entries, normalizing keys by stripping braces
    for k, v in context.items():
        derived[k] = v
        clean_k = str(k).strip("{} ")
        if clean_k and clean_k not in derived:
            derived[clean_k] = v

    # Derive Person / Patient subfields (Nachname, Vorname) if not present
    person_val = str(derived.get("Person") or derived.get("person") or derived.get("Patient") or derived.get("patient") or "").strip()
    if person_val and "," in person_val:
        person_parts = person_val.split(",", 1)
        derived.setdefault("Nachname", person_parts[0].strip())
        derived.setdefault("Vorname", person_parts[1].strip())
    elif person_val and " " in person_val:
        person_parts = person_val.split(" ", 1)
        derived.setdefault("Vorname", person_parts[0].strip())
        derived.setdefault("Nachname", person_parts[1].strip())

    # Derive path-related variables (cross-platform compatible)
    if fullpath:
        from pathlib import PurePath, PureWindowsPath

        p = PureWindowsPath(fullpath) if ("\\" in fullpath or ":" in fullpath) else PurePath(fullpath)
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

    # Case-insensitive lookup map
    lower_map = {k.lower(): v for k, v in derived.items() if isinstance(k, str)}

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
        if val is None and key in derived:
            val = derived[key]
        if val is None and key.lower() in lower_map:
            val = lower_map[key.lower()]

        str_val = str(val) if val is not None else ""
        if modifier:
            return apply_string_modifier(str_val, modifier)
        return str_val

    return re.sub(r"\{([^{}]+)\}", replace_match, text)

