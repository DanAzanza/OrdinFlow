"""Unit-Tests für OCR-Vorverarbeitung, Voting-Diskrepanz, Dateihashing und Vision-Regeln.

TESTS AUFRUFEN: python -m pytest tests/test_ocr_and_vision.py --tb=no -v
"""

import os
from unittest.mock import patch

# ──────────────────────────────────────────────────────────────
# HIGH VALUE: OCR-Vorverarbeitung (_run_ocr_with_bin_filter)
# ──────────────────────────────────────────────────────────────


def test_extract_page_spatial_and_plain_text_without_image_returns_empty():
    """Without an image, spatial and plain text extraction returns empty strings."""
    from core.extraction_pipeline import _extract_page_spatial_and_plain_text

    spatial, plain = _extract_page_spatial_and_plain_text(None)
    assert spatial == ""
    assert plain == ""


def test_vision_visitenkarte_rules_extracted():
    """Visitenkarten-Richtlinien werden korrekt extrahiert."""
    from core.vision import LLMExtractor

    with patch.object(LLMExtractor, "__init__", lambda self: None):
        extractor = object.__new__(LLMExtractor)
        fake_config = type(
            "FakeConfig",
            (),
            {
                "model_name": "test",
                "num_ctx": 4096,
                "classify_temperature": 0.0,
                "num_predict": 128,
                "document_types": {
                    "visitenkarte": {"classification_desc": "x", "specific_rules": "A" * 60},
                },
            },
        )()
        extractor.config = fake_config  # type: ignore[assignment]

    _, rules = extractor._get_specific_rules_for_doctype("visitenkarte")
    assert len(rules) > 50


def test_vision_befundbogen_rules_extracted():
    """Befundbogen-Richtlinien werden korrekt extrahiert."""
    from core.vision import LLMExtractor

    with patch.object(LLMExtractor, "__init__", lambda self: None):
        extractor = object.__new__(LLMExtractor)
        fake_config = type(
            "FakeConfig",
            (),
            {
                "model_name": "test",
                "num_ctx": 4096,
                "classify_temperature": 0.0,
                "num_predict": 128,
                "document_types": {
                    "befundbogen": {"classification_desc": "befundbogen desc", "specific_rules": "B" * 60}
                },
            },
        )()
        extractor.config = fake_config  # type: ignore[assignment]

    _, rules = extractor._get_specific_rules_for_doctype("befundbogen")
    assert len(rules) > 50


def test_vision_unknown_type_returns_empty_rules():
    """Unbekannter Dokumenttyp liefert keine spezifischen Regeln."""
    from core.vision import LLMExtractor

    with patch.object(LLMExtractor, "__init__", lambda self: None):
        extractor = object.__new__(LLMExtractor)
        fake_config = type(
            "FakeConfig",
            (),
            {
                "model_name": "test",
                "num_ctx": 4096,
                "classify_temperature": 0.0,
                "num_predict": 128,
                "document_types": {},
            },
        )()
        extractor.config = fake_config  # type: ignore[assignment]

    _, rules = extractor._get_specific_rules_for_doctype("irgendwas_unbekanntes")
    assert rules == ""


# ──────────────────────────────────────────────────────────────
# MEDIUM VALUE: Image Preprocessing (Skalierung & Kodierung)
# ──────────────────────────────────────────────────────────────


def test_image_preprocessor_scale_and_encode_returns_base64(processor):
    """Skaliertes Bild wird als Base-64-String zurückgegeben und lässt sich dekodieren."""
    import base64
    import io
    import cv2
    import numpy as np
    from PIL import Image

    dummy_img = cv2.cvtColor(
        np.ones((1200, 1600), dtype=np.uint8) * 128,
        cv2.COLOR_GRAY2BGR,
    )
    b64 = processor.image_preprocessor.scale_and_encode_image(Image.fromarray(dummy_img), max_dim=800)
    assert isinstance(b64, str)
    assert len(b64) > 0

    # Verify that the returned base64 string is a valid decoded image scaled to max_dim 800
    decoded_bytes = base64.b64decode(b64)
    decoded_img = Image.open(io.BytesIO(decoded_bytes))
    assert max(decoded_img.width, decoded_img.height) <= 800


