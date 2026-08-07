from typing import Any, cast

from core.config import AppConfig
from core.routing import render_filename, render_folder_name


def test_rezept_verordnetes_produkt_naming():
    # Load configuration
    config = AppConfig()
    config.load_from_yaml()

    # 1. Simulate data extracted from a Rezept
    rezept_data = {
        "Dokument": "Rezept",
        "RezeptDatum": "2026-04-09",
        "Nachname": "Schuster",
        "Vorname": "Erika",
        "Titel": "[FEHLT]",
        "Verordnung": "Maßschuhe",
    }

    # Get config for Rezept
    doc_info = config.document_types.get("Rezept")
    assert doc_info is not None

    routing_cfg = cast(dict[str, Any], doc_info.get("routing", {}))
    validation_cfg = cast(dict[str, Any], doc_info.get("validation", {}))
    optional_fields = set(validation_cfg.get("optional_fields", []))

    # 2. Render folder name
    # The folder template relies on {Produkt}, which is missing from rezept_data
    # Because Produkt is not optional, it should resolve to "Produkt-MISSING"
    folder_name = render_folder_name(
        rezept_data,
        routing_cfg=routing_cfg,
        optional_fields=optional_fields,
        folder_structure=config.folder_structure,
        delimiter=config.folder_delimiter,
    )

    # It should NOT contain "Maßschuhe" but it SHOULD contain "----"
    assert "Maßschuhe" not in folder_name
    assert "----" in folder_name
    assert "Schuster" in folder_name
    assert "Erika" in folder_name

    # 3. Render filename
    # The filename template is Rezept__{Verordnung}__{Datum}
    filename = render_filename(
        rezept_data,
        routing_cfg=routing_cfg,
        ext=".pdf",
        optional_fields=optional_fields,
    )

    # It should be Rezept__Maßschuhe__2026-04-09.pdf
    assert filename == "Rezept__Maßschuhe__2026-04-09.pdf"
