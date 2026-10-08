"""Comprehensive unit & integration tests for inbox retention (keep_inbox_files)."""

from __future__ import annotations

import json
import os
import time
from unittest.mock import patch

from core.config import AppConfig
from core.file_service import FileService, is_file_processed_and_fresh
from core.processor import DocumentProcessor
from core.skills.engines.import_engine import ImportEngine
from core.skills.models import SkillTask, SkillType
from core.utils import safe_copy
from tests.conftest import MINIMAL_1PAGE_PDF_BYTES


def test_config_keep_inbox_files_default_and_yaml(tmp_path):
    """Verifies that keep_inbox_files defaults to False and serializes properly to/from YAML."""
    cfg_file = tmp_path / "settings" / "config.yaml"
    cfg = AppConfig(base_dir=str(tmp_path))
    assert cfg.keep_inbox_files is False

    cfg.keep_inbox_files = True
    cfg.save_to_yaml(str(cfg_file))

    # Read back
    cfg_loaded = AppConfig(base_dir=str(tmp_path))
    cfg_loaded.load_from_yaml(str(cfg_file))
    assert cfg_loaded.keep_inbox_files is True


def test_safe_copy_and_replace(tmp_path):
    """Verifies safe_copy atomically copies source and preserves source file."""
    src = tmp_path / "source.txt"
    src.write_text("Hello OrdinFlow", encoding="utf-8")
    dst = tmp_path / "target_dir" / "destination.txt"

    assert safe_copy(str(src), str(dst)) is True
    assert src.exists()
    assert dst.exists()
    assert dst.read_text(encoding="utf-8") == "Hello OrdinFlow"


def test_file_service_mark_as_processed_and_freshness(tmp_path):
    """Verifies mark_as_processed sidecar lifecycle, metadata fields, and freshness verification."""
    cfg = AppConfig(base_dir=str(tmp_path))
    fs = FileService(cfg)

    doc = tmp_path / "doc.pdf"
    doc.write_bytes(MINIMAL_1PAGE_PDF_BYTES)

    # 1. Before processing: not processed
    assert is_file_processed_and_fresh(str(doc)) is False
    assert fs.is_file_processed(str(doc)) is False

    # 2. Mark as processed
    target_path = str(tmp_path / "Cases" / "Patient" / "doc.pdf")
    extracted_data = {"Document": "Rezept", "Nachname": "Mueller"}
    res = fs.mark_as_processed(str(doc), extracted=extracted_data, routed_paths=[target_path])
    assert res is True

    # 3. Check sidecar content
    meta_path = str(doc) + ".meta"
    assert os.path.exists(meta_path)
    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)

    assert meta["status"] == "processed"
    assert meta["abgearbeitet"] is True
    assert meta["target_files"] == [target_path]
    assert meta["extracted"]["Document"] == "Rezept"
    assert meta["source_size"] == len(MINIMAL_1PAGE_PDF_BYTES)
    assert meta["source_mtime"] > 0

    # 4. Freshness check: returns True when unmodified
    assert is_file_processed_and_fresh(str(doc)) is True

    # 5. Overwrite source file with newer timestamp & different size: freshness check fails
    time.sleep(1.6)  # Exceed 1.5s tolerance
    doc.write_bytes(MINIMAL_1PAGE_PDF_BYTES + b"\n%ExtraData")
    assert is_file_processed_and_fresh(str(doc)) is False


def test_mark_as_processed_clears_prior_review_reasons(tmp_path):
    """Verifies that marking an existing review file as processed clears error reasons."""
    cfg = AppConfig(base_dir=str(tmp_path))
    fs = FileService(cfg)

    doc = tmp_path / "quarantine.pdf"
    doc.write_bytes(MINIMAL_1PAGE_PDF_BYTES)

    fs.mark_for_review(str(doc), reason="Unreadable barcode")
    meta_path = str(doc) + ".meta"
    with open(meta_path, encoding="utf-8") as f:
        m1 = json.load(f)
    assert m1["status"] == "review"
    assert m1["grund"] == "Unreadable barcode"

    # Now mark as processed
    fs.mark_as_processed(str(doc), extracted={"Document": "Befund"})
    with open(meta_path, encoding="utf-8") as f:
        m2 = json.load(f)
    assert m2["status"] == "processed"
    assert m2["abgearbeitet"] is True
    assert "grund" not in m2
    assert "reason" not in m2


