"""Unit tests for automatic OCR validation and confirmation in the extraction pipeline."""

from core.extraction_pipeline import (
    OCR_BOOST_PER_PAGE,
    _evaluate_field_consensus,
    _is_ocr_confirmed,
)


def test_is_ocr_confirmed_token_and_ngram_matching():
    """Tests token-level and n-gram fuzzy matching in OCR confirmation."""
    ocr_page = "Firma Beispiel GmbH Rechnungsdatum: 14.08.2026 Gesamtbetrag 150,00 EUR"

    # Exact single token match
    assert _is_ocr_confirmed("Beispiel", ocr_page) is True
    # Date token
    assert _is_ocr_confirmed("14.08.2026", ocr_page) is True
    # Multi-word n-gram match
    assert _is_ocr_confirmed("Firma Beispiel GmbH", ocr_page) is True
    # Fuzzy match with small typo in OCR
    assert _is_ocr_confirmed("Beispiell", ocr_page) is True
    # Non-existent token
    assert _is_ocr_confirmed("Mustermann", ocr_page) is False


def test_automatic_ocr_validation_boost_in_consensus():
    """Tests that OCR confirmation adds the OCR boost weight in voting consensus."""
    ocr_text = "Name: Anna Müller Datum: 2026-08-14"

    winner, k_score, counts = _evaluate_field_consensus(
        "Nachname",
        [[{"Nachname": "Müller"}]],
        [1396],
        ocr_texts_per_page=[ocr_text],
        is_ocr_validated=True,
    )

    assert winner == "Müller"
    # Base weight 1.0 + OCR boost (0.5)
    assert counts.get("Müller") == 1.0 + OCR_BOOST_PER_PAGE
    assert k_score == 1.0
