"""German Medical GDT (Gerätedatenträger) Export Skill Engine for OrdinFlow.

Compliant with QMS / bvitg GDT 2.1 / 3.0 specification (Satzart 6302 - Befundübermittlung).
Generates atomic, non-clobbering GDT files with strict 4-digit tags and exact byte lengths
for integration with German Praxisverwaltungssysteme (Medistar, TurboMed, Albis, x.iserv, etc.).
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

# Standard GDT encodings mapping to GDT Tag 9206 (Zeichensatz)
# 1 = CP437 (DOS standard, default in German PVS)
# 4 = ISO-8859-15 / ANSI (Windows standard)
GDT_CODEPAGE_TAGS: dict[str, str] = {
    "cp437": "1",
    "ibm437": "1",
    "437": "1",
    "iso-8859-15": "4",
    "iso8859-15": "4",
    "iso-8859-1": "4",
    "latin1": "4",
    "cp1252": "4",
    "windows-1252": "4",
}


def normalize_gdt_date(raw_date: Any) -> str:
    """Normalizes various date formats (DD.MM.YYYY, YYYY-MM-DD, DDMMYYYY) to GDT DDMMYYYY format."""
    if not raw_date:
        return time.strftime("%d%m%Y")
    cleaned = str(raw_date).strip()
    # DD.MM.YYYY or DD/MM/YYYY or DD-MM-YYYY
    m = re.match(r"^(\d{1,2})[./\-](\d{1,2})[./\-](\d{4})$", cleaned)
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), m.group(3)
        return f"{day:02d}{month:02d}{year}"
    # YYYY-MM-DD
    m = re.match(r"^(\d{4})[./\-](\d{1,2})[./\-](\d{1,2})$", cleaned)
    if m:
        year, month, day = m.group(1), int(m.group(2)), int(m.group(3))
        return f"{day:02d}{month:02d}{year}"
    # Already DDMMYYYY (8 digits)
    m = re.match(r"^\d{8}$", cleaned)
    if m:
        return cleaned
    return time.strftime("%d%m%Y")


def normalize_gdt_time(raw_time: Any) -> str:
    """Normalizes time formats (HH:MM:SS, HH:MM, HHMMSS) to GDT HHMMSS format."""
    if not raw_time:
        return time.strftime("%H%M%S")
    cleaned = str(raw_time).strip()
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
    return time.strftime("%H%M%S")


def normalize_insurance_status(raw_status: Any) -> str:
    """Maps insurance status strings to GDT tag 3105 values (1 = GKV/Kasse, 2 = PKV/Privat)."""
    if raw_status is None:
        return "1"
    status_str = str(raw_status).strip().lower()
    if status_str in ("2", "pkv", "privat", "private", "selbstzahler", "beihilfe"):
        return "2"
    return "1"


def transliterate_to_codepage(text: str, codepage: str = "cp437") -> str:
    """Transliterates unencodable characters (e.g. Slavic, Turkish, French) using ASCII-folding.

    Prevents '?' corruption and UnicodeEncodeError while preserving German Umlauts in CP437.
    """
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
            # NFKD decomposition separates base character from diacritics (e.g. 'ç' -> 'c' + combining cedilla)
            decomposed = unicodedata.normalize("NFKD", ch)
            base_char = "".join(c for c in decomposed if not unicodedata.combining(c))
            interm.append(base_char if base_char else " ")

    candidate = "".join(interm)
    try:
        candidate.encode(canonical_cp)
        return candidate
    except UnicodeEncodeError:
        # Final safety net: strictly filter unencodables rather than raising or producing '?'
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
    """Formats a single GDT line: LLLLFFFFDDDD...\\r\\n with strict 4-digit tag and exact byte length."""
    if len(tag) != 4 or not tag.isdigit():
        raise ValueError(f"GDT Tag must be exactly 4 digits: {tag!r}")

    # Remove inline line breaks
    clean_val = str(value).replace("\r", " ").replace("\n", " ").strip()
    canonical_cp = codepage.lower().replace("_", "-")
    trans_val = transliterate_to_codepage(clean_val, canonical_cp)
    val_bytes = trans_val.encode(canonical_cp)

    # Line byte count: 4 (LLLL) + 4 (FFFF) + len(val_bytes) + 2 (\r\n) = len(val_bytes) + 10
    total_line_len = len(val_bytes) + 10
    if total_line_len > 9999:
        val_bytes = val_bytes[: 9999 - 10]
        total_line_len = 9999

    prefix = f"{total_line_len:04d}{tag}".encode(canonical_cp)
    return prefix + val_bytes + b"\r\n"


def build_gdt_6302_payload(
    data: dict[str, Any],
    codepage: str = "cp437",
    sender_id: str = "ORDINFLOW",
    receiver_id: str = "PVS",
) -> bytes:
    """Builds a complete, specification-compliant GDT Satzart 6302 (Befundübermittlung) payload."""
    canonical_cp = codepage.lower().replace("_", "-")
    charset_code = GDT_CODEPAGE_TAGS.get(canonical_cp, "1")

    # Header tags
    line_8000 = format_gdt_line("8000", "6302", canonical_cp)  # Satzart 6302
    line_9218 = format_gdt_line("9218", "02.10", canonical_cp)  # GDT Version 2.10
    line_9206 = format_gdt_line("9206", charset_code, canonical_cp)  # Zeichensatz
    line_8402 = format_gdt_line("8402", str(sender_id)[:8], canonical_cp)  # Sender
    line_8316 = format_gdt_line("8316", str(receiver_id)[:8], canonical_cp)  # Empfänger

    # Patient tags
    pat_id = str(data.get("PatientID") or data.get("PatientenNr") or data.get("ID") or data.get("id") or "").strip()
    if not pat_id:
        raise ValueError("GDT Satzart 6302 requires a non-empty Patient ID (Tag 3000).")

    last_name = str(data.get("Nachname") or data.get("LastName") or data.get("Name") or "").strip()
    first_name = str(data.get("Vorname") or data.get("FirstName") or "").strip()
    birth_date = normalize_gdt_date(data.get("Geburtsdatum") or data.get("DOB") or data.get("Geburtstag") or "")
    insurance = normalize_insurance_status(data.get("Versicherungsstatus") or data.get("Versicherung") or data.get("Status"))

    line_3000 = format_gdt_line("3000", pat_id, canonical_cp)
    line_3101 = format_gdt_line("3101", last_name, canonical_cp) if last_name else None
    line_3102 = format_gdt_line("3102", first_name, canonical_cp) if first_name else None
    line_3103 = format_gdt_line("3103", birth_date, canonical_cp) if birth_date else None
    line_3105 = format_gdt_line("3105", insurance, canonical_cp)

    # Befund / Examination tags
    exam_date = normalize_gdt_date(data.get("Befunddatum") or data.get("Datum") or data.get("Date") or "")
    exam_time = normalize_gdt_time(data.get("Befundzeit") or data.get("Uhrzeit") or data.get("Time") or "")

    line_6200 = format_gdt_line("6200", exam_date, canonical_cp)
    line_6201 = format_gdt_line("6201", exam_time, canonical_cp)

    body_lines: list[bytes] = [
        line_8000,
        # Tag 8100 placeholder inserted later
        line_9218,
        line_9206,
        line_8402,
        line_8316,
        line_3000,
    ]
    if line_3101:
        body_lines.append(line_3101)
    if line_3102:
        body_lines.append(line_3102)
    if line_3103:
        body_lines.append(line_3103)
    body_lines.append(line_3105)
    body_lines.append(line_6200)
    body_lines.append(line_6201)

    # Befund text lines (wrapped to 70 chars)
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
    # Tag 8100 line is fixed at 18 bytes: "0018" + "8100" + 8-digit size + "\r\n"
    tag_8100_fixed_len = 18
    other_lines_bytes = sum(len(b) for b in body_lines)
    total_bytes = other_lines_bytes + tag_8100_fixed_len
    line_8100 = f"00188100{total_bytes:08d}\r\n".encode(canonical_cp)

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

    payload = build_gdt_6302_payload(
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
