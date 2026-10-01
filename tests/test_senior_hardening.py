"""Comprehensive regression tests verifying senior architectural and security hardening.

Covers:
1. PDF split page coverage assertion (zero data loss on missing pages).
2. AllPagesEmptyError trashing (Recycle Bin preservation).
3. RPA SoMGrounder exact match precedence over substring matches.
4. Name clustering subsumption bonus (complete name wins over fragment).
5. RPA credential masking and clipboard bypass.
6. API Host header validation and session token enforcement.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from flask import Flask

from core.file_service import FileService
from core.skills.grounder import SoMGrounder
from core.state import DashboardState
from core.voting import cluster_votes
from routes.api import api_bp


def test_pdf_split_incomplete_coverage_quarantines_file(tmp_path, test_sandbox):
    """Verifies that split_multi_page_pdf aborts and preserves source if pages are missing."""
    import fitz

    # Create a 3-page PDF
    pdf_path = str(tmp_path / "batch.pdf")
    doc = fitz.open()
    for i in range(3):
        p = doc.new_page(width=500, height=700)
        p.insert_text((50, 50), f"Page {i + 1}")
    doc.save(pdf_path)
    doc.close()

    _, config, _ = test_sandbox
    fs = FileService(config)

    # Only provide coverage for page 1 and page 3 (Page 2 is missing!)
    incomplete_pages = [
        {"Document": "Rezept", "pages": [1]},
        {"Document": "Befund", "pages": [3]},
    ]

    success = fs.split_multi_page_pdf(
        filepath=pdf_path,
        page_results=incomplete_pages,
        extracted_base={"Datum": "2026-03-01", "Person": "Mustermann"},
        find_doc_type_cfg_fn=lambda t: (t, {}),
    )

    # 1. Split must fail
    assert success is False
    # 2. Source file must NOT be deleted
    assert os.path.exists(pdf_path)
    # 3. .meta quarantine file must exist
    meta_path = f"{pdf_path}.meta"
    assert os.path.exists(meta_path)
    with open(meta_path, encoding="utf-8") as f:
        meta_content = f.read()
    assert "uncovered pages" in meta_content.casefold() or "incomplete page coverage" in meta_content.casefold()
    assert "2" in meta_content


def test_empty_document_moved_to_trash(tmp_path):
    """Verifies that AllPagesEmptyError calls trash_source_with_meta."""
    from core.config import AppConfig
    from core.processor import AllPagesEmptyError, DocumentProcessor

    cfg = AppConfig(base_dir=str(tmp_path))
    cfg.watch_dir = str(tmp_path / "Inbox")
    os.makedirs(cfg.watch_dir, exist_ok=True)
    proc = DocumentProcessor(cfg)

    dummy_file = str(tmp_path / "Inbox" / "empty.pdf")
    Path(dummy_file).write_bytes(b"%PDF-1.4\n%EOF\n")

    with (
        patch.object(proc, "extract_hybrid_voting", side_effect=AllPagesEmptyError("Empty pages")),
        patch("core.processor.trash_source_with_meta") as mock_trash,
    ):
        res = proc.process_and_route_file(dummy_file)
        assert res is True
        mock_trash.assert_called_once_with(dummy_file)


def test_grounder_exact_match_precedence():
    """Verifies that an exact OCR match anywhere in the screen beats an earlier substring match."""
    from PIL import Image

    mock_ocr = [
        ([[10, 10], [50, 10], [50, 30], [10, 30]], "Sub Term Extra", 0.9),
        ([[100, 100], [140, 100], [140, 120], [100, 120]], "Term", 0.95),
    ]

    with (
        patch.object(SoMGrounder, "capture_screen", return_value=Image.new("RGB", (200, 200))),
        patch("core.image_processing.run_rapid_ocr", return_value=mock_ocr),
    ):
        locator = {"type": "ocr_text", "value": "Term", "offset": [0, 0]}
        coords = SoMGrounder.locate_target(locator)
        assert coords is not None
        assert coords[0] == 120
        assert coords[1] == 110


def test_subsumption_string_clustering():
    """Verifies that a complete informative string wins over a shorter token subset."""
    votes = [("Max", 1.5), ("Max Mustermann", 1.25)]
    clusters = cluster_votes(votes, threshold=0.75)
    assert len(clusters) == 1
    assert clusters[0]["representative"] == "Max Mustermann"


def test_action_executor_masks_secret_and_disables_clipboard():
    """Verifies that sensitive credentials force use_clipboard = False."""
    from core.skills.action_executor import execute_type_text

    step = {
        "text": "MySecretPassword123!",
        "is_secret": True,
        "use_clipboard": True,
    }

    with (
        patch("core.skills.action_executor.paste_text_via_clipboard") as mock_paste,
        patch("core.skills.action_executor.type_unicode_text") as mock_type,
    ):
        res = execute_type_text(
            step=step,
            step_id="step_1",
            action_type="TYPE_TEXT",
            context={},
            substitute_fn=lambda t, c: t,
        )
        assert res is True
        mock_paste.assert_not_called()
        mock_type.assert_called_once_with("MySecretPassword123!", press_enter=False)


def test_api_token_and_host_validation():
    """Verifies Host header and session token validation in production mode."""
    test_app = Flask(__name__)
    test_app.config["TESTING"] = False
    test_app.register_blueprint(api_bp)

    DashboardState.session_token = "valid_secret_token_12345"

    client = test_app.test_client()

    resp = client.get("/api/status", headers={"Host": "attacker.com"})
    assert resp.status_code == 403

    resp = client.post("/api/cases/approve", json={"folder": "Test", "approved": True}, headers={"Host": "localhost"})
    assert resp.status_code == 403

    resp = client.post(
        "/api/cases/approve",
        json={"folder": "Test", "approved": True},
        headers={"Host": "localhost", "X-OrdinFlow-Token": "wrong_token"},
    )
    assert resp.status_code == 403

    resp = client.post(
        "/api/cases/approve",
        json={"folder": "Test", "approved": True},
        headers={"Host": "localhost", "X-OrdinFlow-Token": "valid_secret_token_12345"},
    )
    assert resp.status_code != 403


def test_save_filtered_pdf_deduplicates_and_prevents_overwrite(tmp_path, test_sandbox):
    """Verifies that save_filtered_pdf deduplicates destination path to prevent overwriting existing files."""
    import fitz

    # Create a 2-page source PDF
    src_path = str(tmp_path / "source.pdf")
    doc = fitz.open()
    doc.new_page(width=400, height=600).insert_text((50, 50), "Page 1 - Content")
    doc.new_page(width=400, height=600).insert_text((50, 50), "Page 2 - Empty")
    doc.save(src_path)
    doc.close()

    # Pre-create conflicting target file with distinct content
    target_dir = tmp_path / "Target"
    target_dir.mkdir(parents=True, exist_ok=True)
    conflict_path = str(target_dir / "report.pdf")
    with open(conflict_path, "w", encoding="utf-8") as f:
        f.write("DO_NOT_OVERWRITE_PREVIOUS_VERSION")

    _, config, _ = test_sandbox
    fs = FileService(config)

    saved_path = fs.save_filtered_pdf(src_path, conflict_path, kept_pages=[1])

    # 1. Must return a valid non-colliding destination path
    assert saved_path is not None
    assert saved_path != conflict_path
    assert os.path.exists(saved_path)

    # 2. Pre-existing target file must remain completely unmodified
    with open(conflict_path, "r", encoding="utf-8") as f:
        assert f.read() == "DO_NOT_OVERWRITE_PREVIOUS_VERSION"

    # 3. Source file must have been safely cleaned up
    assert not os.path.exists(src_path)

    # 4. Filtered PDF must contain exactly 1 page
    with fitz.open(saved_path) as res_doc:
        assert len(res_doc) == 1


def test_save_filtered_pdf_guards_empty_kept_pages_and_samefile(tmp_path, test_sandbox):
    """Verifies safety guards against empty kept pages list and in-place samefile overwrites."""
    import fitz

    src_path = str(tmp_path / "doc.pdf")
    doc = fitz.open()
    doc.new_page(width=400, height=600).insert_text((50, 50), "Page 1")
    doc.save(src_path)
    doc.close()

    _, config, _ = test_sandbox
    fs = FileService(config)

    # Empty kept pages -> must safely abort and return None without crashing PyMuPDF
    res = fs.save_filtered_pdf(src_path, str(tmp_path / "out.pdf"), kept_pages=[])
    assert res is None
    assert os.path.exists(src_path)

    # Samefile in-place -> must safely abort without deleting or corrupting source
    res_same = fs.save_filtered_pdf(src_path, src_path, kept_pages=[1])
    assert res_same is None
    assert os.path.exists(src_path)


def test_mark_for_review_merges_existing_metadata(tmp_path, test_sandbox):
    """Verifies that mark_for_review preserves user annotations and uses non-polluting temp files."""
    import json

    doc_path = str(tmp_path / "invoice.pdf")
    Path(doc_path).write_text("dummy")

    meta_path = f"{doc_path}.meta"
    initial_user_meta = {
        "status": "pending",
        "custom_user_tag": "UrgentReview",
        "doctor_notes": "Needs signature check",
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(initial_user_meta, f)

    _, config, _ = test_sandbox
    fs = FileService(config)

    fs.mark_for_review(doc_path, reason="Missing invoice number", extracted={"Amount": "100"})

    with open(meta_path, "r", encoding="utf-8") as f:
        updated = json.load(f)

    # Status and reason updated
    assert updated["status"] == "review"
    assert updated["reason"] == "Missing invoice number"
    # User-added annotations preserved
    assert updated["custom_user_tag"] == "UrgentReview"
    assert updated["doctor_notes"] == "Needs signature check"
    assert updated["extracted"]["Amount"] == "100"

    # Verify no temp files leaked into directory
    temp_files = list(tmp_path.glob("*.tmp*"))
    assert temp_files == []


def test_processor_unhandled_exception_quarantines_and_tracks_stats(tmp_path, test_sandbox):
    """Verifies that unhandled runtime exceptions in process_and_route_file mark file for review and record stats."""
    import json
    from unittest.mock import MagicMock
    from core.processor import DocumentProcessor

    doc_path = str(tmp_path / "corrupt.pdf")
    Path(doc_path).write_text("corrupt_binary_data")

    _, config, _ = test_sandbox
    processor = DocumentProcessor(config)

    # Simulate an unexpected OCR / PyMuPDF internal runtime crash
    processor.extract_hybrid_voting = MagicMock(side_effect=RuntimeError("Simulated OCR kernel crash"))

    success = processor.process_and_route_file(doc_path)
    assert success is False

    # 1. File must be quarantined with .meta to prevent infinite 5-minute queue reprocessing loops
    meta_path = f"{doc_path}.meta"
    assert os.path.exists(meta_path)
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
    assert meta["status"] == "review"
    assert "Unhandled error: RuntimeError" in meta["reason"]

    # 2. Stats must accurately record the failure without skewing
    stats = processor.get_stats()
    assert stats["total"] == 1
    assert stats["failed"] == 1
    assert stats["success"] == 0

