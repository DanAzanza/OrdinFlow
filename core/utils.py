import logging
import os
import re
import shutil
import sys
import threading
import time
from collections import deque
from typing import Any

logger = logging.getLogger(__name__)

# ── In-memory log handler for web dashboard buffering ──


class MemoryLogHandler(logging.Handler):
    def __init__(self, max_records: int = 3000):
        super().__init__()
        self.records: deque[dict[str, Any]] = deque(maxlen=max_records)
        self._lock: threading.Lock = threading.Lock()
        self.seq_id = 0
        self._initialized_from_file = False

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = record.getMessage()
            with self._lock:
                self.seq_id += 1
                self.records.append(
                    {
                        "id": self.seq_id,
                        "level": record.levelname,
                        "message": msg,
                        "time": time.strftime("%H:%M:%S", time.localtime(record.created)),
                    }
                )
        except Exception:
            self.handleError(record)

    def load_initial_from_file(self, log_path: str = "main.log", limit: int = 500) -> None:
        """Populates the in-memory ring buffer with recent historical lines from log file."""
        if not os.path.exists(log_path):
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            candidate = os.path.join(base_dir, log_path)
            if os.path.exists(candidate):
                log_path = candidate
            else:
                return
        try:
            with open(log_path, encoding="utf-8", errors="replace") as f:
                recent = list(deque(f, maxlen=limit))
            for line in recent:
                line_str = line.strip()
                if not line_str:
                    continue
                self.seq_id += 1
                p = line_str.split(" ", 3)
                if len(p) >= 4 and p[2].startswith("[") and p[2].endswith("]"):
                    tm = p[1].split(",")[0]
                    lvl = p[2][1:-1]
                    msg = p[3]
                    self.records.append({"id": self.seq_id, "level": lvl, "message": msg, "time": tm})
                else:
                    self.records.append({"id": self.seq_id, "level": "INFO", "message": line_str, "time": ""})
            self._initialized_from_file = True
        except Exception as e:
            logger.debug("Could not pre-load logs from file: %s", e)

    def get_logs(self, since_id: int = 0, limit: int = 300) -> tuple[list[dict[str, Any]], int]:
        with self._lock:
            if not self._initialized_from_file and not self.records:
                self.load_initial_from_file()
            if since_id == 0:
                logs = list(self.records)[-limit:]
            else:
                logs = [r for r in self.records if int(r["id"]) > since_id][:limit]
            return logs, self.seq_id

    def clear(self) -> None:
        with self._lock:
            self.records.clear()
            self.seq_id = 0
            self._initialized_from_file = True


memory_log_handler = MemoryLogHandler()


_RE_INVALID_PATH_CHARS = re.compile(r'[\\/*?:"<>|]')


MISSING_PLACEHOLDER = "----"

_MISSING_VALUES = frozenset(
    [
        "NONE",
        "NULL",
        "UNKNOWN",
        "",
        "[MISSING]",
        "MISSING",
        "NA",
        "N/A",
        "N.A.",
        "-",
        "NO INFORMATION",
        "----",
    ]
)


_RESERVED_WIN_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "COM1",
    "COM2",
    "COM3",
    "COM4",
    "COM5",
    "COM6",
    "COM7",
    "COM8",
    "COM9",
    "LPT1",
    "LPT2",
    "LPT3",
    "LPT4",
    "LPT5",
    "LPT6",
    "LPT7",
    "LPT8",
    "LPT9",
}


def is_bool_value(val: Any) -> bool:
    """Generically checks whether a value represents an explicit boolean."""
    if isinstance(val, bool):
        return True
    if isinstance(val, str) and val.strip().lower() in (
        "true",
        "false",
        "yes",
        "no",
        "ja",
        "nein",
    ):
        return True
    return False


def to_bool_value(val: Any) -> bool:
    """Generically converts a string or boolean value to a Python bool."""
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().lower() in ("true", "1", "yes", "ja")
    return bool(val)


def sanitize_filename(text: str, fallback: str = "UNKNOWN") -> str:
    """Sanitizes a string for safe use in file and directory names."""
    if not text:
        return fallback
    clean = re.sub(r'[\x00-\x1f\\/*?:"<>|]', "", str(text)).strip()
    clean = clean.strip(". ")
    if not clean:
        return fallback
    if clean.upper() in _RESERVED_WIN_NAMES:
        return f"_{clean}"
    return clean.replace("__", "_").replace("--", "-").strip()


def clean_path_component(text: str) -> str:
    """Strips characters from text that are invalid or disruptive in the Windows filesystem (e.g. square brackets)."""
    return sanitize_filename(text, fallback="UNKNOWN")