# ──────────────────────────────────────────────────────────────
# MEDIUM VALUE: Dokumentenrouting nach Validierung
# ──────────────────────────────────────────────────────────────


def test_routing_without_signature_marks_pruefen(processor, tmp_path):
    """Vertrag OHNE Unterschrift markiert Datei als 'prüfen'."""
    watch_dir = tmp_path / "Inbox"
    target_dir = tmp_path / "Cases"
    os.makedirs(watch_dir, exist_ok=True)
    os.makedirs(target_dir, exist_ok=True)
    processor.config.watch_dir = str(watch_dir)
    processor.config.target_base_dir = str(target_dir)
    processor.config.document_types["Vertrag"] = {
        "validation": {"signature_required": True},
        "routing": {"archive": True, "filename_template": "Vertrag__{Produkt}__{Datum}"},
    }

    dummy_file = watch_dir / "no_sign.pdf"
    dummy_file.write_text("dummy vertrag", encoding="utf-8")

    mock_extracted = {
        "Document": "Vertrag",
        "Vorname": "Hans",
        "Nachname": "Müller",
        "Datum": "2026-07-01",
        "Produkt": "Software",
        "Signed": False,
        "ocr_text": "Vertrag Hans Müller",
        "page_results": [],
    }

    with patch.object(processor, "extract_hybrid_voting", return_value=mock_extracted):
        processor.process_and_route_file(str(dummy_file))

    # After processing attempt, file should stay in inbox (.meta sidecar created)
    pruefen_files = os.listdir(processor.config.watch_dir)
    assert any(f.endswith(".meta") for f in pruefen_files)


def test_routing_with_missing_name_keeps_in_watch(processor, tmp_path):
    """Document without a name stays in inbox (no destination folder created)."""
    watch_dir = tmp_path / "Inbox"
    target_dir = tmp_path / "Cases"
    os.makedirs(watch_dir, exist_ok=True)
    os.makedirs(target_dir, exist_ok=True)
    processor.config.watch_dir = str(watch_dir)
    processor.config.target_base_dir = str(target_dir)
    processor.config.document_types["Vertrag"] = {
        "extraction_fields": {
            "Vorname": "Vorname",
            "Nachname": "Nachname",
            "Datum": "Datum",
            "Produkt": "Produkt",
        },
        "validation": {"signature_required": True},
        "routing": {
            "archive": True,
            "filename_template": "Vertrag__{Produkt}__{Datum}",
            "match_folder_by": ["Nachname", "Vorname"],
        },
    }

    dummy_file = watch_dir / "no_name.pdf"
    dummy_file.write_text("dummy", encoding="utf-8")

    mock_extracted = {
        "Document": "Vertrag",
        "Vorname": "[MISSING]",
        "Nachname": "[MISSING]",
        "Datum": "2026-07-01",
        "Produkt": "Software",
        "Signed": True,
        "ocr_text": "",
        "page_results": [],
    }

    with patch.object(processor, "extract_hybrid_voting", return_value=mock_extracted):
        processor.process_and_route_file(str(dummy_file))

    # No destination folder should be created (no plausible name)
    assert len(os.listdir(processor.config.target_base_dir)) == 0


