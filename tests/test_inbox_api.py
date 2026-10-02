"""Unit tests for the Inbox Document API routes in OrdinFlow."""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

from tests.conftest import MINIMAL_1PAGE_PDF_BYTES


def test_inbox_listing_empty(client, test_sandbox):
    """GET /api/inbox returns an empty list when watch_dir has no files."""
    res = client.get("/api/inbox")
    assert res.status_code == 200
    assert res.get_json() == []


def test_inbox_listing_populated_and_sidecars(client, test_sandbox):
    """GET /api/inbox lists documents, parses .meta sidecars, and ignores desktop.ini."""
    _, config, _ = test_sandbox
    watch_dir = config.watch_dir

    # 1. Normal document without sidecar
    doc1 = os.path.join(watch_dir, "NormalDoc.pdf")
    with open(doc1, "wb") as f:
        f.write(MINIMAL_1PAGE_PDF_BYTES)

    # 2. Document with .meta sidecar indicating manual review
    doc2 = os.path.join(watch_dir, "ReviewDoc.pdf")
    with open(doc2, "wb") as f:
        f.write(MINIMAL_1PAGE_PDF_BYTES)

    meta2 = doc2 + ".meta"
    with open(meta2, "w", encoding="utf-8") as f:
        json.dump(
            {
                "grund": "Patient ID not found",
                "extracted": {"Nachname": "Mustermann", "Vorname": "Max"},
            },
            f,
        )

    # 3. System files that must be ignored
    desktop_ini = os.path.join(watch_dir, "desktop.ini")
    with open(desktop_ini, "w", encoding="utf-8") as f:
        f.write("[.ShellClassInfo]\nIconResource=...")

    res = client.get("/api/inbox")
    assert res.status_code == 200
    items = res.get_json()
    assert len(items) == 2

    # Verify filenames and ordering
    names = [item["name"] for item in items]
    assert "NormalDoc.pdf" in names
    assert "ReviewDoc.pdf" in names
    assert "desktop.ini" not in names

    # Verify sidecar parsing
    review_item = next(it for it in items if it["name"] == "ReviewDoc.pdf")
    assert review_item["is_review"] is True
    assert review_item["reason"] == "Patient ID not found"
    assert review_item["extracted"]["Nachname"] == "Mustermann"
    assert review_item["preview_url"] == "/api/inbox/preview/ReviewDoc.pdf"
    assert review_item["file_url"] == "/api/file/inbox/ReviewDoc.pdf"

    normal_item = next(it for it in items if it["name"] == "NormalDoc.pdf")
    assert normal_item["is_review"] is False
    assert normal_item["reason"] == ""


def test_file_meta_inbox(client, test_sandbox):
    """GET /api/file/meta/inbox/<filename> returns metadata or 404."""
    _, config, _ = test_sandbox
    watch_dir = config.watch_dir

    doc = os.path.join(watch_dir, "Sample.pdf")
    with open(doc, "wb") as f:
        f.write(MINIMAL_1PAGE_PDF_BYTES)

    # 1. 404 when no meta exists
    res_missing = client.get("/api/file/meta/inbox/Sample.pdf")
    assert res_missing.status_code == 404

    # 2. 200 with JSON when meta exists
    with open(doc + ".meta", "w", encoding="utf-8") as f:
        json.dump({"grund": "Low OCR confidence", "extracted": {"Geburtsdatum": "1990-01-01"}}, f)

    res_found = client.get("/api/file/meta/inbox/Sample.pdf")
    assert res_found.status_code == 200
    data = res_found.get_json()
    assert data["grund"] == "Low OCR confidence"
    assert data["extracted"]["Geburtsdatum"] == "1990-01-01"

    # 3. 404 for non-existent file
    res_not_found = client.get("/api/file/meta/inbox/DoesNotExist.pdf")
    assert res_not_found.status_code == 404


def test_inbox_retry_reprocessing(client, test_sandbox):
    """POST /api/inbox/<filename>/retry removes .meta and enqueues task without thread hijacking."""
    _, config, _ = test_sandbox
    watch_dir = config.watch_dir

    doc = os.path.join(watch_dir, "RetryDoc.pdf")
    with open(doc, "wb") as f:
        f.write(MINIMAL_1PAGE_PDF_BYTES)

    meta_file = doc + ".meta"
    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump({"grund": "Failed before"}, f)

    mock_qm = MagicMock()
    mock_task = MagicMock(id="task_mock_999")
    mock_qm.add_to_queue.return_value = mock_task
    mock_qm.skill_manager.get_default_import_skill.return_value = {"id": "import_eingang"}

    with patch("core.skills.queue.get_skill_queue_manager", return_value=mock_qm):
        res = client.post("/api/inbox/RetryDoc.pdf/retry")
        assert res.status_code == 200
        assert res.get_json() == {"status": "ok", "task_id": "task_mock_999"}

        # Sidecar must be deleted
        assert not os.path.exists(meta_file)
        # Original doc must remain
        assert os.path.exists(doc)
        # Queue must have been triggered
        mock_qm.start_queue.assert_called_once()


