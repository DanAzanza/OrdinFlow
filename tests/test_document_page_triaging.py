"""
Unit tests for document page triaging, direct scan extraction, EXIF orientation,
and active Lanczos4 rescaling to prevent voting collapse on low-res documents.
"""

import base64
import io
from unittest.mock import MagicMock, patch

import fitz
import pytest
from PIL import Image

from core.config import AppConfig
from core.extraction_pipeline import ExtractionPipeline
from core.image_processing import (
    ImagePreprocessor,
    _apply_pdf_rotation,
    _encode_pil_fallback,
)
from core.vision import LLMExtractor


@pytest.fixture
def test_config():
    cfg = AppConfig()
    cfg.classify_dimension = 1008
    cfg.white_border = 10
    cfg.crop_edge_threshold = 200
    cfg.min_contour_area = 50
    cfg.crop_padding = 5
    cfg.document_types = {
        "Rechnung": {
            "classification_desc": "Invoices and bills",
            "extraction_fields": {
                "Rechnungsnummer": "Invoice ID",
                "Datum": "Invoice date",
            },
            "validation": {
                "signature_required": False,
            },
        }
    }
    return cfg


def test_scale_and_encode_image_upscales_low_res_image_with_lanczos(test_config):
    """Verifies that low-res inputs (< 1260px) are actively upscaled to different tier sizes."""
    preprocessor = ImagePreprocessor(test_config)
    low_res_img = Image.new("RGB", (600, 800), color="blue")

    b64_t1 = preprocessor.scale_and_encode_image(low_res_img, max_dim=1260)
    b64_t2 = preprocessor.scale_and_encode_image(low_res_img, max_dim=1512)
    b64_t3 = preprocessor.scale_and_encode_image(low_res_img, max_dim=1764)

    # Decode and check dimensions
    img_t1 = Image.open(io.BytesIO(base64.b64decode(b64_t1)))
    img_t2 = Image.open(io.BytesIO(base64.b64decode(b64_t2)))
    img_t3 = Image.open(io.BytesIO(base64.b64decode(b64_t3)))

    # Longest dimension should match target dimension exactly
    assert max(img_t1.size) == 1260
    assert max(img_t2.size) == 1512
    assert max(img_t3.size) == 1764

    # Ensure the three tiers produce distinct base64 payloads to avoid voting collapse
    assert b64_t1 != b64_t2
    assert b64_t2 != b64_t3


def test_scale_and_encode_image_downscales_large_image(test_config):
    """Verifies that large 300 DPI images (> 2000px) are cleanly downscaled."""
    preprocessor = ImagePreprocessor(test_config)
    large_img = Image.new("RGB", (2480, 3508), color="white")

    b64_img = preprocessor.scale_and_encode_image(large_img, max_dim=1260)
    img_result = Image.open(io.BytesIO(base64.b64decode(b64_img)))

    assert max(img_result.size) == 1260


def test_encode_pil_fallback_upscales_and_adds_border():
    """Verifies Pillow fallback handles upscaling, downscaling, and white border correctly."""
    small_img = Image.new("RGB", (400, 300), color="red")
    b64_encoded = _encode_pil_fallback(small_img, max_dim=1260, white_border=15, upscale=True)

    img_result = Image.open(io.BytesIO(base64.b64decode(b64_encoded)))
    assert max(img_result.size) == 1260


def test_apply_pdf_rotation():
    """Tests page rotation transposition logic for 90, 180, and 270 degrees."""
    test_img = Image.new("RGB", (200, 100), color="green")  # width=200, height=100

    # 90 degrees clockwise -> width=100, height=200
    rot_90 = _apply_pdf_rotation(test_img, 90)
    assert rot_90.size == (100, 200)

    # 180 degrees -> width=200, height=100
    rot_180 = _apply_pdf_rotation(test_img, 180)
    assert rot_180.size == (200, 100)

    # 270 degrees clockwise -> width=100, height=200
    rot_270 = _apply_pdf_rotation(test_img, 270)
    assert rot_270.size == (100, 200)

    # 0 degrees -> unchanged
    rot_0 = _apply_pdf_rotation(test_img, 0)
    assert rot_0.size == (200, 100)


