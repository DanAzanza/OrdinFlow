from typing import Any, cast

from core.config import AppConfig


def test_automatic_ocr_validation_fields():
    """Testet, dass OCR-Validation-Fields automatisch aus den extraction_fields abgeleitet werden."""
    config = AppConfig()
    config.load_from_yaml()

    rezept_cfg = config.document_types.get("Rezept")
    assert rezept_cfg is not None

    extraction_fields = cast(dict[str, Any], rezept_cfg.get("extraction_fields", {}))
    ocr_fields = {f.lower() for f in extraction_fields.keys() if f.lower() != "signed"}

    assert "vorname" in ocr_fields
    assert "nachname" in ocr_fields
    assert "titel" in ocr_fields
    assert "verordnung" in ocr_fields
    assert "rezeptdatum" in ocr_fields
