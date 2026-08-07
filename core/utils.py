import datetime
import logging
import os
import re
import shutil
import threading
import time
from collections import deque
from difflib import SequenceMatcher
from typing import Any

logger = logging.getLogger(__name__)

# ── In-memory log handler for web dashboard buffering ──

class MemoryLogHandler(logging.Handler):
    def __init__(self, max_records: int = 2000):
        super().__init__()
        self.records: deque[dict[str, Any]] = deque(maxlen=max_records)
        self._lock: threading.Lock = threading.Lock()
        self.seq_id = 0

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            with self._lock:
                self.seq_id += 1
                self.records.append(
                    {
                        "id": self.seq_id,
                        "level": record.levelname,
                        "message": msg,
                        "time": time.strftime(
                            "%H:%M:%S", time.localtime(record.created)
                        ),
                    }
                )
        except ValueError:
            self.handleError(record)

    def get_logs(
        self, since_id: int = 0, limit: int = 300
    ) -> tuple[list[dict[str, Any]], int]:
        with self._lock:
            if since_id == 0:
                logs = list(self.records)[-limit:]
            else:
                logs = [r for r in self.records if int(r["id"]) > since_id][:limit]
            return logs, self.seq_id

    def clear(self) -> None:
        with self._lock:
            self.records.clear()


memory_log_handler = MemoryLogHandler()
memory_log_handler.setFormatter(
    logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
)


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

def clean_path_component(text: str) -> str:
    """Strips characters from text that are invalid or disruptive in the Windows filesystem (e.g. square brackets)."""
    if not text:
        return "UNKNOWN"
    cleaned = _RE_INVALID_PATH_CHARS.sub("", str(text))
    # Since "__" is our folder delimiter, replace it with a single "_"
    cleaned = cleaned.replace("__", "_")
    cleaned = cleaned.replace("--", "-")
    cleaned = cleaned.strip()
    return cleaned if cleaned else "UNKNOWN"


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
        token = "QQQMISSINGPLACEHOLDERQQQ"
        cleaned = cleaned.replace("----", token)
        cleaned = re.sub(f"{escaped}(?:{escaped})+", delimiter, cleaned)
        cleaned = re.sub(f"(?:{escaped})+$", "", cleaned)
        cleaned = re.sub(f"^{escaped}+", "", cleaned)
        cleaned = cleaned.replace(token, "----")
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


def format_date_robust(date_str: str) -> str:
    """Robustly converts an extracted date string to YYYY-MM-DD format and validates date range."""
    if not date_str or "MISSING" in date_str.upper() or "----" in date_str:
        return "----"

    final_date = None

    # Check if already YYYY-MM-DD
    if re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        final_date = date_str
    else:
        # Check DD.MM.YYYY or DD.MM.YY or DD-MM-YY (also with comma instead of dot due to OCR errors)
        match_ger = re.search(
            r"(\d{1,2})[\.\-\,]\s*(\d{1,2})[\.\-\,]\s*(\d{2,4})", date_str
        )
        if match_ger:
            d, m, y = match_ger.groups()
            if len(y) == 2:
                y = "20" + y
            final_date = f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
        else:
            # Check YYYY.MM.DD
            match_iso = re.search(r"(\d{4})[\.\-](\d{1,2})[\.\-](\d{1,2})", date_str)
            if match_iso:
                y, m, d = match_iso.groups()
                final_date = f"{int(y):04d}-{int(m):02d}-{int(d):02d}"

    if not final_date:
        return date_str

    # Date validation (max 1 year in the past, max 1 month in the future)
    try:
        parsed_date = datetime.datetime.strptime(final_date, "%Y-%m-%d")
        today = datetime.date.today()

        # 1. Maximum 1 year (365 days) in the past
        min_date = today - datetime.timedelta(days=365)
        if parsed_date.date() < min_date:
            return "----"

        # 2. Maximum 31 days in the future
        max_future_date = today + datetime.timedelta(days=31)
        if parsed_date.date() > max_future_date:
            return "----"

        return final_date
    except ValueError:
        return "----"
    except Exception:
        return "----"


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
    """Checks whether a file is exclusively locked by another process."""
    if not os.path.exists(filepath):
        return False
    try:
        with open(filepath, "rb"):
            pass
        return False
    except (OSError, PermissionError):
        return True