def test_process_and_route_file_retention_single_file(test_sandbox):
    """Verifies that keep_inbox_files=True retains file in Inbox and marks as processed."""
    tmp_dir, config, _ = test_sandbox
    config.keep_inbox_files = True
    proc = DocumentProcessor(config)

    inbox_file = os.path.join(config.watch_dir, "SingleDoc.pdf")
    with open(inbox_file, "wb") as f:
        f.write(MINIMAL_1PAGE_PDF_BYTES)

    mock_extracted = {
        "Document": "Rezept",
        "Nachname": "Mustermann",
        "Vorname": "Erika",
        "Datum": "2026-05-10",
        "Produkt": "Medikament",
    }

    with patch.object(proc, "extract_hybrid_voting", return_value=mock_extracted) as mock_extract:
        success = proc.process_and_route_file(inbox_file)
        assert success is True

        # 1. Source file still exists in Inbox!
        assert os.path.exists(inbox_file)

        # 2. Sidecar .meta exists in Inbox and is marked processed
        meta_path = inbox_file + ".meta"
        assert os.path.exists(meta_path)
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
        assert meta["status"] == "processed"
        assert meta["abgearbeitet"] is True

        # 3. Routed copy exists in Cases
        assert len(meta.get("target_files", [])) == 1
        target_copy = meta["target_files"][0]
        assert os.path.exists(target_copy)
        assert target_copy != inbox_file
        assert config.target_base_dir in target_copy

        # 4. Subsequent processing pass without force skips it (extract not called again)
        calls_before = mock_extract.call_count
        assert proc.process_and_route_file(inbox_file, force=False) is True
        assert mock_extract.call_count == calls_before

        # 5. Forced processing pass re-runs extraction
        assert proc.process_and_route_file(inbox_file, force=True) is True
        assert mock_extract.call_count == calls_before + 1


def test_process_and_route_file_disabled_retention_moves_file(test_sandbox):
    """Verifies that keep_inbox_files=False (default) moves/drains file out of Inbox."""
    tmp_dir, config, _ = test_sandbox
    config.keep_inbox_files = False
    proc = DocumentProcessor(config)

    inbox_file = os.path.join(config.watch_dir, "MovingDoc.pdf")
    with open(inbox_file, "wb") as f:
        f.write(MINIMAL_1PAGE_PDF_BYTES)

    mock_extracted = {
        "Document": "Rezept",
        "Nachname": "Mustermann",
        "Vorname": "Max",
        "Datum": "2026-05-10",
        "Produkt": "Medikament",
    }

    with patch.object(proc, "extract_hybrid_voting", return_value=mock_extracted):
        success = proc.process_and_route_file(inbox_file)
        assert success is True

    # Source was moved, no longer in Inbox
    assert not os.path.exists(inbox_file)


def test_split_multi_page_pdf_with_retention(test_sandbox):
    """Verifies multi-page PDF splitting with keep_inbox_files retains original source."""
    tmp_dir, config, _ = test_sandbox
    config.keep_inbox_files = True
    proc = DocumentProcessor(config)

    inbox_file = os.path.join(config.watch_dir, "BatchDoc.pdf")
    with open(inbox_file, "wb") as f:
        f.write(MINIMAL_1PAGE_PDF_BYTES)

    page_results = [
        {
            "Document": "Rezept",
            "pages": [1],
            "Nachname": "Mustermann",
            "Vorname": "Hans",
            "Datum": "2026-05-10",
        }
    ]
    extracted = {
        "Document": "Rezept",
        "page_results": page_results,
        "Nachname": "Mustermann",
        "Vorname": "Hans",
        "Datum": "2026-05-10",
    }

    res = proc.file_service.split_multi_page_pdf(
        filepath=inbox_file,
        page_results=page_results,
        extracted_base=extracted,
        find_doc_type_cfg_fn=proc.llm_extractor.find_doc_type_config,
        keep_source=True,
    )
    assert res is True
    assert os.path.exists(inbox_file)
    assert os.path.exists(inbox_file + ".meta")
    with open(inbox_file + ".meta", encoding="utf-8") as f:
        meta = json.load(f)
    assert meta["status"] == "processed"
    assert meta["abgearbeitet"] is True


def test_save_filtered_pdf_with_retention(test_sandbox):
    """Verifies save_filtered_pdf with keep_source retains original file."""
    tmp_dir, config, _ = test_sandbox
    config.keep_inbox_files = True
    proc = DocumentProcessor(config)

    src_file = os.path.join(config.watch_dir, "FilteredSource.pdf")
    dst_file = os.path.join(config.target_base_dir, "Case1", "FilteredDst.pdf")
    with open(src_file, "wb") as f:
        f.write(MINIMAL_1PAGE_PDF_BYTES)

    saved = proc.file_service.save_filtered_pdf(
        src_path=src_file,
        dst_path=dst_file,
        kept_pages=[1],
        keep_source=True,
    )
    assert saved is not None
    assert os.path.exists(src_file)
    assert os.path.exists(src_file + ".meta")
    assert os.path.exists(dst_file)


