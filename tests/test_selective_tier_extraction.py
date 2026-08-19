from unittest.mock import MagicMock

import pytest

from core.config import AppConfig
from core.extraction_pipeline import ExtractionPipeline
from core.vision import LLMExtractor


@pytest.fixture
def mock_preprocessor():
    preprocessor = MagicMock()
    preprocessor.scale_and_encode_image.return_value = "base64_encoded_dummy"
    return preprocessor


@pytest.fixture
def mock_llm_extractor():
    extractor = MagicMock()
    return extractor


def test_run_extraction_tier_skips_pages_without_matching_target_fields(mock_preprocessor, mock_llm_extractor):
    config = AppConfig()
    pipeline = ExtractionPipeline(config=config, image_preprocessor=mock_preprocessor, llm_extractor=mock_llm_extractor)

    group_pages = [
        {
            "page_num": 1,
            "matched_name": "Arztbrief",
            "matched_info": {
                "extraction_fields": {"Patientenname": "Name", "Geburtsdatum": "DOB"},
                "validation": {"signature_required": False},
            },
            "prep_img": MagicMock(),
        },
        {
            "page_num": 2,
            "matched_name": "Datenschutzerklaerung",
            "matched_info": {
                "extraction_fields": {},
                "validation": {"signature_required": True},
            },
            "prep_img": MagicMock(),
        },
    ]

    mock_llm_extractor.extract_data_from_images_with_type.return_value = {"Signed": True}

    # Query only 'Signed' (Tier 2/3 re-query scenario)
    results = pipeline.run_extraction_tier(
        group_pages,
        doc_type="Document",
        dimension=config.tier2_dimension,
        label="Vision-LLM Tier 2",
        target_fields=["Signed"],
    )

    # Page 1 should be skipped (empty dict), Page 2 should be extracted
    assert results == [{}, {"Signed": True}]

    # scale_and_encode_image must only be called ONCE for Page 2
    assert mock_preprocessor.scale_and_encode_image.call_count == 1
    # extract_data_from_images_with_type must only be called ONCE for Page 2
    assert mock_llm_extractor.extract_data_from_images_with_type.call_count == 1
    mock_llm_extractor.extract_data_from_images_with_type.assert_called_once_with(
        "base64_encoded_dummy", "Datenschutzerklaerung", temperature=0.0, target_fields=["Signed"]
    )


def test_run_extraction_tier_skips_page_when_no_signature_needed(mock_preprocessor, mock_llm_extractor):
    config = AppConfig()
    pipeline = ExtractionPipeline(config=config, image_preprocessor=mock_preprocessor, llm_extractor=mock_llm_extractor)

    group_pages = [
        {
            "page_num": 1,
            "matched_name": "Arztbrief",
            "matched_info": {
                "extraction_fields": {"Patientenname": "Name", "Geburtsdatum": "DOB"},
                "validation": {"signature_required": False},
            },
            "prep_img": MagicMock(),
        },
        {
            "page_num": 2,
            "matched_name": "Datenschutzerklaerung",
            "matched_info": {
                "extraction_fields": {},
                "validation": {"signature_required": True},
            },
            "prep_img": MagicMock(),
        },
    ]

    mock_llm_extractor.extract_data_from_images_with_type.return_value = {"Geburtsdatum": "01.01.1980"}

    # Query only 'Geburtsdatum'
    results = pipeline.run_extraction_tier(
        group_pages,
        doc_type="Document",
        dimension=config.tier2_dimension,
        label="Vision-LLM Tier 2",
        target_fields=["Geburtsdatum"],
    )

    # Page 1 extracted, Page 2 skipped
    assert results == [{"Geburtsdatum": "01.01.1980"}, {}]
    assert mock_preprocessor.scale_and_encode_image.call_count == 1
    assert mock_llm_extractor.extract_data_from_images_with_type.call_count == 1


def test_run_text_extraction_tier_skips_pages_without_matching_target_fields(mock_preprocessor, mock_llm_extractor):
    config = AppConfig()
    pipeline = ExtractionPipeline(config=config, image_preprocessor=mock_preprocessor, llm_extractor=mock_llm_extractor)

    group_pages = [
        {
            "page_num": 1,
            "matched_name": "Arztbrief",
            "matched_info": {
                "extraction_fields": {"Patientenname": "Name"},
            },
            "spatial_text": "[pos: y=0.1, x=0.1] Mustermann, Max",
        },
        {
            "page_num": 2,
            "matched_name": "Laborbericht",
            "matched_info": {
                "extraction_fields": {"Laborwert_Hb": "Hb Wert"},
            },
            "spatial_text": "[pos: y=0.5, x=0.1] Hb: 14.2 g/dl",
        },
    ]

    mock_llm_extractor.extract_data_from_text_with_type.return_value = {"Laborwert_Hb": "14.2"}

    results = pipeline.run_text_extraction_tier(
        group_pages,
        doc_type="Document",
        label="Spatial OCR-LLM Pass",
        target_fields=["Laborwert_Hb"],
    )

    # Page 1 skipped, Page 2 extracted
    assert results == [{}, {"Laborwert_Hb": "14.2"}]
    assert mock_llm_extractor.extract_data_from_text_with_type.call_count == 1


def test_extract_data_from_images_early_exit_on_no_matching_fields():
    doc_types = {
        "Laborbericht": {
            "extraction_fields": {"Laborwert_Hb": "Hb Wert"},
            "validation": {"signature_required": False},
        }
    }
    config = AppConfig(document_types=doc_types)
    extractor = LLMExtractor(config)
    extractor.call_vision_api_json = MagicMock()

    # Query target_fields that do NOT exist in Laborbericht
    result = extractor.extract_data_from_images_with_type(
        b64_image="dummy_img",
        doc_type="Laborbericht",
        target_fields=["Patientenname"],
    )

    # Must return empty dict immediately and NOT call LLM API
    assert result == {}
    extractor.call_vision_api_json.assert_not_called()


def test_extract_data_from_text_early_exit_on_no_matching_fields():
    doc_types = {
        "Laborbericht": {
            "extraction_fields": {"Laborwert_Hb": "Hb Wert"},
            "validation": {"signature_required": False},
        }
    }
    config = AppConfig(document_types=doc_types)
    extractor = LLMExtractor(config)
    extractor.call_vision_api_json = MagicMock()

    result = extractor.extract_data_from_text_with_type(
        spatial_text="[pos: y=0.1, x=0.1] Some spatial text content here",
        doc_type="Laborbericht",
        target_fields=["Patientenname"],
    )

    assert result == {}
    extractor.call_vision_api_json.assert_not_called()