def test_inbox_delete_moves_to_trash(client, test_sandbox):
    """DELETE /api/inbox/<filename> safely moves document and sidecar to trash without C-level leaks."""
    _, config, _ = test_sandbox
    watch_dir = config.watch_dir

    doc = os.path.join(watch_dir, "ToDelete.pdf")
    with open(doc, "wb") as f:
        f.write(MINIMAL_1PAGE_PDF_BYTES)

    meta_file = doc + ".meta"
    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump({"grund": "Trash me"}, f)

    trashed_files = []

    def mock_trash(p):
        trashed_files.append(p)
        if os.path.exists(p):
            os.remove(p)

    # Dual-module patching to prevent Windows Recycle Bin C-calls
    with (
        patch("routes.api.inbox_api.send_to_trash", side_effect=mock_trash),
        patch("routes.api.document_helpers.send_to_trash", side_effect=mock_trash),
    ):
        res = client.delete("/api/inbox/ToDelete.pdf")
        assert res.status_code == 200
        assert res.get_json() == {"status": "ok"}
        assert doc in trashed_files
        assert not os.path.exists(doc)
        assert not os.path.exists(meta_file)

    # 404 for non-existent file
    res_404 = client.delete("/api/inbox/NonExistent.pdf")
    assert res_404.status_code == 404


def test_inbox_assign_success_and_traversal_guard(client, test_sandbox):
    """POST /api/inbox/<filename>/assign routes document, cleans sidecar, and blocks path traversal."""
    _, config, _ = test_sandbox
    watch_dir = config.watch_dir
    cases_dir = config.target_base_dir

    doc = os.path.join(watch_dir, "PatientDoc.pdf")
    with open(doc, "wb") as f:
        f.write(MINIMAL_1PAGE_PDF_BYTES)

    meta_file = doc + ".meta"
    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump({"grund": "Need manual assign"}, f)

    # 1. Successful manual assignment
    payload = {
        "document": "Rezept",
        "Person": "Mustermann Max",
        "Datum": "2026-08-15",
        "Produkt": "Einlagen",
    }
    res = client.post("/api/inbox/PatientDoc.pdf/assign", json=payload)
    assert res.status_code == 200
    res_data = res.get_json()
    assert res_data["status"] == "ok"

    # Verify source and meta removed from inbox
    assert not os.path.exists(doc)
    assert not os.path.exists(meta_file)

    # Verify routed file placed in target cases directory
    folder_name = res_data["folder"]
    file_name = res_data["file"]
    target_path = os.path.join(cases_dir, folder_name, file_name)
    assert os.path.exists(target_path)

    # 2. Path traversal attack blocked via URL path
    res_trav = client.post("/api/inbox/..%2F..%2FEscape.pdf/assign", json=payload)
    assert res_trav.status_code in (400, 403, 404)

    # 3. Path traversal attack blocked via folder escape
    with patch("routes.api.inbox_api._render_target_folder", return_value="../../escaped_dir"):
        doc_escape = os.path.join(watch_dir, "EscapeDoc.pdf")
        with open(doc_escape, "wb") as f:
            f.write(MINIMAL_1PAGE_PDF_BYTES)
        res_folder_trav = client.post("/api/inbox/EscapeDoc.pdf/assign", json=payload)
        assert res_folder_trav.status_code == 403