def test_extract_hybrid_voting_two_phase_grouping(processor):
    """Testet, dass zusammenhängende Seiten gleichen Typs in Phase 1 gruppiert und in Phase 2 gebündelt verarbeitet werden."""
    mock_images = ["img1", "img2", "img3"]

    def mock_classify(raw_img, idx, *args, **kwargs):
        types = ["Vertrag", "Datenschutzerklärung", "Datenschutzerklärung"]
        return {
            "idx": idx,
            "page_num": idx + 1,
            "raw_img": raw_img,
            "prep_img": raw_img,
            "b64_img": f"b64_{idx}",
            "ocr_text": f"ocr_{idx}",
            "doc_type": types[idx],
            "matched_name": types[idx],
            "matched_info": {},
        }

    doc_calls = []

    def mock_process_doc(document_pages):
        doc_calls.append([p["page_num"] for p in document_pages])
        return {
            "Vorname": "Max",
            "Nachname": "Mustermann",
            "Datum": "2026-07-07",
            "Produkt": "Software",
            "Signed": True,
            "_confidence": {"Vorname": 1.0, "Nachname": 1.0},
        }

    with (
        patch.object(processor.image_preprocessor, "create_source_images", return_value=mock_images),
        patch.object(processor, "_classify_single_page", side_effect=mock_classify),
        patch.object(processor, "_process_document_pages", side_effect=mock_process_doc),
    ):
        final_doc = processor.extract_hybrid_voting("dummy.pdf")

    assert len(doc_calls) == 1
    assert doc_calls[0] == [1, 2, 3]
    assert final_doc["Document"] == "Vertrag+Datenschutzerklärung"
    assert len(final_doc["page_results"]) == 2


def test_optional_field_fehlt_is_cleared_to_empty_string():
    """Prüft, ob ein optionales Feld (z.B. Titel), das als [FEHLT] zurückkommt, automatisch zu '' wird."""
    from core.config import AppConfig
    from core.vision import LLMExtractor

    config = AppConfig()
    config.document_types = {"Lieferschein": {"validation": {"optional_fields": ["Titel"]}}}
    extractor = LLMExtractor(config)

    with patch.object(
        extractor,
        "call_vision_api_json",
        return_value={
            "Nachname": "Mustermann",
            "Vorname": "Max",
            "Titel": "[MISSING]",
            "Datum": "10-07-2026",
            "Produkt": "Software",
        },
    ):
        res = extractor.extract_data_from_images_with_type("base64_img", "Lieferschein")

    assert res["Titel"] == ""
    assert res["Nachname"] == "Mustermann"


def test_call_vision_api_json_repairs_truncated_json():
    """Prüft, ob call_vision_api_json abgeschnittenes JSON mit unvollständigen Strings automatisch parst und repariert."""
    from core.config import AppConfig
    from core.vision import LLMExtractor

    extractor = LLMExtractor(AppConfig())
    truncated_raw = '{\n "Vorname": "Denise",\n "Nachname": "Wesselmann",\n "Signed": true,\n "Rechte_betroffener_Person": "Der Kunde hat das Recht auf'

    with patch.object(extractor, "call_vision_api", return_value=truncated_raw):
        res = extractor.call_vision_api_json({"messages": []})

    assert res is not None
    assert res.get("Vorname") == "Denise"
    assert res.get("Nachname") == "Wesselmann"
    assert res.get("Signed") is True


def test_llm_extractor_preload_and_unload():
    """Tests that LLMExtractor delegates preload and unload cleanly to backend."""
    from unittest.mock import MagicMock

    from core.config import AppConfig
    from core.vision import LLMExtractor

    extractor = LLMExtractor(AppConfig())
    mock_backend = MagicMock()
    extractor._backend = mock_backend

    extractor.preload()
    mock_backend.preload.assert_called_once()

    extractor.unload_backend()
    mock_backend.unload.assert_called_once()


def test_format_result_no_pii_masking():
    """Tests that format_result outputs full patient names and values without *** masking."""
    from core.utils import format_result

    data = {
        "Titel": "Dr.",
        "Vorname": "Viktor",
        "Nachname": "Pannen",
        "Produkt": "Einlagen",
        "Document": "Kostenaufstellung",
        "Datum": "15-04-2026",
        "Signed": True,
    }
    result_str = format_result(data)
    assert "Vorname='Viktor'" in result_str
    assert "Nachname='Pannen'" in result_str
    assert "Dr." in result_str
    assert "V***" not in result_str
    assert "P***" not in result_str