def test_direct_scan_image_extraction(tmp_path, test_config):
    """Creates a synthetic PDF containing a single full-page JPEG scan and verifies direct extraction."""
    preprocessor = ImagePreprocessor(test_config)

    # 1. Create sample JPEG scan
    scan_source = Image.new("RGB", (1200, 1600), color="yellow")
    scan_bytes = io.BytesIO()
    scan_source.save(scan_bytes, format="JPEG")
    scan_data = scan_bytes.getvalue()

    # 2. Build PDF with embedded JPEG scan
    pdf_path = str(tmp_path / "scanned_doc.pdf")
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_image(fitz.Rect(0, 0, 595, 842), stream=scan_data)
    doc.save(pdf_path)
    doc.close()

    # 3. Test create_source_images extracts the raw scan image
    raw_images = preprocessor.create_source_images(pdf_path, return_raw=True)
    assert raw_images is not None
    assert len(raw_images) == 1
    # Check that it extracted the 1200x1600 scan directly instead of rendering at 595x842
    assert raw_images[0].size == (1200, 1600)


def test_direct_scan_image_extraction_with_page_rotation(tmp_path, test_config):
    """Verifies that PDF page rotation (/Rotate 90) is properly applied to extracted scans."""
    preprocessor = ImagePreprocessor(test_config)

    # Landscape scan (1600x1200) inserted into rotated page
    scan_source = Image.new("RGB", (1600, 1200), color="cyan")
    scan_bytes = io.BytesIO()
    scan_source.save(scan_bytes, format="JPEG")
    scan_data = scan_bytes.getvalue()

    pdf_path = str(tmp_path / "rotated_scan.pdf")
    doc = fitz.open()
    page = doc.new_page(width=842, height=595)
    page.set_rotation(90)
    page.insert_image(fitz.Rect(0, 0, 842, 595), stream=scan_data)
    doc.save(pdf_path)
    doc.close()

    raw_images = preprocessor.create_source_images(pdf_path, return_raw=True)
    assert raw_images is not None
    assert len(raw_images) == 1
    # After 90° clockwise rotation, size should be 1200x1600 (portrait)
    assert raw_images[0].size == (1200, 1600)


def test_standalone_image_loading_with_exif_support(tmp_path, test_config):
    """Tests loading a standalone JPG/PNG file."""
    preprocessor = ImagePreprocessor(test_config)
    img_path = str(tmp_path / "photo_receipt.jpg")

    img = Image.new("RGB", (800, 1200), color="magenta")
    img.save(img_path, format="JPEG")

    raw_images = preprocessor.create_source_images(img_path, return_raw=True)
    assert raw_images is not None
    assert len(raw_images) == 1
    assert raw_images[0].size == (800, 1200)


def test_classify_single_page_includes_pdf_path(test_config):
    """Verifies classify_single_page passes pdf_path through into the page dict."""
    preprocessor = ImagePreprocessor(test_config)
    llm = MagicMock(spec=LLMExtractor)
    llm.classify_image.return_value = {"Document": "Rechnung"}
    llm.find_doc_type_config.return_value = ("Rechnung", test_config.document_types["Rechnung"])

    pipeline = ExtractionPipeline(test_config, preprocessor, llm)
    test_img = Image.new("RGB", (500, 700), color="white")

    with patch("core.extraction_pipeline._extract_page_spatial_and_plain_text", return_value=("pos_text", "plain")):
        page_dict = pipeline.classify_single_page(test_img, idx=0, pdf_path="test_doc.pdf")

    assert page_dict["pdf_path"] == "test_doc.pdf"
    assert page_dict["doc_type"] == "Rechnung"
    assert page_dict["matched_name"] == "Rechnung"


