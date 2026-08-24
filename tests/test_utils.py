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
