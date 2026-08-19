import datetime

from core.utils import (
    clean_extracted_value,
    clean_path_component,
    format_date_robust,
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


def test_format_date_robust():
    today = datetime.date.today()

    # Valides Format
    valid_date = today - datetime.timedelta(days=10)
    assert format_date_robust(valid_date.strftime("%Y-%m-%d")) == valid_date.strftime("%Y-%m-%d")

    # Deutsches Format (mit Punkt)
    assert format_date_robust(valid_date.strftime("%d.%m.%Y")) == valid_date.strftime("%Y-%m-%d")

    # Deutsches Format (mit Komma als OCR-Fehler)
    d = valid_date.strftime("%d")
    m = valid_date.strftime("%m")
    y = valid_date.strftime("%Y")
    assert format_date_robust(f"{d},{m},{y}") == f"{y}-{m}-{d}"

    # Historische Daten (z.B. Vorjahre / Altabdrücke von 2023) werden als valides Datum formatiert
    old_date = today - datetime.timedelta(days=400)
    assert format_date_robust(old_date.strftime("%Y-%m-%d")) == old_date.strftime("%Y-%m-%d")

    # Zukunftsdaten werden ebenfalls formatiert
    future_date = today + datetime.timedelta(days=40)
    assert format_date_robust(future_date.strftime("%Y-%m-%d")) == future_date.strftime("%Y-%m-%d")

    # Ungültige Kalenderdaten -> ----
    assert format_date_robust("31.02.2026") == "----"

    # Unbekannter String -> ----
    assert format_date_robust("[MISSING]") == "----"


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
