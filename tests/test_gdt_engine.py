"""Automated tests for OrdinFlow German Medical GDT 2.1 (Gerätedatenträger) Export Engine.

Validates strict adherence to QMS / bvitg GDT 2.1 specification (Satzart 6310):
- 3-digit line length (LLL = len + 9)
- 4-digit tags (FFFF)
- Satzart 6310 (Daten einer Untersuchung)
- Tag 8315 (Receiver) & Tag 8316 (Sender)
- Tag 9206 (Zeichensatz: 2 = CP437, 3 = ISO 8859-1)
- Accurate byte length calculation across CP437 and ISO-8859-1
- Total Satzlänge (Tag 8100) mathematical parity
- Transliteration and ASCII-folding for unencodable characters
- Line wrapping of long Befund reports (<= 70 chars per 6220 tag)
- Safe handling of missing DOB (omitted, never synthetically injected with today's date)
- Atomic, non-clobbering disk export
"""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import pytest

from core.skills.engines.gdt_engine import (
    GDTEngine,
    build_gdt_6310_payload,
    export_case_to_gdt,
    format_gdt_line,
    normalize_gdt_date,
    normalize_gdt_time,
    transliterate_to_codepage,
    wrap_gdt_text,
)
from core.skills.models import SkillTask


def test_gdt_line_format_strict_3_digit_dimensions():
    """Every line must strictly follow LLLFFFFDDDD...\\r\\n where LLL is 3 digits and FFFF is 4 digits."""
    line = format_gdt_line("8000", "6310", "cp437")
    assert line.endswith(b"\r\n")
    # Length of line in bytes: 3 (LLL) + 4 (8000) + 4 (6310) + 2 (\r\n) = 13 bytes
    byte_len = len(line)
    assert byte_len == 13
    assert line == b"01380006310\r\n"
    # First 3 bytes are length ASCII digits
    header_len = int(line[:3].decode("ascii"))
    assert header_len == byte_len
    # Next 4 bytes are tag
    tag = line[3:7].decode("ascii")
    assert tag == "8000"
    # Content
    content = line[7:-2].decode("ascii")
    assert content == "6310"


def test_gdt_invalid_tag_length_raises():
    """Tags not exactly 4 digits or non-numeric must be rejected immediately."""
    with pytest.raises(ValueError, match="Tag must be exactly 4 digits"):
        format_gdt_line("800", "test", "cp437")
    with pytest.raises(ValueError, match="Tag must be exactly 4 digits"):
        format_gdt_line("80000", "test", "cp437")
    with pytest.raises(ValueError, match="Tag must be exactly 4 digits"):
        format_gdt_line("ABCD", "test", "cp437")


def test_gdt_byte_vs_char_length_with_umlauts():
    """In CP437, Umlauts are single bytes (e.g. 0x81, 0x94, 0x84, 0xE1). Byte count must match exactly."""
    line = format_gdt_line("3101", "Müller-Schöneß", "cp437")
    assert len(line) == int(line[:3].decode("ascii"))
    assert b"M\x81ller-Sch\x94ne\xe1" in line


def test_gdt_unencodable_chars_transliteration():
    """Characters outside CP437 (Turkish, Slavic, French, emojis) must transliterate cleanly without '?' corruption."""
    raw_name = "Dr. Françoise Çelik-Milošević 😊"
    trans = transliterate_to_codepage(raw_name, "cp437")
    encoded = trans.encode("cp437")
    assert b"?" not in encoded
    assert "Francoise" in trans
    assert "Celik" in trans
    assert "Milosevic" in trans


def test_gdt_line_length_overflow_clamping():
    """Values exceeding GDT 2.1 3-digit line bounds (>990 bytes) must clamp at max 999 bytes total."""
    oversized = "A" * 1500
    line = format_gdt_line("6220", oversized, "cp437")
    assert len(line) == 999
    assert line[:3] == b"999"