def test_inbox_auto_assign_delimiter_and_meta(client, test_sandbox):
    """POST /api/inbox/<filename>/auto_assign parses delimiters and meta fallback."""
    _, config, _ = test_sandbox
    watch_dir = config.watch_dir

    # 1. Delimiter-based auto-assign
    delim_filename = "Rezept__2026-08-15__Einlagen__Mustermann Max.pdf"
    doc_delim = os.path.join(watch_dir, delim_filename)
    with open(doc_delim, "wb") as f:
        f.write(MINIMAL_1PAGE_PDF_BYTES)

    res_delim = client.post(f"/api/inbox/{delim_filename}/auto_assign")
    assert res_delim.status_code == 200
    assert not os.path.exists(doc_delim)

    # 2. Fallback to .meta sidecar extracted fields when filename has no delimiter
    plain_filename = "Scan_12345.pdf"
    doc_plain = os.path.join(watch_dir, plain_filename)
    with open(doc_plain, "wb") as f:
        f.write(MINIMAL_1PAGE_PDF_BYTES)

    meta_plain = doc_plain + ".meta"
    with open(meta_plain, "w", encoding="utf-8") as f:
        json.dump(
            {
                "extracted": {
                    "Document": "Befund",
                    "Person": "Erika Musterfrau",
                    "Datum": "2026-09-01",
                    "Produkt": "Kompressionsstrümpfe",
                }
            },
            f,
        )

    res_meta = client.post(f"/api/inbox/{plain_filename}/auto_assign")
    assert res_meta.status_code == 200
    assert not os.path.exists(doc_plain)
    assert not os.path.exists(meta_plain)


def test_inbox_preview_and_file_serving(client, test_sandbox):
    """GET preview and raw file endpoints serve valid content and MIME types."""
    _, config, _ = test_sandbox
    watch_dir = config.watch_dir

    doc_name = "PreviewDoc.pdf"
    doc_path = os.path.join(watch_dir, doc_name)
    with open(doc_path, "wb") as f:
        f.write(MINIMAL_1PAGE_PDF_BYTES)

    # 1. Raw file serving
    res_file = client.get(f"/api/file/inbox/{doc_name}")
    assert res_file.status_code == 200
    assert res_file.mimetype == "application/pdf"
    assert res_file.data == MINIMAL_1PAGE_PDF_BYTES

    # 2. PDF Preview thumbnail generation
    res_prev = client.get(f"/api/inbox/preview/{doc_name}")
    assert res_prev.status_code == 200
    assert res_prev.mimetype in ("image/jpeg", "image/png")
    assert len(res_prev.data) > 0


def test_inbox_error_branches_and_processor_integration(client, test_sandbox):
    """Verifies edge case errors: invalid schema, missing required fields, and processor file discard."""
    from routes.state import DashboardState

    _, config, _ = test_sandbox
    watch_dir = config.watch_dir

    doc_name = "EdgeDoc.pdf"
    doc_path = os.path.join(watch_dir, doc_name)
    with open(doc_path, "wb") as f:
        f.write(MINIMAL_1PAGE_PDF_BYTES)

    # 1. Wire up mock processor to verify file discard on retry
    mock_processor = MagicMock()
    mock_processor.processing_files = {doc_path}
    DashboardState.processor = mock_processor

    mock_qm = MagicMock()
    mock_qm.add_to_queue.side_effect = RuntimeError("Queue fault")
    with patch("core.skills.queue.get_skill_queue_manager", return_value=mock_qm):
        res_fail_retry = client.post(f"/api/inbox/{doc_name}/retry")
        assert res_fail_retry.status_code == 500
        assert doc_path not in mock_processor.processing_files

    # 2. Assign with missing required fields / invalid schema
    res_bad_schema = client.post(f"/api/inbox/{doc_name}/assign", json="not a dict")
    assert res_bad_schema.status_code == 400

    # 3. Auto-assign with insufficient metadata
    blank_doc = os.path.join(watch_dir, "Blank.pdf")
    with open(blank_doc, "wb") as f:
        f.write(MINIMAL_1PAGE_PDF_BYTES)
    res_insufficient = client.post("/api/inbox/Blank.pdf/auto_assign")
    assert res_insufficient.status_code == 400
    assert "sufficient data" in res_insufficient.get_json()["error"]

    # 4. Processor discard on delete
    delete_doc = os.path.join(watch_dir, "DeleteDiscard.pdf")
    with open(delete_doc, "wb") as f:
        f.write(MINIMAL_1PAGE_PDF_BYTES)
    mock_processor.processing_files.add(delete_doc)
    with (
        patch("routes.api.inbox_api.send_to_trash"),
        patch("routes.api.document_helpers.send_to_trash"),
    ):
        res_del = client.delete("/api/inbox/DeleteDiscard.pdf")
        assert res_del.status_code == 200
        assert delete_doc not in mock_processor.processing_files

    # 5. Delete OSError returns 500
    with patch("routes.api.inbox_api.send_to_trash", side_effect=OSError("Disk write error")):
        res_del_err = client.delete("/api/inbox/EdgeDoc.pdf")
        assert res_del_err.status_code == 500

