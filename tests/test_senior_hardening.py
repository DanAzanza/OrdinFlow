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
