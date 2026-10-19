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
from core.voting import cluster_votes, evaluate_field_consensus
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

    from tests.conftest import MINIMAL_1PAGE_PDF_BYTES

    cfg = AppConfig(base_dir=str(tmp_path))
    cfg.watch_dir = str(tmp_path / "Inbox")
    os.makedirs(cfg.watch_dir, exist_ok=True)
    proc = DocumentProcessor(cfg)

    dummy_file = str(tmp_path / "Inbox" / "empty.pdf")
    Path(dummy_file).write_bytes(MINIMAL_1PAGE_PDF_BYTES)

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


def test_distinct_first_names_prevent_false_consensus_clustering():
    """Verifies that different persons with shared surnames are NEVER merged into the same cluster."""
    votes = [("Hans Müller", 1.0), ("Anna Müller", 1.25)]
    clusters = cluster_votes(votes, threshold=0.80)
    assert len(clusters) == 2
    reps = {c["representative"] for c in clusters}
    assert "Hans Müller" in reps
    assert "Anna Müller" in reps


def test_voting_intra_cluster_consistency_discount():
    """Verifies that confidence K is discounted when cluster members diverge (preventing false 1.0 consensus)."""
    # 1. Divergent cluster members: One source had only surname, one had full name
    winner_div, k_div, counts_div = evaluate_field_consensus(
        "PatientName",
        [[{"PatientName": "Anna Müller"}], [{"PatientName": "Müller"}]],
        ["tier1", "text"],
    )
    assert winner_div == "Anna Müller"
    # Even though subsumed into one winning cluster, confidence K must be discounted (< 1.0)
    assert 0.80 <= k_div < 0.95
    assert k_div != 1.0

    # 2. Similar typo/variant: 'Jan Meier' vs 'Jana Maier'
    winner_typo, k_typo, counts_typo = evaluate_field_consensus(
        "PatientName",
        [[{"PatientName": "Jana Maier"}], [{"PatientName": "Jan Meier"}]],
        ["tier1", "text"],
    )
    assert k_typo < 1.0

    # 3. Exact matching members: Unanimous agreement must remain 1.0
    winner_exact, k_exact, counts_exact = evaluate_field_consensus(
        "PatientName",
        [[{"PatientName": "Anna Müller"}], [{"PatientName": "anna müller"}]],
        ["tier1", "text"],
    )
    assert winner_exact == "Anna Müller"
    assert k_exact == 1.0



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

    # Bypass header must NOT bypass token checks anymore
    resp = client.post(
        "/api/cases/approve",
        json={"folder": "Test", "approved": True},
        headers={"Host": "localhost", "X-OrdinFlow-Test-Bypass": "1"},
    )
    assert resp.status_code == 403

    # Sensitive GET endpoints require token
    resp_get_unauth = client.get("/api/log", headers={"Host": "localhost"})
    assert resp_get_unauth.status_code == 403

    # Sensitive GET endpoints succeed with valid token via header
    resp_get_auth = client.get(
        "/api/log",
        headers={"Host": "localhost", "X-OrdinFlow-Token": "valid_secret_token_12345"},
    )
    assert resp_get_auth.status_code == 200

    # Sensitive GET endpoints succeed with valid token via query param
    resp_get_query = client.get(
        "/api/log?token=valid_secret_token_12345",
        headers={"Host": "localhost"},
    )
    assert resp_get_query.status_code == 200

    # Public status endpoint is accessible without token
    resp_status = client.get("/api/status", headers={"Host": "localhost"})
    assert resp_status.status_code == 200

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

    from tests.conftest import MINIMAL_1PAGE_PDF_BYTES

    doc_path = str(tmp_path / "corrupt.pdf")
    Path(doc_path).write_bytes(MINIMAL_1PAGE_PDF_BYTES)

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


def test_extraction_pipeline_does_not_log_pii_at_info_level(caplog, test_sandbox):
    """Verifies that patient names and sensitive fields are never emitted to logs at INFO level."""
    import logging
    from unittest.mock import MagicMock
    from core.extraction_pipeline import ExtractionPipeline
    from core.image_processing import ImagePreprocessor

    _, config, _ = test_sandbox
    config.document_types = {
        "Arztbrief": {
            "classification_desc": "Medical report",
            "extraction_fields": {"Patient": "Full name", "Geburtsdatum": "Date of birth"},
        }
    }
    preprocessor = ImagePreprocessor(config)
    mock_llm = MagicMock()
    mock_llm.extract_data_from_images_with_type.return_value = {
        "Patient": "SecretPatientName123",
        "Geburtsdatum": "01.01.1960",
    }
    mock_llm.extract_data_from_text_with_type.return_value = {
        "Patient": "SecretPatientName123",
        "Geburtsdatum": "01.01.1960",
    }
    pipeline = ExtractionPipeline(config, preprocessor, mock_llm)

    page = {
        "page_num": 1,
        "matched_name": "Arztbrief",
        "matched_info": config.document_types["Arztbrief"],
        "spatial_text": "[pos: y=0.1, x=0.1] SecretPatientName123 01.01.1960",
        "b64_img": "mock_b64",
    }

    caplog.set_level(logging.INFO)
    caplog.clear()

    pipeline.run_extraction_tier([page], "Arztbrief", dimension=1120, label="Vision-LLM Tier 1")
    pipeline.run_text_extraction_tier([page], "Arztbrief")

    # Assert PII strings are strictly absent from INFO-level log output
    assert "SecretPatientName123" not in caplog.text
    assert "01.01.1960" not in caplog.text
    # But structural completion should be logged
    assert "completed (2 fields)" in caplog.text