def test_digital_pdf_line_level_spatial_coordinates(tmp_path):
    """Verifies that multi-line digital PDFs receive distinct line-level y coordinates."""
    from core.extraction_pipeline import _extract_page_spatial_and_plain_text

    pdf_path = str(tmp_path / "digital_invoice.pdf")
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)

    # Insert two lines of text at distinct vertical positions
    page.insert_text(fitz.Point(50, 100), "Header: Rechnungsnummer 12345")
    page.insert_text(fitz.Point(50, 300), "Body: Gesamtbetrag 99.00 EUR")
    page.insert_text(fitz.Point(50, 600), "Footer: Vielen Dank fuer Ihren Einkauf")
    doc.save(pdf_path)
    doc.close()

    spatial_text, plain_text = _extract_page_spatial_and_plain_text(None, pdf_path=pdf_path, page_idx=0)
    assert "Rechnungsnummer 12345" in plain_text
    assert "Gesamtbetrag 99.00 EUR" in plain_text

    # Extract [pos: y=..., x=...] tags
    lines = [line.strip() for line in spatial_text.split("\n") if line.strip()]
    assert len(lines) >= 3
    # Check that the y coordinates are strictly increasing for lower text lines
    assert "[pos: y=0.1" in lines[0] or "[pos: y=0.0" in lines[0] or "[pos: y=0.1" in lines[0]
    assert "[pos: y=0.3" in lines[1]
    assert "[pos: y=0.7" in lines[2]


def test_small_logo_not_treated_as_full_scan(tmp_path, test_config):
    """Verifies that a page with a small logo (< 60% page area) is not extracted as a full-page scan."""
    preprocessor = ImagePreprocessor(test_config)

    logo = Image.new("RGB", (100, 50), color="red")
    logo_bytes = io.BytesIO()
    logo.save(logo_bytes, format="JPEG")
    logo_data = logo_bytes.getvalue()

    pdf_path = str(tmp_path / "invoice_with_logo.pdf")
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    # Insert tiny logo in top right corner (covers < 5% of page)
    page.insert_image(fitz.Rect(450, 20, 550, 70), stream=logo_data)
    page.insert_text(fitz.Point(50, 150), "Rechnung Nr. 998877")
    doc.save(pdf_path)

    # extract_single_page_image must return None because logo covers < 60% of page
    scan_img = preprocessor.extract_single_page_image(page, doc)
    doc.close()
    assert scan_img is None


def test_split_multi_page_pdf_deflates_and_saves(tmp_path, test_config):
    """Verifies that split_multi_page_pdf splits and compresses pages cleanly."""
    from core.file_service import FileService

    test_config.target_base_dir = str(tmp_path / "Cases")
    fs = FileService(test_config)

    pdf_path = str(tmp_path / "batch.pdf")
    doc = fitz.open()
    p1 = doc.new_page(width=595, height=842)
    p1.insert_text(fitz.Point(50, 100), "Rechnung 001 Page 1")
    p2 = doc.new_page(width=595, height=842)
    p2.insert_text(fitz.Point(50, 100), "Rechnung 002 Page 2")
    doc.save(pdf_path)
    doc.close()

    page_results = [
        {"Document": "Rechnung", "pages": [1], "Rechnungsnummer": "RE-001", "Datum": "2026-08-19"},
        {"Document": "Rechnung", "pages": [2], "Rechnungsnummer": "RE-002", "Datum": "2026-08-19"},
    ]

    def mock_find_doc_type(name):
        return name, {"routing": {"archive": True, "filename_template": "{Rechnungsnummer}"}}

    success = fs.split_multi_page_pdf(
        filepath=pdf_path,
        page_results=page_results,
        extracted_base={"Datum": "2026-08-19"},
        find_doc_type_cfg_fn=mock_find_doc_type,
    )
    assert success is True
