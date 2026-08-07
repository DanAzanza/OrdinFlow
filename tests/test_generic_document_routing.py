from core.config import AppConfig
from core.routing import render_filename, render_folder_name


def test_generic_document_naming_and_routing():
    # Load configuration
    config = AppConfig()
    config.load_from_yaml()

    # 1. Simulate data extracted from a document (e.g., invoice/Rechnung)
    doc_data = {
        "Dokument": "Rechnung",
        "RechnungsDatum": "2026-04-09",
        "Nachname": "Schuster",
        "Vorname": "Erika",
        "Titel": "[FEHLT]",
        "Kategorie": "Software",
    }

    routing_cfg = {
        "archive": True,
        "filename_template": "Rechnung__{Kategorie}__{RechnungsDatum}"
    }
    optional_fields = {"Titel"}

    # 2. Render folder name
    # The folder template relies on {Produkt}, which is missing from doc_data
    # Because Produkt is not optional, it should resolve to "----" or missing placeholder
    folder_name = render_folder_name(
        doc_data,
        routing_cfg=routing_cfg,
        optional_fields=optional_fields,
        folder_structure=config.folder_structure,
        delimiter=config.folder_delimiter,
    )

    # It should NOT contain "Software" but it SHOULD contain "----" and person names
    assert "Software" not in folder_name
    assert "----" in folder_name
    assert "Schuster" in folder_name
    assert "Erika" in folder_name

    # 3. Render filename
    filename = render_filename(
        doc_data,
        routing_cfg=routing_cfg,
        ext=".pdf",
        optional_fields=optional_fields,
    )

    # It should render cleanly
    assert filename == "Rechnung__Software__2026-04-09.pdf"