def test_extraction_pipeline_preload():
    """Tests that ExtractionPipeline.preload coordinates LLM, OCR, and fitz preloading."""
    from unittest.mock import MagicMock
    from core.config import AppConfig
    from core.extraction_pipeline import ExtractionPipeline
    from core.image_processing import ImagePreprocessor
    from core.vision import LLMExtractor

    cfg = AppConfig()
    mock_llm = MagicMock(spec=LLMExtractor)
    preprocessor = ImagePreprocessor(cfg)
    pipeline = ExtractionPipeline(cfg, preprocessor, mock_llm)

    pipeline.preload()
    mock_llm.preload.assert_called_once()


def test_build_classification_gbnf_with_german_umlauts_and_symbols():
    """Tests that _build_classification_gbnf generates valid GBNF syntax with umlauts and symbols."""
    from core.vision import _build_classification_gbnf

    doc_types = [
        "Rechnung",
        "Datenschutzerklärung",
        "Rezept / Verordnung",
        'Kostenaufstellung "Privat"',
        "Überweisungsträger",
    ]
    grammar = _build_classification_gbnf(doc_types)

    assert "root ::= opt-ws (" in grammar
    assert "opt-ws ::= [ \\t\\n\\r]?" in grammar
    assert '"Rechnung"' in grammar
    assert '"Datenschutzerklärung"' in grammar
    assert '"Rezept / Verordnung"' in grammar
    assert '"Kostenaufstellung \\"Privat\\""' in grammar
    assert '"Überweisungsträger"' in grammar
    assert '"UNKNOWN"' in grammar
    assert '"LEER"' in grammar
    assert '"EMPTY"' in grammar


def test_build_classification_gbnf_empty_fallback():
    """Tests that _build_classification_gbnf with empty list produces valid fallback grammar."""
    from core.vision import _build_classification_gbnf

    grammar = _build_classification_gbnf([])
    assert "root ::= opt-ws (" in grammar
    assert '"UNKNOWN"' in grammar
    assert '"LEER"' in grammar
    assert '"EMPTY"' in grammar


def test_classify_image_passes_grammar_and_max_tokens_16():
    """Tests that classify_image injects grammar and max_tokens=16 into vision API payload."""
    from unittest.mock import MagicMock
    from core.config import AppConfig
    from core.vision import LLMExtractor

    cfg = AppConfig()
    cfg.document_types = {
        "Arztbrief": {},
        "Rechnung": {},
    }
    extractor = LLMExtractor(cfg)
    extractor.call_vision_api = MagicMock(return_value="Rechnung")

    res = extractor.classify_image("base64_dummy_image_data")

    assert res == {"Document": "Rechnung"}
    extractor.call_vision_api.assert_called_once()
    payload = extractor.call_vision_api.call_args[0][0]
    assert payload.get("max_tokens") == 16
    assert payload.get("temperature") == 0.0
    assert "grammar" in payload
    assert '"Rechnung"' in payload["grammar"]
    assert '"Arztbrief"' in payload["grammar"]
    assert '"UNKNOWN"' in payload["grammar"]


def test_clean_description_text():
    """Tests that _clean_description_text strips thinking tags, markdown, and prefixes."""
    from core.vision import _clean_description_text

    raw = (
        "<think>The image shows a drawing with pencil lines.</think>\n"
        "```markdown\n"
        "Hier ist die Beschreibung: Handschriftliche Notiz mit Bleistiftskizze einer Fußsohle.\n"
        "```"
    )
    cleaned = _clean_description_text(raw)
    assert "<think>" not in cleaned
    assert "```" not in cleaned
    assert "Hier ist die Beschreibung:" not in cleaned
    assert cleaned == "Handschriftliche Notiz mit Bleistiftskizze einer Fußsohle."


def test_describe_image_success():
    """Tests that describe_image generates clean German description with max_tokens=64."""
    from unittest.mock import MagicMock
    from core.config import AppConfig
    from core.vision import LLMExtractor

    extractor = LLMExtractor(AppConfig())
    extractor.call_vision_api = MagicMock(return_value="Ein Scan eines Rezepts mit handschriftlicher Notiz.")

    dummy_b64 = "A" * 150
    desc = extractor.describe_image(dummy_b64, max_tokens=64)

    assert desc == "Ein Scan eines Rezepts mit handschriftlicher Notiz."
    extractor.call_vision_api.assert_called_once()
    payload = extractor.call_vision_api.call_args[0][0]
    assert payload["max_tokens"] == 64
    assert payload["temperature"] == 0.0
    assert len(payload["messages"]) == 2
    assert "system" == payload["messages"][0]["role"]
    assert "Deutsch" in payload["messages"][0]["content"]


