import os
from pathlib import Path

from core.utils import (
    clean_extracted_value,
    clean_path_component,
    is_missing_value,
)


def test_clean_path_component():
    assert clean_path_component("Hans Müller") == "Hans Müller"
    assert clean_path_component("Hans/Müller: ") == "HansMüller"
    assert clean_path_component("Max -- Mustermann") == "Max - Mustermann"
    assert clean_path_component("") == "UNKNOWN"


def test_is_missing_value():
    assert is_missing_value("NONE") is True
    assert is_missing_value("N/A") is True
    assert is_missing_value("[MISSING]") is True
    assert is_missing_value("Hans") is False
    assert is_missing_value("") is True


def test_clean_extracted_value():
    assert clean_extracted_value("\u0131") == "i"
    assert clean_extracted_value(" Test ") == "Test"
    assert clean_extracted_value(None) == "----"


def test_central_routing_module():
    from core.routing import render_filename, render_folder_name

    data = {"Abteilung": "HR", "Mitarbeiter": "Meyer, Hans", "Jahr": "2026"}
    routing_cfg = {
        "filename_template": "{Abteilung}_{Mitarbeiter}_{Jahr}",
    }
    assert render_folder_name(data, folder_structure=["{Abteilung}", "{Mitarbeiter}"]) == "HR--Meyer, Hans"
    assert render_filename(data, routing_cfg, ".pdf") == "HR_Meyer, Hans_2026.pdf"


def test_declarative_folder_structure_and_parsing():
    from core.routing import parse_folder_name, render_folder_name

    data = {"Datum": "2026-07-09", "Produkt": "Software", "Nachname": "Müller", "Vorname": "Max"}
    folder_structure = [
        "{Datum}",
        "{Produkt}",
        "{Nachname}",
        "{Vorname}",
    ]
    rendered = render_folder_name(data, folder_structure=folder_structure, delimiter="--")
    assert rendered == "2026-07-09--Software--Müller--Max"

    parsed = parse_folder_name(rendered, folder_structure=folder_structure, delimiter="--")
    assert parsed["Datum"] == "2026-07-09"
    assert parsed["Produkt"] == "Software"
    assert parsed["Nachname"] == "Müller"
    assert parsed["Vorname"] == "Max"


def test_deduplicate_path_no_collision(tmp_path):
    from core.utils import deduplicate_path

    target = str(tmp_path / "new_doc.pdf")
    assert deduplicate_path(target) == target


def test_deduplicate_path_with_collision_same_second(tmp_path):
    from core.utils import deduplicate_path

    target = tmp_path / "report.pdf"
    target.write_text("orig")

    # First deduplication creates timestamp suffix
    c1 = deduplicate_path(str(target))
    assert c1 != str(target)
    assert c1.endswith(".pdf")
    assert not os.path.exists(c1)

    # Simulate c1 already written in the same second
    Path(c1).write_text("c1")

    # Second deduplication must avoid colliding with c1
    c2 = deduplicate_path(str(target))
    assert c2 != str(target)
    assert c2 != c1
    assert "_1.pdf" in c2 or c2.endswith(".pdf")
    assert not os.path.exists(c2)

    # Simulate c2 written as well
    Path(c2).write_text("c2")
    c3 = deduplicate_path(str(target))
    assert c3 not in (str(target), c1, c2)
    assert not os.path.exists(c3)


def test_deduplicate_path_sidecar_meta(tmp_path):
    from core.utils import deduplicate_path

    meta_target = tmp_path / "invoice.pdf.meta"
    meta_target.write_text("{}")

    deduped_meta = deduplicate_path(str(meta_target))
    assert deduped_meta != str(meta_target)
    # Must preserve .pdf.meta structure for clean pair association
    assert deduped_meta.endswith(".pdf.meta")

