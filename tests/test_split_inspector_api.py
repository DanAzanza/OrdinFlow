"""Tests for PDF Split Inspector and multi-document slicing."""

import fitz
from routes.api.split_api import _parse_pages_input
from routes.state import DashboardState


def test_parse_pages_input_formats():
    # Number
    assert _parse_pages_input(2, 5) == [2]
    # List of digits
    assert _parse_pages_input(["1", 3, "4"], 5) == [1, 3, 4]
    # Range string
    assert _parse_pages_input("2-4", 5) == [2, 3, 4]
    # Comma-separated with range
    assert _parse_pages_input("1, 3-4", 5) == [1, 3, 4]
    # All / wildcard
    assert _parse_pages_input("all", 3) == [1, 2, 3]
    assert _parse_pages_input("*", 3) == [1, 2, 3]
    # Out-of-range clipping
    assert _parse_pages_input("1-10", 3) == [1, 2, 3]


def test_api_split_inspector_submit(client, tmp_path):
    inbox = tmp_path / "Inbox"
    cases = tmp_path / "Cases"
    inbox.mkdir(parents=True, exist_ok=True)
    cases.mkdir(parents=True, exist_ok=True)

    orig_watch = DashboardState.config.watch_dir
    orig_target = DashboardState.config.target_base_dir
    DashboardState.config.watch_dir = str(inbox)
    DashboardState.config.target_base_dir = str(cases)
    DashboardState.config.folder_structure = ["{Datum}", "{Produkt}", "{Nachname}"]
    DashboardState.config.document_types = {
        "DocA": {
            "routing": {
                "filename_template": "DocA__{Nachname}__{Datum}",
            }
        },
        "DocB": {
            "routing": {
                "filename_template": "DocB__{Nachname}__{Datum}",
            }
        },
    }

    try:
        # Create a multi-page PDF in Inbox
        pdf_path = inbox / "scan_multi.pdf"
        doc = fitz.open()
        p1 = doc.new_page()
        p1.insert_text((50, 50), "Page 1 - DocA")
        p2 = doc.new_page()
        p2.insert_text((50, 50), "Page 2 - DocB")
        doc.save(str(pdf_path))
        doc.close()

        # Submit split into 2 documents
        payload = {
            "context": "inbox",
            "filename": "scan_multi.pdf",
            "documents": [
                {
                    "Document": "DocA",
                    "Nachname": "Smith",
                    "Datum": "2026-08-10",
                    "Produkt": "Software",
                    "pages": "1",
                },
                {
                    "Document": "DocB",
                    "Nachname": "Smith",
                    "Datum": "2026-08-10",
                    "Produkt": "Software",
                    "pages": "2",
                },
            ],
        }

        res = client.post("/api/split_inspector/submit", json=payload)
        assert res.status_code == 200, res.get_json()
        data = res.get_json()
        assert data["status"] == "ok"
        assert len(data["results"]) == 2

        # Verify routed folder & split files
        target_folder = cases / "2026-08-10__Software__Smith"
        assert target_folder.is_dir()
        doc_a_file = target_folder / "DocA__Smith__2026-08-10.pdf"
        doc_b_file = target_folder / "DocB__Smith__2026-08-10.pdf"
        assert doc_a_file.is_file()
        assert doc_b_file.is_file()

        # Verify page counts in split documents
        doc_a = fitz.open(str(doc_a_file))
        assert len(doc_a) == 1
        doc_a.close()

        doc_b = fitz.open(str(doc_b_file))
        assert len(doc_b) == 1
        doc_b.close()

        # Verify source file was cleaned up
        assert not pdf_path.exists()
    finally:
        DashboardState.config.watch_dir = orig_watch
        DashboardState.config.target_base_dir = orig_target


def test_split_inspector_invalid_page_range(client, tmp_path):
    inbox = tmp_path / "Inbox"
    cases = tmp_path / "Cases"
    inbox.mkdir(parents=True, exist_ok=True)
    cases.mkdir(parents=True, exist_ok=True)

    orig_watch = DashboardState.config.watch_dir
    orig_target = DashboardState.config.target_base_dir
    DashboardState.config.watch_dir = str(inbox)
    DashboardState.config.target_base_dir = str(cases)

    try:
        pdf_path = inbox / "scan_test.pdf"
        doc = fitz.open()
        p1 = doc.new_page()
        p1.insert_text((50, 50), "Single Page")
        doc.save(str(pdf_path))
        doc.close()

        # Out-of-bounds page range
        payload = {
            "context": "inbox",
            "filename": "scan_test.pdf",
            "documents": [
                {
                    "Document": "DocA",
                    "pages": "99",
                }
            ],
        }

        res = client.post("/api/split_inspector/submit", json=payload)
        assert res.status_code == 400
        assert "Invalid or empty page range" in res.get_json()["error"]
        assert pdf_path.exists()
    finally:
        DashboardState.config.watch_dir = orig_watch
        DashboardState.config.target_base_dir = orig_target


def test_split_inspector_non_pdf_multi_doc(client, tmp_path):
    inbox = tmp_path / "Inbox"
    inbox.mkdir(parents=True, exist_ok=True)

    orig_watch = DashboardState.config.watch_dir
    DashboardState.config.watch_dir = str(inbox)

    try:
        img_path = inbox / "photo.jpg"
        img_path.write_bytes(b"dummy image bytes")

        payload = {
            "context": "inbox",
            "filename": "photo.jpg",
            "documents": [
                {"Document": "DocA", "pages": "1"},
                {"Document": "DocB", "pages": "2"},
            ],
        }

        res = client.post("/api/split_inspector/submit", json=payload)
        assert res.status_code == 400
        assert "only supported for PDF" in res.get_json()["error"]
        assert img_path.exists()
    finally:
        DashboardState.config.watch_dir = orig_watch


def test_mark_for_review_preserves_page_results(tmp_path):
    import json
    from core.config import AppConfig
    from core.file_service import FileService

    fs = FileService(config=AppConfig())
    test_pdf = tmp_path / "scan_005095.pdf"
    test_pdf.write_bytes(b"fake pdf")

    extracted = {
        "Document": "Fußscan+Zuzahlungsaufstellung",
        "Nachname": "Bramkamp-Wannink",
        "Vorname": "Sylke",
        "images": ["base64_large_data"],
        "page_results": [
            {
                "Document": "Fußscan",
                "pages": [1],
                "Nachname": "Bramkamp-Wannink",
                "Vorname": "Sylke",
                "images": ["large_img_data"],
            },
            {
                "Document": "Zuzahlungsaufstellung",
                "pages": [2],
                "Nachname": "Bramkamp-Wannink",
                "Vorname": "Sylke",
            },
        ],
    }

    fs.mark_for_review(str(test_pdf), reason="Verification required", extracted=extracted)

    meta_file = tmp_path / "scan_005095.pdf.meta"
    assert meta_file.is_file()

    meta_data = json.loads(meta_file.read_text(encoding="utf-8"))
    assert "page_results" in meta_data["extracted"]
    pr = meta_data["extracted"]["page_results"]
    assert len(pr) == 2
    assert pr[0]["Document"] == "Fußscan"
    assert pr[0]["pages"] == [1]
    assert "images" not in pr[0]
    assert pr[1]["Document"] == "Zuzahlungsaufstellung"
    assert pr[1]["pages"] == [2]

