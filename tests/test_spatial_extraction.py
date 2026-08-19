"""
Unit tests for Dual-Source Tier 1 Spatial Text Extraction, Debouncing, and RPA Error Handling.
"""

from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from core.config import AppConfig
from core.extraction_pipeline import (
    ExtractionPipeline,
    _extract_page_spatial_and_plain_text,
)
from core.skills.executor import SkillExecutor
from core.skills.manager import SkillManager
from core.utils import wait_until_unlocked
from core.vision import LLMExtractor


@pytest.fixture
def sample_config():
    cfg = AppConfig()
    cfg.document_types = {
        "Rechnung": {
            "classification_desc": "Invoices and bills",
            "extraction_fields": {
                "Rechnungsnummer": "Invoice ID",
                "Datum": "Invoice date YYYY-MM-DD",
                "Betrag": "Total amount",
            },
            "validation": {
                "signature_required": True,
                "optional_fields": ["Betrag"],
            },
            "routing": {
                "archive": True,
                "folder_template": "Invoices",
                "filename_template": "{Rechnungsnummer}_{Datum}",
            },
        }
    }
    return cfg


def test_extract_page_spatial_and_plain_text_rapidocr_mock():
    # Test fallback spatial extraction when rapidocr returns mock bounding boxes
    mock_engine = MagicMock()
    mock_engine.return_value = (
        [
            (
                [[100, 50], [300, 50], [300, 80], [100, 80]],
                "Datum: 17.08.2026",
                0.99,
            ),
            (
                [[50, 150], [250, 150], [250, 180], [50, 180]],
                "Rechnungsnummer: RE-2026-001",
                0.98,
            ),
        ],
        None,
    )

    test_img = Image.new("RGB", (1000, 1000), color="white")
    with patch("core.extraction_pipeline._get_rapid_ocr", return_value=mock_engine):
        spatial_text, plain_text = _extract_page_spatial_and_plain_text(test_img)

    assert "[pos: y=0.05, x=0.10] Datum: 17.08.2026" in spatial_text
    assert "[pos: y=0.15, x=0.05] Rechnungsnummer: RE-2026-001" in spatial_text
    assert "Datum: 17.08.2026" in plain_text
    assert "Rechnungsnummer: RE-2026-001" in plain_text


def test_extract_data_from_text_with_type(sample_config):
    llm = LLMExtractor(sample_config)

    spatial_text = (
        "[pos: y=0.05, x=0.80] Datum: 17.08.2026\n"
        "[pos: y=0.15, x=0.10] Rechnungsnummer: INV-999\n"
        "[pos: y=0.85, x=0.70] Betrag: 149.99 EUR\n"
    )

    mock_json = {
        "Rechnungsnummer": "INV-999",
        "Datum": "17.08.2026",
        "Betrag": "149.99",
    }

    with patch.object(llm, "call_vision_api_json", return_value=mock_json):
        result = llm.extract_data_from_text_with_type(spatial_text, "Rechnung")

    assert result["Rechnungsnummer"] == "INV-999"
    assert result["Datum"] == "2026-08-17"  # Normalized date
    assert result["Betrag"] == "149.99"
    assert "Signed" not in result  # Signed is not extracted via text pass


def test_dual_source_tier1_consensus_when_no_signature_needed(sample_config):
    sample_config.document_types["Rechnung"]["validation"]["signature_required"] = False
    preprocessor = MagicMock()
    llm = MagicMock()

    # Tier 1 Vision extraction result
    vision_result = {
        "Rechnungsnummer": "INV-100",
        "Datum": "2026-08-17",
        "Betrag": "50.00",
    }
    # Tier 1 Spatial Text extraction result (agrees with Vision)
    text_result = {
        "Rechnungsnummer": "INV-100",
        "Datum": "2026-08-17",
        "Betrag": "50.00",
    }

    llm.extract_data_from_images_with_type.return_value = vision_result
    llm.extract_data_from_text_with_type.return_value = text_result

    pipeline = ExtractionPipeline(sample_config, preprocessor, llm)

    document_pages = [
        {
            "page_num": 1,
            "matched_name": "Rechnung",
            "matched_info": sample_config.document_types["Rechnung"],
            "spatial_text": "[pos: y=0.1, x=0.1] Rechnungsnummer: INV-100",
            "ocr_text": "INV-100 17.08.2026",
            "b64_img": "dummy_b64",
            "prep_img": None,
        }
    ]

    final_res = pipeline.process_document_pages(document_pages)
    assert final_res is not None
    assert final_res["Rechnungsnummer"] == "INV-100"
    assert final_res["Datum"] == "2026-08-17"
    # All fields validated with >= 2 measurements in Tier 1 -> Tier 2 not needed
    assert llm.extract_data_from_images_with_type.call_count == 1


