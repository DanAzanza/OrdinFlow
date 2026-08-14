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
        }
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
                }
            ]
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