def clean_template_result(text: str, delimiter: str = "__") -> str:
    """Cleans multiple spaces, spaces before commas, and orphaned delimiters after a template substitution."""
    if not text:
        return ""
    if text == "----":
        return "----"
    cleaned = re.sub(r" +", " ", str(text))
    cleaned = re.sub(r" +,", ",", cleaned)
    # Sanitize the active delimiter at start, end, and for doubled delimiters
    if delimiter:
        escaped = re.escape(delimiter)
        # Protect the placeholder "----" with a token without underscores/hyphens
        placeholder_mask = "QQQMISSINGPLACEHOLDERQQQ"
        cleaned = cleaned.replace("----", placeholder_mask)
        cleaned = re.sub(f"{escaped}(?:{escaped})+", delimiter, cleaned)
        cleaned = re.sub(f"(?:{escaped})+$", "", cleaned)
        cleaned = re.sub(f"^{escaped}+", "", cleaned)
        cleaned = cleaned.replace(placeholder_mask, "----")
    return cleaned.strip()


def is_missing_value(val: Any) -> bool:
    """Checks whether a value is empty or contains a typical AI placeholder (e.g. NA, N/A, [MISSING])."""
    if not val:
        return True
    s = str(val).strip().upper()
    if s in _MISSING_VALUES:
        return True
    if "MISSING" in s:
        return True
    return False


def clean_extracted_value(val: Any) -> str:
    """Cleans extracted values of known OCR errors (such as dotless i)."""
    if not val:
        return "----"
    s = str(val).strip()
    s = s.replace("\u0131", "i")  # Turkish/OCR dotless i -> i
    return s


def format_result(res: dict, include_missing: bool = True) -> str:
    """Formats the result dictionary for clean log output with all extracted fields."""
    if not res:
        return "No data"
    ignore_keys = {"pages", "page_results", "b64_img", "raw_text", "images"}
    parts = []
    for k, val in res.items():
        if k in ignore_keys or isinstance(val, (dict, list)):
            continue
        if include_missing or (val and not is_missing_value(val)):
            parts.append(f"{k}='{val}'")
    return ", ".join(parts) if parts else "No extracted fields"


def is_file_locked(filepath: str) -> bool:
    """Checks whether a file is exclusively locked by another process or unreadable."""
    if not os.path.exists(filepath):
        return False
    try:
        with open(filepath, "rb"):
            pass
        return False
    except (OSError, PermissionError):
        return True


def wait_until_unlocked(filepath: str, retries: int = 6, delay: float = 0.5) -> bool:
    """Patiently waits until a file is no longer locked, non-empty, and structurally ready."""
    if not os.path.exists(filepath):
        return False

    filename = os.path.basename(filepath)
    is_pdf = filepath.lower().endswith(".pdf")

    for attempt in range(retries):
        if not is_file_locked(filepath):
            try:
                size = os.path.getsize(filepath)
                if size > 0:
                    if is_pdf:
                        try:
                            import fitz

                            with fitz.open(filepath) as doc:
                                if len(doc) > 0 and not doc.is_closed:
                                    return True
                        except Exception as e:
                            logger.debug("PDF not structurally complete yet: %s", e)
                    else:
                        return True
            except OSError as e:
                logger.debug("Could not inspect file '%s': %s", filepath, e)

        if attempt < retries - 1:
            logger.info(
                f"[*] File '{filename}' is still writing or locked. "
                f"Waiting {delay}s (attempt {attempt + 1}/{retries})..."
            )
            time.sleep(delay)

    # Final fallback check if retries exhausted
    if not is_file_locked(filepath) and os.path.exists(filepath):
        try:
            return os.path.getsize(filepath) > 0
        except OSError:
            return False
    return False


def safe_move(src: str, dst: str, retries: int = 3, delay: float = 2.0) -> bool:
    for attempt in range(retries):
        try:
            shutil.move(src, dst)
            return True
        except PermissionError:
            if attempt < retries - 1:
                logger.warning(f"[*] File locked, retrying {attempt + 1}/{retries} for {src}...")
                time.sleep(delay)
    raise PermissionError(f"File could not be moved: {src}")


def deduplicate_path(target_filepath: str) -> str:
    """Appends a timestamp suffix if the target file already exists."""
    if os.path.exists(target_filepath):
        base, ext = os.path.splitext(target_filepath)
        return f"{base}_{int(time.time())}{ext}"
    return target_filepath


def init_windows_dpi_awareness() -> None:
    """Configures Per-Monitor V2 DPI awareness on Windows with progressive fallbacks."""
    if sys.platform == "win32":
        try:
            import ctypes

            u32 = getattr(ctypes.windll, "user32", None)
            shcore = getattr(ctypes.windll, "shcore", None)
            if u32 and hasattr(u32, "SetProcessDpiAwarenessContext"):
                u32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
                return
            if shcore and hasattr(shcore, "SetProcessDpiAwareness"):
                shcore.SetProcessDpiAwareness(2)
                return
            if u32 and hasattr(u32, "SetProcessDPIAware"):
                u32.SetProcessDPIAware()
        except Exception as e:
            logger.debug("[Utils] DPI awareness init error: %s", e)


