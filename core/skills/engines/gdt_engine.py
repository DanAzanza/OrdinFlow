"""German Medical GDT (Gerätedatenträger) Export Skill Engine for OrdinFlow.

Compliant with QMS / bvitg GDT 2.1 specification (Satzart 6310 - Daten einer Untersuchung).
Generates atomic, non-clobbering GDT files with strict 3-digit length prefixes (LLL)
and exact byte lengths for direct integration into German Praxisverwaltungssysteme
(CGM Medistar, CGM TurboMed, CGM ALBIS, medatixx / x.iserv, Tomedo, DURIA, etc.).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
import re
import time
from typing import Any
import unicodedata
import uuid

from core.skills.base import BaseSkill
from core.skills.models import SkillTask, SkillType, TaskProgress, TaskResult
from core.utils import is_within_allowed_roots, sanitize_safe_path

logger = logging.getLogger(__name__)

# Standard GDT 2.1 encodings mapping to GDT Tag 9206 (Zeichensatz)
# 1 = 7-Bit ASCII
# 2 = IBM CP 437 (DOS standard, default in German PVS)
# 3 = ISO 8859-1 (ANSI / Windows standard)
GDT_CODEPAGE_TAGS: dict[str, str] = {
    "cp437": "2",
    "ibm437": "2",
    "437": "2",
    "iso-8859-1": "3",
    "iso8859-1": "3",
    "latin1": "3",
    "cp1252": "3",
    "windows-1252": "3",
    "iso-8859-15": "3",
    "iso8859-15": "3",
}


def normalize_gdt_date(raw_date: Any, allow_fallback: bool | None = None) -> str | None:
    """Normalizes date formats (DD.MM.YYYY, YYYY-MM-DD, DDMMYYYY) to GDT DDMMYYYY format.

    For patient demographics (e.g. Geburtsdatum Tag 3103), this strictly returns None
    for invalid/missing dates to prevent corrupting patient records with synthetic/today dates.
    """
    if not raw_date:
        return time.strftime("%d%m%Y") if allow_fallback else None
    cleaned = str(raw_date).strip()
    if not cleaned or cleaned in ("-", "–", "unbekannt", "None"):
        return time.strftime("%d%m%Y") if allow_fallback else None

    # DD.MM.YYYY or DD/MM/YYYY or DD-MM-YYYY
    m = re.match(r"^(\d{1,2})[./\-](\d{1,2})[./\-](\d{4})$", cleaned)
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), m.group(3)
        if 1 <= day <= 31 and 1 <= month <= 12:
            return f"{day:02d}{month:02d}{year}"

    # YYYY-MM-DD
    m = re.match(r"^(\d{4})[./\-](\d{1,2})[./\-](\d{1,2})$", cleaned)
    if m:
        year, month, day = m.group(1), int(m.group(2)), int(m.group(3))
        if 1 <= day <= 31 and 1 <= month <= 12:
            return f"{day:02d}{month:02d}{year}"

    # Already DDMMYYYY (8 digits)
    m = re.match(r"^\d{8}$", cleaned)
    if m:
        day = int(cleaned[:2])
        month = int(cleaned[2:4])
        if 1 <= day <= 31 and 1 <= month <= 12:
            return cleaned

    return time.strftime("%d%m%Y") if allow_fallback else None


def normalize_gdt_time(raw_time: Any, allow_fallback: bool | None = None) -> str | None:
    """Normalizes time formats (HH:MM:SS, HH:MM, HHMMSS) to GDT HHMMSS format.

    Returns None if unparseable or absent unless allow_fallback is explicitly set.
    """
    if not raw_time:
        return time.strftime("%H%M%S") if allow_fallback else None
    cleaned = str(raw_time).strip()
    if not cleaned:
        return time.strftime("%H%M%S") if allow_fallback else None

    # HH:MM:SS
    m = re.match(r"^(\d{1,2}):(\d{1,2}):(\d{1,2})$", cleaned)
    if m:
        return f"{int(m.group(1)):02d}{int(m.group(2)):02d}{int(m.group(3)):02d}"
    # HH:MM
    m = re.match(r"^(\d{1,2}):(\d{1,2})$", cleaned)
    if m:
        return f"{int(m.group(1)):02d}{int(m.group(2)):02d}00"
    # Already HHMMSS (6 digits)
    m = re.match(r"^\d{6}$", cleaned)
    if m:
        return cleaned
    return time.strftime("%H%M%S") if allow_fallback else None


def transliterate_to_codepage(text: str, codepage: str = "cp437") -> str:
    """Transliterates unencodable characters (e.g. Slavic, Turkish, French) using ASCII-folding.

    Prevents '?' corruption and UnicodeEncodeError while preserving German Umlauts in CP437.
    """
    # Normalize Windows-1252 specific characters (0x80-0x9F) to ISO-8859-1 / ASCII equivalents
    win1252_replacements = {
        "€": "EUR",
        "„": '"',
        "“": '"',
        "”": '"',
        "‚": "'",
        "‘": "'",
        "’": "'",
        "–": "-",
        "—": "-",
        "…": "...",
        "‰": "%",
        "™": "TM",
        "•": "*",
    }
    for old_ch, new_ch in win1252_replacements.items():
        if old_ch in text:
            text = text.replace(old_ch, new_ch)

    canonical_cp = codepage.lower().replace("_", "-")
    try:
        text.encode(canonical_cp)
        return text
    except UnicodeEncodeError:
        pass

    # German Umlaut preservation dictionary for non-standard encodings
    char_map = {
        "ä": "ä", "ö": "ö", "ü": "ü", "Ä": "Ä", "Ö": "Ö", "Ü": "Ü", "ß": "ß",
        "æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE",
        "ø": "o", "Ø": "O", "å": "a", "Å": "A",
        "ł": "l", "Ł": "L", "đ": "d", "Đ": "D",
    }
    interm: list[str] = []
    for ch in text:
        if ch in char_map:
            interm.append(char_map[ch])
        else:
            # NFKD decomposition separates base character from diacritics
            decomposed = unicodedata.normalize("NFKD", ch)
            base_char = "".join(c for c in decomposed if not unicodedata.combining(c))
            interm.append(base_char if base_char else " ")

    candidate = "".join(interm)
    try:
        candidate.encode(canonical_cp)
        return candidate
    except UnicodeEncodeError:
        safe_chars = []
        for ch in candidate:
            try:
                ch.encode(canonical_cp)
                safe_chars.append(ch)
            except UnicodeEncodeError:
                safe_chars.append(" ")
        return "".join(safe_chars)


def wrap_gdt_text(text: str, max_chars: int = 70) -> list[str]:
    """Wraps long medical report or notes into sequential GDT 6220 lines on word boundaries."""
    if not text:
        return []
    lines: list[str] = []
    for raw_line in text.splitlines():
        cleaned_line = raw_line.strip()
        if not cleaned_line:
            continue
        words = cleaned_line.split()
        current_line: list[str] = []
        current_len = 0
        for w in words:
            word_len = len(w)
            if current_line and (current_len + 1 + word_len) > max_chars:
                lines.append(" ".join(current_line))
                current_line = [w]
                current_len = word_len
            else:
                current_line.append(w)
                current_len += (1 if current_line else 0) + word_len
        if current_line:
            lines.append(" ".join(current_line))
    return lines


def format_gdt_line(tag: str, value: str, codepage: str = "cp437") -> bytes:
    """Formats a single GDT 2.1 line: LLLFFFFDDDD...\\r\\n with strict 3-digit length and 4-digit tag.

    LLL = 3 (length field) + 4 (tag) + len(val_bytes) + 2 (\\r\\n) = len(val_bytes) + 9.
    LLL is strictly clamped to max 999 bytes to prevent 4-digit width overflow.
    """
    if len(tag) != 4 or not tag.isdigit():
        raise ValueError(f"GDT Tag must be exactly 4 digits: {tag!r}")

    # Remove inline line breaks
    clean_val = str(value).replace("\r", " ").replace("\n", " ").strip()
    canonical_cp = codepage.lower().replace("_", "-")
    trans_val = transliterate_to_codepage(clean_val, canonical_cp)
    val_bytes = trans_val.encode(canonical_cp)

    # In GDT 2.1, LLL is 3 ASCII digits. Max line length is 999 bytes.
    # 3 (LLL) + 4 (FFFF) + len(val_bytes) + 2 (\r\n) = len(val_bytes) + 9
    max_val_bytes = 999 - 9  # 990 bytes max value payload
    if len(val_bytes) > max_val_bytes:
        logger.warning("[GDTEngine] Tag %s value length (%d bytes) exceeds GDT 2.1 line limit; truncating to %d bytes", tag, len(val_bytes), max_val_bytes)
        val_bytes = val_bytes[:max_val_bytes]

    total_line_len = len(val_bytes) + 9
    prefix = f"{total_line_len:03d}{tag}".encode(canonical_cp)
    return prefix + val_bytes + b"\r\n"


def build_gdt_6310_payload(
    data: dict[str, Any],
    codepage: str = "cp437",
    sender_id: str = "ORDINFLOW",
    receiver_id: str = "PVS",
) -> bytes:
    """Builds a complete, specification-compliant GDT Satzart 6310 (Daten einer Untersuchung) payload.

    Standard GDT 2.1 Header structure:
      8000: Satzart (6310)
      8100: Satzlänge (Gesamtlänge in Bytes inkl. CR LF)
      9218: GDT-Version (02.10)
      8315: GDT-ID des Empfängers
      8316: GDT-ID des Senders
      9206: Zeichensatz (2 = CP437, 3 = ISO 8859-1)
    """
    canonical_cp = codepage.lower().replace("_", "-")
    charset_code = GDT_CODEPAGE_TAGS.get(canonical_cp, "2")

    # Header tags
    line_8000 = format_gdt_line("8000", "6310", canonical_cp)  # Satzart 6310 (Daten einer Untersuchung)
    line_9218 = format_gdt_line("9218", "02.10", canonical_cp)  # GDT Version 2.10
    line_8315 = format_gdt_line("8315", str(receiver_id)[:8], canonical_cp)  # Empfänger-ID
    line_8316 = format_gdt_line("8316", str(sender_id)[:8], canonical_cp)  # Sender-ID
    line_9206 = format_gdt_line("9206", charset_code, canonical_cp)  # Zeichensatz

    # Patient tags
    pat_id = str(data.get("PatientID") or data.get("PatientenNr") or data.get("PatientNr") or "").strip()
    if not pat_id:
        raise ValueError("GDT Satzart 6310 requires a valid, non-empty Patient ID (Tag 3000).")

    line_3000 = format_gdt_line("3000", pat_id, canonical_cp)

    last_name = str(data.get("Nachname") or data.get("LastName") or "").strip()
    first_name = str(data.get("Vorname") or data.get("FirstName") or "").strip()
    # Tag 3103 (Geburtsdatum) is optional in 6310: OMIT if missing, NEVER synthesize current date
    birth_date = normalize_gdt_date(data.get("Geburtsdatum") or data.get("DOB") or data.get("Geburtstag") or "")

    # Tag 3105 is strictly Versichertennummer (10-12 alphanumeric characters)
    insurance_no = str(data.get("Versichertennummer") or data.get("InsuranceNumber") or "").strip()

    # Examination / Befund tags (Tag 6200 is Mandatory in 6310, Tag 6201 is Optional)
    raw_exam_date = data.get("Befunddatum") or data.get("Datum") or data.get("Date") or ""
    exam_date = normalize_gdt_date(raw_exam_date)
    if not exam_date:
        exam_date = time.strftime("%d%m%Y")
        logger.warning(
            "[GDT] Tag 6200 (Untersuchungsdatum) missing or invalid (%r). Falling back to current date: %s",
            raw_exam_date,
            exam_date,
        )

    # Tag 6201 (Untersuchungsuhrzeit) is Optional in GDT 2.1: OMIT if missing, never synthesize fake seconds
    raw_exam_time = data.get("Befundzeit") or data.get("Uhrzeit") or data.get("Time") or ""
    exam_time = normalize_gdt_time(raw_exam_time)

    line_6200 = format_gdt_line("6200", exam_date, canonical_cp)

    body_lines: list[bytes] = [
        line_8000,
        # Tag 8100 inserted at index 1
        line_9218,
        line_8315,
        line_8316,
        line_9206,
        line_3000,
    ]
    if last_name:
        body_lines.append(format_gdt_line("3101", last_name, canonical_cp))
    if first_name:
        body_lines.append(format_gdt_line("3102", first_name, canonical_cp))
    if birth_date:
        body_lines.append(format_gdt_line("3103", birth_date, canonical_cp))
    if insurance_no:
        body_lines.append(format_gdt_line("3105", insurance_no, canonical_cp))

    body_lines.append(line_6200)
    if exam_time:
        body_lines.append(format_gdt_line("6201", exam_time, canonical_cp))

    # Befund text lines (wrapped to 70 chars per GDT standard)
    raw_text = str(
        data.get("Befund")
        or data.get("Befundtext")
        or data.get("Text")
        or data.get("Diagnose")
        or data.get("Summary")
        or ""
    ).strip()
    if raw_text:
        for chunk in wrap_gdt_text(raw_text, max_chars=70):
            body_lines.append(format_gdt_line("6220", chunk, canonical_cp))

    # PDF Document path reference (Tag 6227) and file name (Tag 6228)
    pdf_path = str(data.get("PDFPath") or data.get("document_fullpath") or data.get("filepath") or "").strip()
    if pdf_path:
        body_lines.append(format_gdt_line("6227", pdf_path, canonical_cp))
        body_lines.append(format_gdt_line("6228", os.path.basename(pdf_path), canonical_cp))

    # Deterministic Satzlänge (Tag 8100) calculation:
    # Standard GDT 2.1 Tag 8100 line is fixed at 14 bytes:
    # 3 (LLL='014') + 4 (tag='8100') + 5 (size='%05d') + 2 ('\r\n') = 14 bytes.
    tag_8100_fixed_len = 14
    other_lines_bytes = sum(len(b) for b in body_lines)
    total_bytes = other_lines_bytes + tag_8100_fixed_len

    if total_bytes <= 99999:
        line_8100 = f"0148100{total_bytes:05d}\r\n".encode(canonical_cp)
    else:
        # 6-digit overflow support: 3 (LLL='015') + 4 (tag='8100') + 6 (size='%06d') + 2 ('\r\n') = 15 bytes
        total_bytes = other_lines_bytes + 15
        line_8100 = f"0158100{total_bytes:06d}\r\n".encode(canonical_cp)

    # Assemble full payload: Tag 8000 is line 0, Tag 8100 is line 1
    final_lines: list[bytes] = [body_lines[0], line_8100] + body_lines[1:]
    return b"".join(final_lines)


def export_case_to_gdt(
    data: dict[str, Any],
    target_dir: str,
    codepage: str = "cp437",
    sender_id: str = "ORDINFLOW",
    receiver_id: str = "PVS",
    filename_prefix: str = "ORDINFLOW",
    write_semaphore: bool = False,
) -> str:
    """Atomically exports a case dictionary as a specification-compliant GDT file to target_dir.

    Returns the absolute path of the created GDT file.
    """
    is_safe, clean_dir = sanitize_safe_path(target_dir)
    if not is_safe or not clean_dir:
        raise ValueError(f"Target directory failed security sanitization: {target_dir!r}")

    out_dir = Path(clean_dir).resolve()
    if not is_within_allowed_roots(out_dir, allow_desktop=True):
        raise PermissionError(f"Target directory is outside allowed filesystem roots: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)

    payload = build_gdt_6310_payload(
        data=data,
        codepage=codepage,
        sender_id=sender_id,
        receiver_id=receiver_id,
    )

    # Collision-safe unique filename generation
    ts = time.strftime("%Y%m%d_%H%M%S")
    counter = 1
    clean_prefix = re.sub(r"[^\w\-]", "", filename_prefix) or "ORDINFLOW"
    while counter < 10000:
        candidate_name = f"{clean_prefix}_{ts}_{counter:04d}.gdt"
        candidate_path = out_dir / candidate_name
        if not candidate_path.exists():
            break
        counter += 1
    else:
        candidate_name = f"{clean_prefix}_{ts}_{uuid.uuid4().hex[:6]}.gdt"
        candidate_path = out_dir / candidate_name

    # Atomic write via temporary file
    temp_path = candidate_path.with_suffix(".gdt.tmp")
    with open(temp_path, "wb") as f:
        f.write(payload)
        f.flush()
        os.fsync(f.fileno())

    os.replace(temp_path, candidate_path)
    logger.info("[GDTEngine] Atomically exported GDT file (%d bytes) to %s", len(payload), candidate_path)

    # Optional semaphore file for legacy PVS directory watchers (e.g. .ok or .sem)
    if write_semaphore:
        sem_path = candidate_path.with_suffix(".sem")
        sem_tmp = sem_path.with_suffix(".sem.tmp")
        with open(sem_tmp, "w", encoding="ascii") as f:
            f.write(candidate_name)
        os.replace(sem_tmp, sem_path)

    return str(candidate_path)


class GDTEngine(BaseSkill):
    """Executes structured GDT exports for processed cases and documents directly to PVS directories."""

    def __init__(self, definition: dict[str, Any]):
        super().__init__(definition)
        self.skill_type = SkillType.GDT
        self.target_dir = str(definition.get("target_dir") or definition.get("export_dir") or "").strip()
        self.codepage = str(definition.get("codepage") or "cp437").strip()
        self.sender_id = str(definition.get("sender_id") or "ORDINFLOW").strip()
        self.receiver_id = str(definition.get("receiver_id") or "PVS").strip()
        self.filename_prefix = str(definition.get("filename_prefix") or "ORDINFLOW").strip()
        self.write_semaphore = bool(definition.get("write_semaphore", False))

    def execute(
        self,
        task: SkillTask,
        reporter: Any = None,
    ) -> TaskResult:
        """Executes GDT export for the given task context or file metadata."""
        if not self.target_dir:
            err_msg = "GDT Engine configuration missing 'target_dir'."
            logger.error("[GDTEngine] %s", err_msg)
            return TaskResult(
                success=False,
                error=err_msg,
            )

        context_data = dict(task.context or {})

        try:
            if reporter:
                reporter(TaskProgress(message=f"Exporting case to GDT in {self.target_dir}..."))

            out_file = export_case_to_gdt(
                data=context_data,
                target_dir=self.target_dir,
                codepage=self.codepage,
                sender_id=self.sender_id,
                receiver_id=self.receiver_id,
                filename_prefix=self.filename_prefix,
                write_semaphore=self.write_semaphore,
            )

            if reporter:
                reporter(TaskProgress(message=f"GDT export complete: {os.path.basename(out_file)}"))

            return TaskResult(
                success=True,
                data={"gdt_file": out_file, "filename": os.path.basename(out_file)},
            )
        except Exception as e:
            logger.error("[GDTEngine] Export failed: %s", e, exc_info=True)
            return TaskResult(
                success=False,
                error=str(e),
            )