def wait_until_unlocked(filepath: str, retries: int = 5, delay: float = 1.0) -> bool:
    """Patiently waits until a file is no longer locked by external processes (e.g. scanners)."""
    for attempt in range(retries):
        if not is_file_locked(filepath):
            return True
        logger.info(
            f"[*] File '{os.path.basename(filepath)}' is still locked (write in progress?). "
            f"Waiting {delay}s (attempt {attempt + 1}/{retries})..."
        )
        time.sleep(delay)
    return not is_file_locked(filepath)


def safe_move(src: str, dst: str, retries: int = 3, delay: int = 2) -> bool:
    for attempt in range(retries):
        try:
            shutil.move(src, dst)
            return True
        except PermissionError:
            if attempt < retries - 1:
                logger.warning(
                    f"[*] File locked, retrying {attempt + 1}/{retries} for {src}..."
                )
                time.sleep(delay)
    raise PermissionError(f"File could not be moved: {src}")


def correct_name_with_ocr(extracted: str, ocr_text: str) -> str:
    """Corrects the extracted name (first or last) based on OCR text.
    Uses SequenceMatcher (LCS-based, not pure Levenshtein) for fuzzy matching
    with strict, length-dependent safety rules:
    1. Corrects formatting (whitespace/casing) when the normalized string is identical.
    2. Corrects missing umlauts when the OCR word contains the umlaut and otherwise matches.

    The threshold depends on name length:
    - <= 5 chars: 0.92 (very strict — short names are more prone to false corrections)
    - <= 8 chars: 0.88
    - > 8 chars:  0.82
    """
    if not extracted or is_missing_value(extracted):
        return extracted

    def _clean_for_match(text: str) -> str:
        if not text:
            return ""
        return re.sub(r"[^a-zäöüß]", "", text.lower())

    extracted_clean = _clean_for_match(extracted)
    if len(extracted_clean) < 3:
        return extracted

    # Dynamic threshold: score short names stricter, medium/long more tolerantly
    name_len = len(extracted_clean)
    if name_len <= 4:
        threshold = 0.9
    elif name_len <= 8:
        threshold = 0.85
    else:
        threshold = 0.80

    ocr_words = re.split(r"[^a-zA-ZäöüÄÖÜß]", ocr_text)

    best_word = None
    best_ratio = 0.0

    for word in ocr_words:
        word_clean = _clean_for_match(word)
        if len(word_clean) < min(3, len(extracted_clean)):  # Exclude artifacts, but allow short names
            continue

        ratio = SequenceMatcher(None, extracted_clean, word_clean).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_word = word

    if best_word:
        best_clean = _clean_for_match(best_word)

        # Pre-check for pure umlaut match (e.g. Muller vs. Müller)
        extracted_has_umlaut = any(c in extracted_clean for c in "äöüß")
        ocr_has_umlaut = any(c in best_clean for c in "äöüß")
        is_pure_umlaut_match = False
        if ocr_has_umlaut and not extracted_has_umlaut:
            vowel_map = str.maketrans("äöü", "aou")
            best_trans = best_clean.translate(vowel_map)
            if best_trans == extracted_clean:
                is_pure_umlaut_match = True

        # Allow correction with sufficient best-ratio OR pure umlaut match >= 0.80.
        if best_ratio >= threshold or (is_pure_umlaut_match and best_ratio >= 0.80):
            correction_type = (
                "format" if extracted_clean == best_clean
                else "umlaut" if is_pure_umlaut_match
                else "fuzzy"
            )
            logger.info(
                "[+] OCR correction (%s): '%s' -> '%s' (Similarity: %.2f, Threshold: %.2f)",
                correction_type, extracted, best_word, best_ratio, threshold,
            )
            return best_word

    return extracted


def _deduplicate_path(target_filepath: str) -> str:
    """Appends a timestamp suffix if the target file already exists."""
    if os.path.exists(target_filepath):
        base, ext = os.path.splitext(target_filepath)
        return f"{base}_{int(time.time())}{ext}"
    return target_filepath


def _remove_source_with_meta(filepath: str) -> None:
    """Deletes the source file and its associated .meta sidecar file."""
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
        meta_path = filepath + ".meta"
        if os.path.exists(meta_path):
            os.remove(meta_path)
    except OSError as e:
        logger.warning(f"[!] Error deleting source file '{filepath}': {e}")