def test_dual_source_tier1_triggers_tier2_for_single_page_signature(sample_config):
    sample_config.document_types["Rechnung"]["validation"]["signature_required"] = True
    preprocessor = MagicMock()
    llm = MagicMock()

    # Tier 1 Vision extraction result (1 visual measurement for Signed)
    vision_result_t1 = {
        "Rechnungsnummer": "INV-100",
        "Datum": "2026-08-17",
        "Betrag": "50.00",
        "Signed": True,
    }
    # Tier 1 Text extraction (omits Signed)
    text_result = {
        "Rechnungsnummer": "INV-100",
        "Datum": "2026-08-17",
        "Betrag": "50.00",
    }
    # Tier 2 Vision extraction (2nd visual measurement specifically for Signed)
    vision_result_t2 = {
        "Signed": True,
    }

    def vision_mock(img, doc_type, temperature=0.0, target_fields=None):
        if target_fields and "Signed" in target_fields:
            return vision_result_t2
        return vision_result_t1

    llm.extract_data_from_images_with_type.side_effect = vision_mock
    llm.extract_data_from_text_with_type.return_value = text_result

    pipeline = ExtractionPipeline(sample_config, preprocessor, llm)

    document_pages = [
        {
            "page_num": 1,
            "matched_name": "Rechnung",
            "matched_info": sample_config.document_types["Rechnung"],
            "spatial_text": "[pos: y=0.1, x=0.1] Rechnungsnummer: INV-100",
            "ocr_text": "INV-100 17.08.2026",
            "b64_img": "dummy_b64",
            "prep_img": None,
        }
    ]

    final_res = pipeline.process_document_pages(document_pages)
    assert final_res is not None
    assert final_res["Rechnungsnummer"] == "INV-100"
    assert final_res["Datum"] == "2026-08-17"
    assert final_res["Signed"] is True
    # Tier 2 was called specifically for 2nd measurement of Signed
    assert llm.extract_data_from_images_with_type.call_count == 2


def test_dual_source_tier1_disagreement_triggers_tier2(sample_config):
    sample_config.document_types["Rechnung"]["validation"]["signature_required"] = False
    preprocessor = MagicMock()
    llm = MagicMock()

    # Tier 1 Vision returns INV-100
    vision_res_t1 = {"Rechnungsnummer": "INV-100", "Datum": "2026-08-17"}
    # Tier 1 Text returns INV-200 (disagreement!)
    text_res_t1 = {"Rechnungsnummer": "INV-200", "Datum": "2026-08-17"}
    # Tier 2 Vision confirms INV-200
    vision_res_t2 = {"Rechnungsnummer": "INV-200", "Datum": "2026-08-17"}

    def vision_side_effect(img, doc_type, temperature=0.0, target_fields=None):
        if target_fields and "Rechnungsnummer" in target_fields:
            return vision_res_t2
        return vision_res_t1

    llm.extract_data_from_images_with_type.side_effect = vision_side_effect
    llm.extract_data_from_text_with_type.return_value = text_res_t1

    pipeline = ExtractionPipeline(sample_config, preprocessor, llm)

    document_pages = [
        {
            "page_num": 1,
            "matched_name": "Rechnung",
            "matched_info": sample_config.document_types["Rechnung"],
            "spatial_text": "[pos: y=0.1, x=0.1] Rechnungsnummer: INV-200",
            "ocr_text": "INV-200 17.08.2026",
            "b64_img": "dummy_b64",
            "prep_img": None,
        }
    ]

    final_res = pipeline.process_document_pages(document_pages)
    assert final_res is not None
    # Tier 2 was called and resolved the conflict
    assert final_res["Rechnungsnummer"] == "INV-200"
    assert llm.extract_data_from_images_with_type.call_count == 2


def test_wait_until_unlocked_debouncing(tmp_path):
    import fitz

    test_file = tmp_path / "incoming_scan.pdf"
    # Create empty file first
    test_file.write_bytes(b"")

    # While file is 0 bytes, it should not be ready
    assert wait_until_unlocked(str(test_file), retries=2, delay=0.1) is False

    # Write valid PDF content and verify readiness check
    doc = fitz.open()
    doc.new_page()
    doc.save(str(test_file))
    doc.close()

    assert wait_until_unlocked(str(test_file), retries=4, delay=0.1) is True


def test_skill_executor_aborts_and_records_screenshot_on_locator_failure(tmp_path):
    mgr = MagicMock(spec=SkillManager)
    skill_def = {
        "id": "test_rpa",
        "name": "Test RPA",
        "enabled": True,
        "steps": [
            {
                "id": "step_click_missing",
                "action_type": "CLICK",
                "description": "Click non-existent button",
                "locator": {"type": "ocr_exact", "value": "BUTTON_THAT_DOES_NOT_EXIST"},
                "max_retries": 1,
                "retry_delay_s": 0.01,
            },
            {
                "id": "step_should_never_run",
                "action_type": "TYPE_TEXT",
                "text": "Dangerous blindly typed text",
            },
        ],
    }
    mgr.get_skill.return_value = skill_def

    executor = SkillExecutor(mgr)

    dummy_screen = Image.new("RGB", (200, 200), color="blue")
    with patch("core.skills.grounder.SoMGrounder.capture_screen", return_value=dummy_screen):
        success = executor.execute_skill("test_rpa", {})

    # Execution must abort and return False immediately
    assert success is False