def test_get_stats_queue_count_excludes_sidecars(test_sandbox):
    """Verifies that processor.get_stats() does not count processed or review files in queue_size."""
    tmp_dir, config, _ = test_sandbox
    proc = DocumentProcessor(config)

    # File 1: Pending (no .meta)
    p1 = os.path.join(config.watch_dir, "Pending.pdf")
    with open(p1, "wb") as f:
        f.write(MINIMAL_1PAGE_PDF_BYTES)

    # File 2: Processed (has .meta)
    p2 = os.path.join(config.watch_dir, "Done.pdf")
    with open(p2, "wb") as f:
        f.write(MINIMAL_1PAGE_PDF_BYTES)
    with open(p2 + ".meta", "w", encoding="utf-8") as f:
        json.dump({"status": "processed", "abgearbeitet": True}, f)

    stats = proc.get_stats()
    assert stats["queue_size"] == 1


def test_import_engine_batch_skips_processed_files(test_sandbox):
    """Verifies that ImportEngine batch scanning skips already processed files."""
    tmp_dir, config, _ = test_sandbox
    config.keep_inbox_files = True
    proc = DocumentProcessor(config)

    # 1. Create a processed file with .meta
    done_file = os.path.join(config.watch_dir, "DoneScan.pdf")
    with open(done_file, "wb") as f:
        f.write(MINIMAL_1PAGE_PDF_BYTES)
    proc.file_service.mark_as_processed(done_file, extracted={"Document": "Rezept"})

    # 2. Run ImportEngine batch
    engine = ImportEngine(definition={"id": "import_test", "type": "import"}, processor=proc)
    task = SkillTask(
        id="task_test",
        skill_id="import_test",
        skill_name="Import",
        skill_type=SkillType.IMPORT,
        context={},  # Batch mode
    )

    with patch.object(proc, "process_and_route_file", wraps=proc.process_and_route_file) as mock_route:
        result = engine.execute(task)
        assert result.success is True
        # The processed file was skipped by the scanner
        assert mock_route.call_count == 0


def test_inbox_api_processed_and_review_distinction(client, test_sandbox):
    """Verifies GET /api/inbox returns is_processed=True and is_review=False for processed files."""
    _, config, _ = test_sandbox
    watch_dir = config.watch_dir

    # 1. Processed file
    f1 = os.path.join(watch_dir, "Processed.pdf")
    with open(f1, "wb") as f:
        f.write(MINIMAL_1PAGE_PDF_BYTES)
    with open(f1 + ".meta", "w", encoding="utf-8") as f:
        json.dump({"status": "processed", "abgearbeitet": True, "extracted": {"Document": "Rezept"}}, f)

    # 2. Review file
    f2 = os.path.join(watch_dir, "Review.pdf")
    with open(f2, "wb") as f:
        f.write(MINIMAL_1PAGE_PDF_BYTES)
    with open(f2 + ".meta", "w", encoding="utf-8") as f:
        json.dump({"status": "review", "grund": "Barcode unreadable"}, f)

    res = client.get("/api/inbox")
    assert res.status_code == 200
    items = res.get_json()
    assert len(items) == 2

    p_item = next(it for it in items if it["name"] == "Processed.pdf")
    assert p_item["is_processed"] is True
    assert p_item["is_abgearbeitet"] is True
    assert p_item["is_review"] is False
    assert p_item["is_pruefen"] is False
    assert p_item["status"] == "processed"

    r_item = next(it for it in items if it["name"] == "Review.pdf")
    assert r_item["is_processed"] is False
    assert r_item["is_review"] is True
    assert r_item["is_pruefen"] is True
    assert r_item["status"] == "review"


def test_api_config_put_and_get_keep_inbox_files(client, test_sandbox):
    """Verifies PUT /api/config and GET /api/config handle keep_inbox_files properly."""
    res_get = client.get("/api/config")
    assert res_get.status_code == 200
    data_get = res_get.get_json()
    assert "keep_inbox_files" in data_get

    # Update setting
    res_put = client.put("/api/config", json={"keep_inbox_files": True})
    assert res_put.status_code == 200
    data_put = res_put.get_json()
    assert "keep_inbox_files" in data_put["changed"]

    # Verify updated value
    res_get_updated = client.get("/api/config")
    assert res_get_updated.get_json()["keep_inbox_files"] is True
