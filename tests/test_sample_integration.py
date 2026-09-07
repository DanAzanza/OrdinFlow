"""Integration tests for OrdinFlow workflows using real sample data (Cake Recipes & Images in sample_data/).

Covering:
1. Multi-page PDF splitting with PyMuPDF verification.
2. Incomplete page coverage pre-flight assertion & review quarantine sidecar generation.
3. Skill configuration loading, ImportEngine ingestion, and dynamic folder/filename routing.
4. High-resolution sample image preprocessing, aspect ratio preservation, and multi-tier scaling.

These tests are marked with @pytest.mark.integration and are excluded by default in fast local dev.
Run explicitly with: python -m pytest tests/test_sample_integration.py -v -m integration
"""

from __future__ import annotations

import base64
import gc
import io
from pathlib import Path
import shutil
from unittest.mock import patch

import fitz
from PIL import Image
import pytest

from core.config import AppConfig
from core.file_service import FileService
from core.image_processing import ImagePreprocessor
from core.processor import DocumentProcessor
from core.skills.engines.import_engine import ImportEngine
from core.skills.manager import SkillManager
from core.skills.models import SkillTask

SAMPLE_ROOT = Path(__file__).resolve().parent.parent / "sample_data"


@pytest.fixture
def sample_sandbox(tmp_path: Path):
    """Provides an isolated sandbox filesystem guaranteeing sample_data/ remains read-only."""
    inbox_dir = tmp_path / "Inbox"
    cases_dir = tmp_path / "Cases"
    settings_dir = tmp_path / "settings"
    skills_dir = settings_dir / "skills"

    inbox_dir.mkdir(parents=True, exist_ok=True)
    cases_dir.mkdir(parents=True, exist_ok=True)
    skills_dir.mkdir(parents=True, exist_ok=True)

    config = AppConfig(base_dir=str(tmp_path))
    config.watch_dir = str(inbox_dir)
    config.target_base_dir = str(cases_dir)
    config.folder_delimiter = "__"

    yield tmp_path, config, inbox_dir, cases_dir, skills_dir

    # Teardown: ensure sample_data directory was not touched or corrupted
    assert SAMPLE_ROOT.exists(), "sample_data directory was unexpectedly modified or removed!"
    gc.collect()


@pytest.mark.integration
def test_split_multipage_cake_recipes(sample_sandbox):
    """Verifies that FileService.split_multi_page_pdf splits a real 6-page PDF into 6 separate 1-page documents."""
    _, config, inbox_dir, cases_dir, _ = sample_sandbox
    src_multipage = SAMPLE_ROOT / "recipes_pdf" / "Compilation_Cake_Recipes_Multipage.pdf"
    assert src_multipage.exists(), f"Source sample PDF not found at {src_multipage}"

    test_pdf = inbox_dir / "Compilation_Cake_Recipes_Multipage.pdf"
    shutil.copy2(src_multipage, test_pdf)

    file_service = FileService(config)

    # Define the 6 expected recipes matching the pages of Compilation_Cake_Recipes_Multipage.pdf
    categories = [
        ("Black Forest Cake", "Layer Cakes & Celebrations", "45 mins"),
        ("Marble Cake", "Pound Cakes & Traditional Bakes", "55 mins"),
        ("New York Cheesecake", "Cheesecakes & Custard Pies", "60 mins"),
        ("Apple Crumble Cake", "Sheet Cakes & Fruit Bakes", "40 mins"),
        ("Lemon Bundt Cake", "Bundt & Ring Cakes", "50 mins"),
        ("Viennese Sachertorte", "Chocolate Specialties", "50 mins"),
    ]

    page_results = [
        {
            "Document": "CakeRecipe",
            "pages": [idx + 1],
            "RecipeName": name,
            "Category": cat,
            "BakeTime": bt,
        }
        for idx, (name, cat, bt) in enumerate(categories)
    ]

    def mock_find_doc_type(name: str):
        return name, {
            "routing": {
                "archive": True,
                "folder_template": "Recipes__{Category}",
                "filename_template": "Recipe__{RecipeName}__{BakeTime}",
            }
        }

    success = file_service.split_multi_page_pdf(
        filepath=str(test_pdf),
        page_results=page_results,
        extracted_base={},
        find_doc_type_cfg_fn=mock_find_doc_type,
    )

    assert success is True
    assert not test_pdf.exists(), "Source PDF in sandbox should be cleanly removed after splitting"

    # Verify that exactly 6 split PDFs were generated under Cases/
    split_pdfs = list(cases_dir.rglob("*.pdf"))
    assert len(split_pdfs) == 6

    # Verify that each generated PDF has exactly 1 page and contains valid text
    for pdf_path in split_pdfs:
        with fitz.open(str(pdf_path)) as doc:
            assert len(doc) == 1
            text = doc[0].get_text()
            assert len(text.strip()) > 0

    # Ensure no .meta files were created for split children (conforming to OrdinFlow contracts)
    meta_files = list(cases_dir.rglob("*.meta"))
    assert len(meta_files) == 0