def test_gdt_satzlaenge_8100_convergence():
    """Tag 8100 must mathematically equal the exact total byte count of the whole payload."""
    data = {
        "PatientID": "P12345",
        "Nachname": "Mustermann",
        "Vorname": "Max",
        "Geburtsdatum": "15.03.1980",
        "Befund": "Patient klagt über thorakale Schmerzen seit 3 Tagen. EKG zeigt unauffälligen Sinusrhythmus.",
    }
    payload = build_gdt_6310_payload(data, codepage="cp437")
    total_bytes = len(payload)

    # Extract tag 8100 line (line index 1 in header)
    lines = payload.split(b"\r\n")
    tag_8100_line = lines[1]
    assert tag_8100_line[3:7] == b"8100"
    reported_bytes = int(tag_8100_line[7:].decode("ascii"))
    assert reported_bytes == total_bytes

    # Check header tags compliance
    assert lines[0] == b"01380006310"  # Satzart 6310
    assert lines[2] == b"014921802.10"  # Version 02.10
    assert lines[3] == b"0128315PVS"    # Receiver ID 8315
    assert lines[4] == b"0178316ORDINFLO"  # Sender ID 8316 (max 8 chars)
    assert lines[5] == b"01092062"     # Charset 2 (CP437)


def test_gdt_befundtext_line_wrapping():
    """Long medical reports must be wrapped into multiple sequential 6220 lines <= 70 chars."""
    long_report = (
        "Die Magnetresonanztomographie des Schädels nativ und mit Kontrastmittel zeigt keine "
        "intrakraniellen Raumforderungen, keine frischen ischämischen Infarktareale und kein "
        "pathologisches Kontrastmittelenhancement. Die inneren und äußeren Liquorräume sind "
        "altersentsprechend regelrecht konfiguriert."
    )
    chunks = wrap_gdt_text(long_report, max_chars=70)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 70

    data = {
        "PatientID": "PAT999",
        "Nachname": "Schmidt",
        "Befund": long_report,
    }
    payload = build_gdt_6310_payload(data)
    count_6220 = sum(1 for line in payload.split(b"\r\n") if len(line) >= 7 and line[3:7] == b"6220")
    assert count_6220 == len(chunks)


def test_gdt_rejects_missing_mandatory_patient_id():
    """GDT Satzart 6310 without Patient ID (Tag 3000) must fail fast."""
    data = {
        "Nachname": "Mustermann",
        "Vorname": "Max",
    }
    with pytest.raises(ValueError, match="Patient ID"):
        build_gdt_6310_payload(data)


def test_gdt_omits_missing_dob_safely():
    """Tag 3103 (DOB) is omitted if missing/invalid, never synthetically injected with today's date."""
    data = {
        "PatientID": "P12345",
        "Nachname": "Mustermann",
        "Vorname": "Max",
        # No Geburtsdatum provided
    }
    payload = build_gdt_6310_payload(data)
    lines = payload.split(b"\r\n")
    # Tag 3103 must NOT be present
    tags = [line[3:7].decode("ascii") for line in lines if len(line) >= 7]
    assert "3103" not in tags
    assert "3000" in tags


def test_gdt_date_and_time_normalization():
    """Various date and time formats normalize to DDMMYYYY and HHMMSS, rejecting invalid values."""
    assert normalize_gdt_date("15.03.1980") == "15031980"
    assert normalize_gdt_date("1980-03-15") == "15031980"
    assert normalize_gdt_date("15/03/1980") == "15031980"
    assert normalize_gdt_date("15031980") == "15031980"
    assert normalize_gdt_date("", allow_fallback=False) is None
    assert normalize_gdt_date("invalid", allow_fallback=False) is None

    assert normalize_gdt_time("14:30:15") == "143015"
    assert normalize_gdt_time("14:30") == "143000"
    assert normalize_gdt_time("143015") == "143015"


def test_gdt_atomic_export_and_semaphore():
    """Exporting to disk must be atomic, produce unique non-clobbered files, and optionally write semaphores."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = str(Path(tmpdir).resolve())
        data = {
            "PatientID": "P100",
            "Nachname": "Weber",
            "Vorname": "Anna",
            "Geburtsdatum": "01.01.1990",
            "Befund": "Laborwerte ohne pathologischen Befund.",
        }

        # Export file 1
        file1 = export_case_to_gdt(data, target_dir=tmp_path, write_semaphore=True)
        assert os.path.isfile(file1)
        assert file1.endswith(".gdt")
        sem1 = file1[:-4] + ".sem"
        assert os.path.isfile(sem1)

        # Export file 2 - must NOT overwrite file 1
        file2 = export_case_to_gdt(data, target_dir=tmp_path, write_semaphore=True)
        assert os.path.isfile(file2)
        assert file1 != file2
        assert os.path.exists(file1)


def test_gdt_engine_base_skill_execution():
    """GDTEngine should execute successfully through the standard BaseSkill interface."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = str(Path(tmpdir).resolve())
        definition = {
            "id": "test_gdt",
            "name": "Test GDT Skill",
            "type": "gdt",
            "target_dir": tmp_path,
        }
        engine = GDTEngine(definition)
        task = SkillTask(
            id="task_1",
            skill_id="test_gdt",
            skill_name="Test GDT Skill",
            skill_type="gdt",
            context={
                "PatientID": "P42",
                "Nachname": "Bauer",
                "Vorname": "Klaus",
            },
        )
        res = engine.execute(task)
        assert res.success is True
        assert res.data is not None
        assert "gdt_file" in res.data
        assert os.path.isfile(res.data["gdt_file"])