def test_save_failure_screenshot_pruning(tmp_path):
    """Verifies that prune_failure_screenshots enforces retention limit and deletes oldest files."""
    from core.skills.window_manager import prune_failure_screenshots

    fail_dir = tmp_path / "rpa_failures"
    fail_dir.mkdir(parents=True, exist_ok=True)

    # Create 25 mock screenshot files with distinct timestamps
    for i in range(25):
        f = fail_dir / f"failure_{1000 + i}_step.png"
        f.write_bytes(b"\x89PNG\r\n\x1a\n")
        # Explicitly set mtime
        os.utime(str(f), (1000 + i, 1000 + i))

    assert len(list(fail_dir.glob("*.png"))) == 25

    pruned = prune_failure_screenshots(str(fail_dir), max_count=20)
    assert pruned == 5
    remaining = sorted(list(fail_dir.glob("*.png")))
    assert len(remaining) == 20
    # Oldest 5 files (1000 to 1004) should be deleted
    for i in range(5):
        assert not (fail_dir / f"failure_{1000 + i}_step.png").exists()
    # Newest file should still exist
    assert (fail_dir / "failure_1024_step.png").exists()


def test_multi_page_document_voting_isolation(test_sandbox):
    """Verifies that pages from different document types do not cross-contaminate voting results."""
    from unittest.mock import patch
    from core.processor import DocumentProcessor

    _, config, _ = test_sandbox
    processor = DocumentProcessor(config)

    mock_images = ["img1", "img2"]

    def mock_classify(raw_img, idx, *args, **kwargs):
        types = ["Arztbrief", "Rezept"]
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

    def mock_process_group(doc_type, group_pages):
        if doc_type == "Arztbrief":
            return {"Patient": "Hans Mueller", "Diagnose": "Grippe"}
        return {"Patient": "Anna Schmidt", "Medikament": "Ibuprofen"}

    with (
        patch.object(processor.image_preprocessor, "create_raw_source_images", return_value=mock_images),
        patch.object(processor, "_classify_single_page", side_effect=mock_classify),
        patch.object(processor, "_process_page_group", side_effect=mock_process_group),
    ):
        final_doc = processor.extract_hybrid_voting("batch.pdf")

    assert final_doc is not None
    assert final_doc["Document"] == "Arztbrief+Rezept"
    assert len(final_doc["page_results"]) == 2

    # Group 1 (Arztbrief) must only contain Arztbrief fields
    pr1 = final_doc["page_results"][0]
    assert pr1["Document"] == "Arztbrief"
    assert pr1["Patient"] == "Hans Mueller"
    assert pr1["Diagnose"] == "Grippe"
    assert "Medikament" not in pr1

    # Group 2 (Rezept) must only contain Rezept fields without Arztbrief contamination
    pr2 = final_doc["page_results"][1]
    assert pr2["Document"] == "Rezept"
    assert pr2["Patient"] == "Anna Schmidt"
    assert pr2["Medikament"] == "Ibuprofen"
    assert "Diagnose" not in pr2


def test_condition_evaluator_handles_multiline_strings():
    """Verifies that multiline strings with newlines do not trigger SyntaxError in SafeASTEvaluator."""
    from core.skills.condition_evaluator import evaluate_condition

    context = {
        "report_text": "Header Line\nSecond Paragraph with details\nFooter 2026",
        "single_line": "Simple Value",
    }

    # 1. Quoted placeholder with multiline string
    cond1 = '"{report_text}".startswith("Header")'
    assert evaluate_condition(cond1, context) is True

    # 2. Unquoted placeholder with multiline string
    cond2 = "{report_text}.endswith('2026')"
    assert evaluate_condition(cond2, context) is True

    # 3. Disagreement comparison
    cond3 = "{report_text} == 'Something Else'"
    assert evaluate_condition(cond3, context) is False


def test_cleanup_stale_instance_skips_third_party_process():
    """Verifies that _cleanup_stale_instance never terminates third-party python services without OrdinFlow signature."""
    from unittest.mock import MagicMock, patch
    from main import _cleanup_stale_instance

    mock_netstat = MagicMock()
    mock_netstat.returncode = 0
    mock_netstat.stdout = "  TCP    127.0.0.1:8080         0.0.0.0:0              LISTENING       99999\n"

    mock_tasklist = MagicMock()
    mock_tasklist.returncode = 0
    mock_tasklist.stdout = '"python.exe","99999","Console","1","45,000 K"\n'

    # Third party python service (e.g. jupyter, unrelated flask app)
    mock_powershell = MagicMock()
    mock_powershell.returncode = 0
    mock_powershell.stdout = "C:\\Python312\\python.exe -m jupyter notebook --port 8080\n"

    with (
        patch("subprocess.run") as mock_run,
        patch("sys.platform", "win32"),
    ):
        def side_effect(cmd, *args, **kwargs):
            if cmd[0] == "netstat":
                return mock_netstat
            if cmd[0] == "tasklist":
                return mock_tasklist
            if cmd[0] == "powershell":
                return mock_powershell
            return MagicMock(returncode=0)

        mock_run.side_effect = side_effect
        _cleanup_stale_instance(8080)

        # Confirm taskkill was NEVER invoked
        executed_commands = [call.args[0] for call in mock_run.call_args_list if call.args]
        taskkill_calls = [c for c in executed_commands if c[0] == "taskkill"]
        assert len(taskkill_calls) == 0



