"""Umfassende Tests für die Allgemeingültigkeit und Domänenagnostik des DMS.

Testet verschiedene Einsatzszenarien wie Versicherungsdokumente, Steuer-/Buchhaltung,
Fotosammlungen und Immobilienverwaltung, um sicherzustellen, dass das DMS flexibel
und ohne harte Domänenannahmen funktioniert.
"""

from core.config import AppConfig
from core.routing import (
    parse_folder_name,
    render_filename,
    render_folder_name,
)
from routes.api import _parse_folder_name, _validate_required_api_fields
from routes.state import DashboardState


def test_insurance_domain_routing_and_parsing():
    """Testfall: Versicherungsdokumente (Schadensmeldung, Policen)."""
    data = {
        "Versicherungsnummer": "VN-998877",
        "Schadenstyp": "Wasserschaden",
        "kundenname": "Schmidt, Erika",  # absichtlich kleingeschrieben für Case-Insensitivity-Test
        "Datum": "2026-07-10",
    }
    routing_cfg = {
        "folder_template": "{Datum}--{Schadenstyp}--{Kundenname}",
        "filename_template": "Schadensmeldung_{Versicherungsnummer}_{Datum}",
    }
    folder_structure = ["{Datum}", "{Schadenstyp}", "{Kundenname}"]

    # 1. Ordnernamen generieren
    folder = render_folder_name(data, routing_cfg=routing_cfg, folder_structure=folder_structure)
    assert folder == "2026-07-10--Wasserschaden--Schmidt, Erika"

    # 2. Dateinamen generieren
    filename = render_filename(data, routing_cfg=routing_cfg, ext=".pdf")
    assert filename == "Schadensmeldung_VN-998877_2026-07-10.pdf"

    # 3. Ordnernamen bi-direktional zurückparsen
    parsed = parse_folder_name(folder, folder_structure=folder_structure, delimiter="--")
    assert parsed["Datum"] == "2026-07-10"
    assert parsed["Schadenstyp"] == "Wasserschaden"
    assert parsed["Kundenname"] == "Schmidt, Erika"


def test_tax_and_accounting_domain():
    """Testfall: Steuer- und Buchhaltungsdokumente (Rechnungen, Belege)."""
    data = {
        "Steuerjahr": "2026",
        "Kategorie": "Eingangsrechnung",
        "Lieferant": "Acme Cloud Services GmbH",
        "Belegnummer": "INV-2026-0042",
        "Datum": "10.07.2026",
    }
    folder_structure = ["{Steuerjahr}", "{Kategorie}", "{Lieferant}"]

    # 1. Generierung mit benutzerdefiniertem Trennzeichen '__'
    folder = render_folder_name(data, folder_structure=folder_structure, delimiter="__")
    assert folder == "2026__Eingangsrechnung__Acme Cloud Services GmbH"

    # 2. Parse with delimiter '__'
    parsed = parse_folder_name(folder, folder_structure=folder_structure, delimiter="__")
    assert parsed["Steuerjahr"] == "2026"
    assert parsed["Kategorie"] == "Eingangsrechnung"
    assert parsed["Lieferant"] == "Acme Cloud Services GmbH"

    # 3. Test API required field validation for custom document types
    config = AppConfig()
    config.document_types["Eingangsrechnung"] = {
        "routing": {
            "mapping": {
                "lieferant": "Lieferant",
                "belegnr": "Belegnummer",
            }
        }
    }
    DashboardState.config = config

    # Valid data -> no error
    err = _validate_required_api_fields(data, "Eingangsrechnung")
    assert err is None

    # Incomplete data -> validation error
    empty_data = {"Lieferant": "", "Belegnummer": ""}
    err_missing = _validate_required_api_fields(empty_data, "Eingangsrechnung")
    assert err_missing is not None
    assert "Lieferant" in err_missing and "Belegnummer" in err_missing


def test_creative_photo_archive_domain():
    """Test case: Photo collection / project archive with optional fields."""
    data_with_title = {
        "Projekt": "Alpen-Shooting",
        "Ort": "Innsbruck",
        "Titel": "Sonnenaufgang Gipfel",
    }
    data_without_title = {
        "Projekt": "Alpen-Shooting",
        "Ort": "Innsbruck",
        "Titel": "[MISSING]",
    }
    folder_structure = ["{Projekt}", "{Ort}", "{Titel}"]
    # Test optional field 'Titel'
    folder_full = render_folder_name(data_with_title, folder_structure=folder_structure, optional_fields={"Titel"})
    assert folder_full == "Alpen-Shooting--Innsbruck--Sonnenaufgang Gipfel"

    folder_no_title = render_folder_name(
        data_without_title, folder_structure=folder_structure, optional_fields={"Titel"}
    )
    # Empty optional field should not produce 'Titel-MISSING' and cleans delimiter
    assert "Titel-MISSING" not in folder_no_title
    assert folder_no_title == "Alpen-Shooting--Innsbruck"


def test_real_estate_domain_sanitization():
    """Testfall: Immobilienverwaltung mit Sonderzeichen in Dateipfaden."""
    data = {
        "ObjektID": "OBJ/2026/01",
        "Mieter": 'Müller & "Partner" <GmbH>',
        "Wohnung": "WE: 04 / 2. OG",
        "Document": "Mietvertrag",
    }
    routing_cfg = {
        "folder_template": "{ObjektID}--{Mieter}",
        "filename_template": "{Document}_{ObjektID}_{Wohnung}",
    }

    folder = render_folder_name(data, routing_cfg=routing_cfg)
    filename = render_filename(data, routing_cfg=routing_cfg, ext=".pdf")

    # Ungültige Pfadzeichen (/ : < > ") müssen durch clean_path_component bereinigt sein
    for illegal_char in ["/", "\\", ":", "*", "?", '"', "<", ">", "|"]:
        assert illegal_char not in folder
        assert illegal_char not in filename


def test_dynamic_api_folder_parsing_across_domains():
    """Testfall: Die REST API _parse_folder_name passt sich dynamisch an Config an."""
    config = AppConfig()
    config.folder_delimiter = "::"
    config.folder_structure = [
        "{Abteilung}",
        "{Projektcode}",
        "{Verantwortlicher}",
    ]
    DashboardState.config = config

    folder_name = "F&E::PRJ-2026-X::Dr. Meier, Stefan"
    parsed = _parse_folder_name(folder_name)

    assert parsed["display_title"] == folder_name
    assert parsed["Abteilung"] == "F&E"
    assert parsed["Projektcode"] == "PRJ-2026-X"
    assert parsed["Verantwortlicher"] == "Dr. Meier, Stefan"