def test_gdt_engine_missing_target_dir_fails():
    """GDTEngine must cleanly fail if target_dir is not configured."""
    engine = GDTEngine({"id": "gdt_no_dir", "name": "GDT"})
    task = SkillTask(
        id="task_fail",
        skill_id="gdt_no_dir",
        skill_name="GDT",
        skill_type="gdt",
        context={"PatientID": "P42"},
    )
    res = engine.execute(task)
    assert res.success is False
    assert "missing 'target_dir'" in res.error


def test_gdt_engine_execution_error_handling():
    """GDTEngine must catch and return TaskResult with error when payload creation fails."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = str(Path(tmpdir).resolve())
        engine = GDTEngine({"id": "gdt_err", "name": "GDT", "target_dir": tmp_path})
        task = SkillTask(
            id="task_err",
            skill_id="gdt_err",
            skill_name="GDT",
            skill_type="gdt",
            context={"Nachname": "Mustermann"},
        )
        res = engine.execute(task)
        assert res.success is False
        assert "Patient ID" in res.error


def test_gdt_pdf_path_tags_emitted():
    """Providing PDFPath must emit tags 6227 (path) and 6228 (basename)."""
    data = {
        "PatientID": "P123",
        "PDFPath": "C:\\Praxis\\Befunde\\Report_2026.pdf",
    }
    payload = build_gdt_6310_payload(data)
    lines = payload.split(b"\r\n")
    tags = [line[3:7].decode("ascii") for line in lines if len(line) >= 7]
    assert "6227" in tags
    assert "6228" in tags
    line_6228 = next(line for line in lines if len(line) >= 7 and line[3:7] == b"6228")
    assert b"Report_2026.pdf" in line_6228


def test_gdt_optional_exam_time_tag_6201_omitted_when_absent():
    """Tag 6201 (Untersuchungsuhrzeit) is optional in GDT 2.1 Satzart 6310 and must be omitted if absent."""
    data_no_time = {
        "PatientID": "P456",
        "Nachname": "Mustermann",
        "Datum": "15.03.2026",
    }
    payload_no_time = build_gdt_6310_payload(data_no_time)
    lines_no_time = payload_no_time.split(b"\r\n")
    tags_no_time = [line[3:7].decode("ascii") for line in lines_no_time if len(line) >= 7]
    assert "6200" in tags_no_time  # Mandatory exam date present
    assert "6201" not in tags_no_time  # Optional exam time omitted

    # When explicitly provided, Tag 6201 must be present
    data_with_time = dict(data_no_time, Befundzeit="14:30:00")
    payload_with_time = build_gdt_6310_payload(data_with_time)
    lines_with_time = payload_with_time.split(b"\r\n")
    tags_with_time = [line[3:7].decode("ascii") for line in lines_with_time if len(line) >= 7]
    assert "6201" in tags_with_time
    line_6201 = next(line for line in lines_with_time if len(line) >= 7 and line[3:7] == b"6201")
    assert b"143000" in line_6201


def test_gdt_cp1252_special_chars_normalized():
    """Characters in the Windows-1252 0x80-0x9F range (Euro, quotes, dashes) must normalize cleanly."""
    raw = 'Honorarkosten: 150 € für „Spezialbehandlung“ – inkl. MwSt.'
    trans = transliterate_to_codepage(raw, "iso-8859-1")
    assert "€" not in trans
    assert "EUR" in trans
    assert "„" not in trans
    assert '"Spezialbehandlung"' in trans
    assert "–" not in trans
    assert "-" in trans
    # Verify strict encodability in ISO-8859-1
    encoded = trans.encode("iso-8859-1")
    assert all(b < 0x80 or b > 0x9F for b in encoded)

