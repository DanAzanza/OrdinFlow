"""Automated tests for OrdinFlow German Medical GDT (Gerätedatenträger) Export Engine.

Validates strict adherence to QMS / bvitg GDT 2.1 / 3.0 specification:
- 4-digit tags (FFFF)
- Accurate byte length calculation (LLLL) across CP437 and ISO-8859-15
- Total Satzlänge (Tag 8100) mathematical parity
- Transliteration and ASCII-folding for unencodable characters
- Line wrapping of long Befund reports
- Atomic, non-clobbering disk export
"""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import pytest

from core.skills.engines.gdt_engine import (
    GDTEngine,
    build_gdt_6302_payload,
    export_case_to_gdt,
    format_gdt_line,
    normalize_gdt_date,
    normalize_gdt_time,
    normalize_insurance_status,
    transliterate_to_codepage,
    wrap_gdt_text,
)
from core.skills.models import SkillTask


def test_gdt_line_format_strict_dimensions():
    """Every line must strictly follow LLLLFFFFDDDD...\\r\\n where tag is 4 digits."""
    line = format_gdt_line("8000", "6302", "cp437")
    assert line.endswith(b"\r\n")
    # Length of line in bytes
    byte_len = len(line)
    # First 4 bytes are length ASCII digits
    header_len = int(line[:4].decode("ascii"))
    assert header_len == byte_len
    # Next 4 bytes are tag
    tag = line[4:8].decode("ascii")
    assert tag == "8000"
    # Content
    content = line[8:-2].decode("ascii")
    assert content == "6302"


def test_gdt_invalid_tag_length_raises():
    """3-digit or non-numeric tags must be rejected immediately."""
    with pytest.raises(ValueError, match="Tag must be exactly 4 digits"):
        format_gdt_line("800", "test", "cp437")
    with pytest.raises(ValueError, match="Tag must be exactly 4 digits"):
        format_gdt_line("80000", "test", "cp437")
    with pytest.raises(ValueError, match="Tag must be exactly 4 digits"):
        format_gdt_line("ABCD", "test", "cp437")


def test_gdt_byte_vs_char_length_with_umlauts():
    """In CP437, Umlauts are single bytes (e.g. 0x81, 0x94, 0x84, 0xE1). Byte count must match exactly."""
    line = format_gdt_line("3101", "Müller-Schöneß", "cp437")
    assert len(line) == int(line[:4].decode("ascii"))
    assert b"M\x81ller-Sch\x94ne\xe1" in line


def test_gdt_unencodable_chars_transliteration():
    """Characters outside CP437 (Turkish, Slavic, French, emojis) must transliterate cleanly without '?' corruption."""
    raw_name = "Dr. Françoise Çelik-Milošević 😊"
    trans = transliterate_to_codepage(raw_name, "cp437")
    # Must be encodable to CP437 without raising
    encoded = trans.encode("cp437")
    assert b"?" not in encoded
    # Accents are folded: ç -> c, š -> s, ć -> c
    assert "Francoise" in trans
    assert "Celik" in trans
    assert "Milosevic" in trans


def test_gdt_satzlaenge_8100_convergence():
    """Tag 8100 must mathematically equal the exact total byte count of the whole payload."""
    data = {
        "PatientID": "P12345",
        "Nachname": "Mustermann",
        "Vorname": "Max",
        "Geburtsdatum": "15.03.1980",
        "Befund": "Patient klagt über thorakale Schmerzen seit 3 Tagen. EKG zeigt unauffälligen Sinusrhythmus.",
    }
    payload = build_gdt_6302_payload(data, codepage="cp437")
    total_bytes = len(payload)

    # Extract tag 8100 line (line index 1)
    lines = payload.split(b"\r\n")
    tag_8100_line = lines[1]
    assert tag_8100_line[4:8] == b"8100"
    reported_bytes = int(tag_8100_line[8:].decode("ascii"))
    assert reported_bytes == total_bytes


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
    payload = build_gdt_6302_payload(data)
    # Count occurrences of tag 6220
    count_6220 = sum(1 for line in payload.split(b"\r\n") if len(line) >= 8 and line[4:8] == b"6220")
    assert count_6220 == len(chunks)


def test_gdt_rejects_missing_mandatory_patient_id():
    """GDT Satzart 6302 without Patient ID (Tag 3000) must fail fast."""
    data = {
        "Nachname": "Mustermann",
        "Vorname": "Max",
    }
    with pytest.raises(ValueError, match="non-empty Patient ID"):
        build_gdt_6302_payload(data)


def test_gdt_date_and_time_normalization():
    """Various date and time formats must normalize to DDMMYYYY and HHMMSS."""
    assert normalize_gdt_date("15.03.1980") == "15031980"
    assert normalize_gdt_date("1980-03-15") == "15031980"
    assert normalize_gdt_date("15/03/1980") == "15031980"
    assert normalize_gdt_date("15031980") == "15031980"

    assert normalize_gdt_time("14:30:15") == "143015"
    assert normalize_gdt_time("14:30") == "143000"
    assert normalize_gdt_time("143015") == "143015"

    assert normalize_insurance_status("Privat") == "2"
    assert normalize_insurance_status("PKV") == "2"
    assert normalize_insurance_status("Kasse") == "1"
    assert normalize_insurance_status("GKV") == "1"


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
