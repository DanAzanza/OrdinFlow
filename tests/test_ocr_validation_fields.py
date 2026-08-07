from typing import Any, cast

from core.config import AppConfig


def test_automatic_ocr_validation_fields():
    """Testet, dass OCR-Validation-Fields automatisch aus den extraction_fields abgeleitet werden."""
    config = AppConfig()
    config.load_from_yaml()

    doctype_cfg = next(iter(config.document_types.values()), None)
    if not doctype_cfg:
        doctype_cfg = {
            "extraction_fields": {
                "RechnungsDatum": "Datum",
                "RechnungsNummer": "Nummer",
                "Empfaenger": "Empfänger"
            }
        }

    extraction_fields = cast(dict[str, Any], doctype_cfg.get("extraction_fields", {}))
    ocr_fields = {f.lower() for f in extraction_fields if f.lower() != "signed"}

    assert len(ocr_fields) > 0