def send_to_trash(path: str) -> bool:
    """Moves a file or directory to the OS recycle bin (Windows Recycle Bin / trash).

    Returns True if successfully trashed or False if path does not exist or failed.
    """
    if not os.path.exists(path):
        return False

    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class SHFILEOPSTRUCTW(ctypes.Structure):
            _fields_ = [
                ("hwnd", wintypes.HWND),
                ("wFunc", wintypes.UINT),
                ("pFrom", wintypes.LPCWSTR),
                ("pTo", wintypes.LPCWSTR),
                ("fFlags", wintypes.WORD),
                ("fAnyOperationsAborted", wintypes.BOOL),
                ("hNameMappings", wintypes.LPVOID),
                ("lpszProgressTitle", wintypes.LPCWSTR),
            ]

        fo_delete = 0x0003
        fof_allowundo = 0x0040
        fof_noconfirmation = 0x0010
        fof_silent = 0x0004
        fof_noerrorui = 0x0400

        abs_path = os.path.abspath(path)
        p_from = abs_path + "\0\0"
        fileop = SHFILEOPSTRUCTW()
        fileop.hwnd = None
        fileop.wFunc = fo_delete
        fileop.pFrom = p_from
        fileop.pTo = None
        fileop.fFlags = fof_allowundo | fof_noconfirmation | fof_silent | fof_noerrorui
        shell32 = ctypes.windll.shell32
        shell32.SHFileOperationW.argtypes = [ctypes.c_void_p]
        shell32.SHFileOperationW.restype = ctypes.c_int
        res = shell32.SHFileOperationW(ctypes.byref(fileop))
        return res == 0
    else:
        try:
            import send2trash

            send2trash.send2trash(path)
            return True
        except ImportError:
            if os.path.isdir(path):
                import shutil

                shutil.rmtree(path)
            else:
                os.remove(path)
            return True


def trash_source_with_meta(filepath: str) -> None:
    """Moves the source file and its associated .meta sidecar file to the Recycle Bin."""
    try:
        if os.path.exists(filepath):
            send_to_trash(filepath)
        meta_path = filepath + ".meta"
        if os.path.exists(meta_path):
            send_to_trash(meta_path)
    except Exception as e:
        logger.warning(f"[!] Error moving source file to trash '{filepath}': {e}")


def remove_source_with_meta(filepath: str) -> None:
    """Deletes the source file and its associated .meta sidecar file."""
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
        meta_path = filepath + ".meta"
        if os.path.exists(meta_path):
            os.remove(meta_path)
    except OSError as e:
        logger.warning(f"[!] Error deleting source file '{filepath}': {e}")


def cleanup_empty_folder(folder_path: str, stop_at: str | None = None) -> None:
    """Recursively deletes empty directory and parent directories upwards up to stop_at."""
    if not os.path.exists(folder_path):
        return

    stop_abs = os.path.abspath(stop_at) if stop_at else None
    cur_path = os.path.abspath(folder_path)

    while cur_path and os.path.exists(cur_path):
        if stop_abs and (cur_path == stop_abs or not cur_path.startswith(stop_abs)):
            break
        try:
            entries = os.listdir(cur_path)
            doc_files = [f for f in entries if not f.lower().endswith(".meta") and f.lower() != "desktop.ini"]
            if not doc_files:
                for f in entries:
                    try:
                        os.remove(os.path.join(cur_path, f))
                    except OSError as e:
                        logger.debug("[Utils] Could not remove auxiliary file %s: %s", f, e)
                os.rmdir(cur_path)
                logger.info(f"[+] Deleted empty folder: {cur_path}")
                cur_path = os.path.dirname(cur_path)
            else:
                break
        except OSError as e:
            logger.debug("[Utils] Could not clean folder %s: %s", cur_path, e)
            break


def is_sensitive_credential_text(text: str, description: str = "") -> bool:
    """Checks if a string or description contains suspected credentials, passwords, or secret tokens."""
    if not text and not description:
        return False
    combined = f"{description} {text}".lower()
    pattern = r"\b(password|passwort|kennwort|geheim|secret|pin|api_key|token|access_key|auth_token|bearer)\b"
    return bool(re.search(pattern, combined))


def sanitize_safe_path(path: str) -> tuple[bool, str]:
    """Validates and sanitizes a file path against null bytes, traversal, and dangerous characters.

    Returns (is_safe, sanitized_normalized_path).
    """
    if not path or not isinstance(path, str):
        return True, ""

    # 1. Null byte check
    if "\x00" in path:
        logger.warning("[Security] Blocked path containing null bytes: %r", path)
        return False, ""

    # 2. Directory traversal checks (reject '..' components)
    parts = re.split(r"[\\/]", path)
    if ".." in parts:
        logger.warning("[Security] Blocked path containing directory traversal sequence '..': %r", path)
        return False, ""

    # 3. Clean and normalize
    normalized = os.path.normpath(path.strip())
    return True, normalized