def test_describe_image_empty_input_returns_empty():
    """Tests that describe_image with empty or invalid image returns empty string immediately."""
    from unittest.mock import MagicMock
    from core.config import AppConfig
    from core.vision import LLMExtractor

    extractor = LLMExtractor(AppConfig())
    extractor.call_vision_api = MagicMock()

    assert extractor.describe_image("") == ""
    assert extractor.describe_image("   ") == ""
    assert extractor.describe_image("short") == ""
    extractor.call_vision_api.assert_not_called()


def test_classify_single_page_triggers_describe_image_on_unknown():
    """Tests that classify_single_page queries description only when document is UNKNOWN on page 1."""
    import numpy as np
    from unittest.mock import MagicMock
    from core.config import AppConfig
    from core.extraction_pipeline import ExtractionPipeline
    from core.image_processing import ImagePreprocessor
    from core.vision import LLMExtractor

    cfg = AppConfig()
    cfg.document_types = {"Rechnung": {}}
    mock_llm = MagicMock(spec=LLMExtractor)
    mock_llm.classify_image.return_value = {"Document": "UNKNOWN"}
    mock_llm.find_doc_type_config.return_value = ("UNKNOWN", {})
    mock_llm.describe_image.return_value = "Skizze einer orthopädischen Einlage."

    pipeline = ExtractionPipeline(cfg, ImagePreprocessor(cfg), mock_llm)
    dummy_img = np.ones((100, 100, 3), dtype=np.uint8) * 255

    res = pipeline.classify_single_page(dummy_img, idx=0)

    assert res["doc_type"] == "UNKNOWN"
    assert res["matched_name"] == "UNKNOWN"
    assert res["vision_description"] == "Skizze einer orthopädischen Einlage."
    mock_llm.describe_image.assert_called_once()


def test_classify_single_page_skips_describe_image_on_known_doctype():
    """Tests that classify_single_page skips describe_image for recognized document types."""
    import numpy as np
    from unittest.mock import MagicMock
    from core.config import AppConfig
    from core.extraction_pipeline import ExtractionPipeline
    from core.image_processing import ImagePreprocessor
    from core.vision import LLMExtractor

    cfg = AppConfig()
    cfg.document_types = {"Rechnung": {}}
    mock_llm = MagicMock(spec=LLMExtractor)
    mock_llm.classify_image.return_value = {"Document": "Rechnung"}
    mock_llm.find_doc_type_config.return_value = ("Rechnung", {"extraction_fields": {}})
    mock_llm.describe_image = MagicMock()

    pipeline = ExtractionPipeline(cfg, ImagePreprocessor(cfg), mock_llm)
    dummy_img = np.ones((100, 100, 3), dtype=np.uint8) * 255

    res = pipeline.classify_single_page(dummy_img, idx=0)

    assert res["doc_type"] == "Rechnung"
    assert res["matched_name"] == "Rechnung"
    assert res["vision_description"] == ""
    mock_llm.describe_image.assert_not_called()


def test_get_optimal_cpu_threads():
    """Tests that _get_optimal_cpu_threads respects configured threads and calculates physical cores cleanly."""
    from core.llm_backends import _get_optimal_cpu_threads

    # 1. Configured threads > 0 are respected directly
    assert _get_optimal_cpu_threads(4) == 4
    assert _get_optimal_cpu_threads(8) == 8

    # 2. Default calculation (0) returns a positive integer
    threads = _get_optimal_cpu_threads(0)
    assert isinstance(threads, int)
    assert threads >= 1


def test_render_dpi_in_app_config():
    """Tests that AppConfig default render_dpi is 200 and white_border is 21."""
    from core.config import AppConfig

    cfg = AppConfig()
    assert cfg.render_dpi == 200
    assert cfg.white_border == 21