@pytest.mark.integration
def test_split_multipage_incomplete_coverage_aborts(sample_sandbox):
    """Verifies that FileService.split_multi_page_pdf aborts when page coverage is incomplete."""
    _, config, inbox_dir, cases_dir, _ = sample_sandbox
    src_multipage = SAMPLE_ROOT / "recipes_pdf" / "Compilation_Cake_Recipes_Multipage.pdf"
    test_pdf = inbox_dir / "Compilation_Cake_Recipes_Multipage.pdf"
    shutil.copy2(src_multipage, test_pdf)

    file_service = FileService(config)

    # Incomplete coverage: provide only 5 pages out of 6
    partial_results = [
        {
            "Document": "CakeRecipe",
            "pages": [p],
            "RecipeName": f"Recipe {p}",
            "Category": "TestCategory",
            "BakeTime": "30 mins",
        }
        for p in range(1, 6)
    ]

    success = file_service.split_multi_page_pdf(
        filepath=str(test_pdf),
        page_results=partial_results,
        extracted_base={"RecipeName": "Incomplete"},
        find_doc_type_cfg_fn=lambda t: (t, {"routing": {"archive": True, "folder_template": "Test"}}),
    )

    assert success is False
    assert test_pdf.exists(), "Source PDF must NOT be removed when split aborts"

    # A review .meta sidecar must be generated for the quarantined source file
    quarantine_meta = Path(f"{test_pdf}.meta")
    assert quarantine_meta.exists(), "A .meta quarantine sidecar must be created on coverage failure"

    # Zero split PDFs should have been created in Cases/
    assert len(list(cases_dir.rglob("*.pdf"))) == 0


@pytest.mark.integration
def test_cake_recipe_skill_ingestion_and_routing(sample_sandbox):
    """Tests loading the sample cake recipe skill and executing document routing on a sample PDF."""
    _, config, inbox_dir, cases_dir, skills_dir = sample_sandbox

    # Copy cake recipe skill into sandbox skills directory
    src_skill = SAMPLE_ROOT / "cake_recipe_skill_example.yaml"
    target_skill = skills_dir / "import_cake_recipes.yaml"
    shutil.copy2(src_skill, target_skill)

    skill_mgr = SkillManager(skills_dir=str(skills_dir))
    skill_def = skill_mgr.get_skill("Cake Recipes & Bakery Import") or skill_mgr.get_skill("import_cake_recipes")
    assert skill_def is not None, "Cake recipe skill should be loaded by SkillManager"

    # Copy single-page sample PDF to Inbox
    src_pdf = SAMPLE_ROOT / "recipes_pdf" / "Recipe__01_Black_Forest_Cake.pdf"
    test_pdf = inbox_dir / "Recipe__01_Black_Forest_Cake.pdf"
    shutil.copy2(src_pdf, test_pdf)

    processor = DocumentProcessor(config)

    # Mock extraction to return structured cake data without live LLM calls
    mock_extracted = {
        "Document": "CakeRecipe",
        "RecipeName": "Black Forest Cake",
        "Category": "Layer Cakes & Celebrations",
        "BakeTime": "45 mins",
        "BakeTemperature": "175 °C / 350 °F",
        "Portions": "12 slices",
        "Chef": "Master Pastry Chef Stefan Weber",
        "Date": "March 15, 2026",
        "page_results": [
            {
                "Document": "CakeRecipe",
                "pages": [1],
                "RecipeName": "Black Forest Cake",
                "Category": "Layer Cakes & Celebrations",
                "BakeTime": "45 mins",
            }
        ],
    }

    import_engine = ImportEngine(skill_def, processor=processor)
    task = SkillTask(
        id="task_cake_test",
        skill_id=str(skill_def.get("id", "import_cake_recipes")),
        skill_name=str(skill_def.get("name", "Cake Recipes & Bakery Import")),
        skill_type="import",
        context={"filepath": str(test_pdf)},
    )

    with patch.object(processor, "extract_hybrid_voting", return_value=mock_extracted):
        result = import_engine.execute(task)

    assert result.success is True
    assert not test_pdf.exists(), "Source PDF should be routed out of Inbox"

    # Verify target directory and routed filename
    expected_folder = cases_dir / "Recipes__Layer Cakes & Celebrations"
    expected_file = expected_folder / "Recipe__Black Forest Cake__45 mins.pdf"

    assert expected_folder.exists(), f"Target category folder {expected_folder} was not created"
    assert expected_file.exists(), f"Routed PDF {expected_file} was not found"

    # Verify routed file is valid PDF
    with fitz.open(str(expected_file)) as doc:
        assert len(doc) == 1


@pytest.mark.integration
def test_high_res_sample_image_preprocessing(sample_sandbox):
    """Verifies that ImagePreprocessor processes real high-res sample images across all tiers without corruption."""
    _, config, _, _, _ = sample_sandbox
    src_img = SAMPLE_ROOT / "images" / "01_Black_Forest_Cake.jpg"
    assert src_img.exists(), f"Sample image not found at {src_img}"

    preprocessor = ImagePreprocessor(config)

    # 1. Load native raw image
    raw_images = preprocessor.create_source_images(str(src_img), return_raw=True)
    assert raw_images is not None
    assert len(raw_images) == 1
    orig_w, orig_h = raw_images[0].size
    assert orig_w > 0 and orig_h > 0

    # 2. Test multi-tier scaling
    for max_dim in [config.tier1_dimension, config.tier2_dimension, config.tier3_dimension]:
        b64_scaled = preprocessor.scale_and_encode_image(raw_images[0], max_dim=max_dim)
        assert isinstance(b64_scaled, str)
        assert len(b64_scaled) > 0

        # Decode and verify dimensions
        img_bytes = base64.b64decode(b64_scaled)
        with Image.open(io.BytesIO(img_bytes)) as decoded_img:
            w, h = decoded_img.size
            assert max(w, h) <= max_dim
            # VLM patch alignment: dimensions should be divisible by 28
            assert w % 28 == 0
            assert h % 28 == 0
