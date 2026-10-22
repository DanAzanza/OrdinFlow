import json

from routes.state import DashboardState


def test_api_eingang(client, tmp_path):
    # Set temporary watch_dir to tmp_path
    DashboardState.config.watch_dir = str(tmp_path)

    # Create dummy PDF file and .meta sidecar file
    dummy_pdf = tmp_path / "test_person.pdf"
    dummy_pdf.touch()
    dummy_meta = tmp_path / "test_person.pdf.meta"
    dummy_meta.touch()

    response = client.get("/api/inbox")
    assert response.status_code == 200
    data = response.get_json()

    # Only PDF files should be listed; .meta sidecars are ignored
    assert len(data) == 1
    assert data[0]["name"] == "test_person.pdf"
    # File has a .meta sidecar -> 'grund' field is present
    assert "grund" in data[0]
    assert "preview_url" in data[0]
    # Verify that URL is correctly URL-encoded
    assert "/api/inbox/preview/test_person.pdf" in data[0]["preview_url"]


def test_api_vorgaenge(client, tmp_path):
    # Set temporary target_base_dir to tmp_path
    DashboardState.config.target_base_dir = str(tmp_path)
    DashboardState.config.folder_structure = ["{Datum}", "{Produkt}", "{Person}"]

    # Create dummy folder and PDF + .meta sidecar file
    person_folder = tmp_path / "2026-03-13__Software__Muster, Max"
    person_folder.mkdir()
    dummy_file = person_folder / "Vertrag__Software__2026-03-13.pdf"
    dummy_file.touch()
    dummy_meta = person_folder / "Vertrag__Software__2026-03-13.pdf.meta"
    dummy_meta.touch()

    # Test /api/cases
    response = client.get("/api/cases")
    assert response.status_code == 200
    data = response.get_json()
    assert len(data) == 1
    assert data[0]["person"] == "Muster, Max"
    # file_count must not count .meta files (only 1 PDF)
    assert data[0]["file_count"] == 1

    # Test /api/cases/<folder_name> (Detail)
    response_detail = client.get("/api/cases/2026-03-13__Software__Muster%2C%20Max")
    assert response_detail.status_code == 200
    data_detail = response_detail.get_json()
    # Only PDF should be listed
    assert len(data_detail["files"]) == 1
    assert data_detail["files"][0]["name"] == "Vertrag__Software__2026-03-13.pdf"
    assert "preview_url" in data_detail["files"][0]
    assert "Muster%2C%20Max" in data_detail["files"][0]["preview_url"]


def test_api_eingang_retry_and_delete(client, tmp_path):
    from core.processor import DocumentProcessor
    from core.skills.queue import get_skill_queue_manager

    DashboardState.config.watch_dir = str(tmp_path)
    DashboardState.processor = DocumentProcessor(DashboardState.config)

    # Erstelle Dummy PDF und Meta in einem Unterordner
    subfolder = tmp_path / "Subfolder Name"
    subfolder.mkdir()
    pdf = subfolder / "scan_001.pdf"
    pdf.touch()
    meta = subfolder / "scan_001.pdf.meta"
    meta.touch()

    # Teste Retry (wieder verarbeiten über Skill Queue)
    resp_retry = client.post("/api/inbox/Subfolder%20Name/scan_001.pdf/retry")
    assert resp_retry.status_code == 200
    assert not meta.exists()  # .meta Datei muss gelöscht sein
    qm = get_skill_queue_manager()
    assert len(qm.items) >= 1

    # Teste Delete
    meta.touch()  # Wieder erstellen für den Lösch-Test
    resp_delete = client.delete("/api/inbox/Subfolder%20Name/scan_001.pdf")
    assert resp_delete.status_code == 200
    assert not pdf.exists()  # PDF gelöscht
    assert not meta.exists()  # .meta gelöscht


def test_api_config_driven_routing(client, tmp_path):
    from routes.api import _render_target_filename, _render_target_folder

    DashboardState.config.folder_structure = ["{Abteilung}", "{Kunde}"]
    DashboardState.config.document_types = {
        "CustomDoc": {
            "routing": {
                "filename_template": "{Document}_{Kunde}_{Datum}",
            }
        }
    }
    data = {"Abteilung": "Finanzen", "Kunde": "Acme AG", "Datum": "2026-07-09"}
    folder = _render_target_folder(data, "CustomDoc")
    delim = getattr(DashboardState.config, "folder_delimiter", "__") or "__"
    assert folder == f"Finanzen{delim}Acme AG"
    filename = _render_target_filename(data, "CustomDoc", ".pdf")
    assert filename == "CustomDoc_Acme AG_2026-07-09.pdf"


def test_api_skills_crud(client):
    # 1. GET /api/skills (List)
    res_list = client.get("/api/skills")
    assert res_list.status_code == 200
    data = res_list.get_json()
    assert "skills" in data

    # 2. POST /api/skills (Save / Create)
    new_skill = {
        "id": "test_api_skill_1",
        "name": "API Test Skill",
        "type": "export",
        "description": "Test skill created via API",
        "enabled": True,
        "steps": [
            {"id": "step_1", "description": "Step 1", "action_type": "FOCUS_WINDOW", "window_title": "Remote Desktop*"}
        ],
    }
    res_save = client.post("/api/skills", json=new_skill)
    assert res_save.status_code == 200
    assert res_save.get_json()["status"] == "ok"
    assert res_save.get_json()["name"] == "API Test Skill"

    # 3. POST /api/skills/<id>/duplicate (Duplizieren)
    res_dup = client.post("/api/skills/API Test Skill/duplicate")
    assert res_dup.status_code == 200
    dup_skill = res_dup.get_json()["skill"]
    assert "Copy" in dup_skill["name"]

    # 4. DELETE /api/skills/<id> (Löschen)
    res_del1 = client.delete("/api/skills/API Test Skill")
    assert res_del1.status_code == 200
    res_del2 = client.delete(f"/api/skills/{dup_skill['name']}")
    assert res_del2.status_code == 200


def test_api_vorgaenge_approval_status(client, tmp_path):
    orig_target_base = DashboardState.config.target_base_dir
    test_folder = tmp_path / "2026-07-29__Software__Mustermann__Erika"
    test_folder.mkdir(parents=True, exist_ok=True)

    DashboardState.config.target_base_dir = str(tmp_path)

    try:
        # Before approval
        res = client.get("/api/cases")
        assert res.status_code == 200
        data = res.get_json()
        assert len(data) == 1
        assert data[0]["is_approved"] is False
        assert data[0]["export_status"] == "pending_approval"

        # Toggle approval via /api/cases/approve
        res_toggle = client.post(
            "/api/cases/approve", json={"folder": "2026-07-29__Software__Mustermann__Erika", "approved": True}
        )
        assert res_toggle.status_code == 200
        assert res_toggle.get_json()["is_approved"] is True

        res_approved = client.get("/api/cases")
        assert res_approved.status_code == 200
        data_approved = res_approved.get_json()
        assert data_approved[0]["is_approved"] is True
        assert data_approved[0]["export_status"] == "approved"

        # Revoke approval
        res_revoke = client.post(
            "/api/cases/approve", json={"folder": "2026-07-29__Software__Mustermann__Erika", "approved": False}
        )
        assert res_revoke.status_code == 200
        assert res_revoke.get_json()["is_approved"] is False
    finally:
        DashboardState.config.target_base_dir = orig_target_base


def test_api_cases_edit_file_atomic_sidecar(client, tmp_path):
    orig_target_base = DashboardState.config.target_base_dir
    DashboardState.config.target_base_dir = str(tmp_path)
    DashboardState.config.folder_structure = ["{Datum}", "{Produkt}", "{Nachname}", "{Vorname}"]
    DashboardState.config.document_types = {
        "Invoice": {
            "routing": {
                "filename_template": "Invoice__{Nachname}__{Datum}",
            }
        }
    }

    src_folder = tmp_path / "2026-08-01__Software__Doe__John"
    src_folder.mkdir(parents=True, exist_ok=True)
    pdf_file = src_folder / "Invoice__Doe__2026-08-01.pdf"
    pdf_file.write_text("dummy pdf", encoding="utf-8")
    meta_file = src_folder / "Invoice__Doe__2026-08-01.pdf.meta"
    meta_file.write_text('{"status": "ok"}', encoding="utf-8")

    try:
        edit_payload = {
            "document": "Invoice",
            "Nachname": "Smith",
            "Vorname": "Jane",
            "Datum": "2026-08-02",
            "Produkt": "Hardware",
            "move": True,
        }
        res = client.post(
            "/api/cases/2026-08-01__Software__Doe__John/Invoice__Doe__2026-08-01.pdf/edit",
            json=edit_payload,
        )
        assert res.status_code == 200
        res_data = res.get_json()
        assert res_data["status"] == "ok"
        new_folder = tmp_path / res_data["folder"]
        new_pdf = new_folder / res_data["file"]
        new_meta = new_folder / (res_data["file"] + ".meta")

        # Verify atomic movement of both file and its sidecar
        assert new_pdf.exists()
        assert new_meta.exists()
        assert not pdf_file.exists()
        assert not meta_file.exists()
    finally:
        DashboardState.config.target_base_dir = orig_target_base


def test_api_cases_edit_file_schema_validation(client, tmp_path):
    """POST /api/cases/.../edit validates payload using FlexibleDocumentPayload and handles invalid inputs."""
    orig_target_base = DashboardState.config.target_base_dir
    DashboardState.config.target_base_dir = str(tmp_path)
    src_folder = tmp_path / "2026-08-01__Software__Doe__John"
    src_folder.mkdir(parents=True, exist_ok=True)
    pdf_file = src_folder / "Invoice__Doe__2026-08-01.pdf"
    pdf_file.write_text("dummy pdf", encoding="utf-8")

    try:
        # 1. Empty payload
        res_empty = client.post(
            "/api/cases/2026-08-01__Software__Doe__John/Invoice__Doe__2026-08-01.pdf/edit",
            json={},
        )
        assert res_empty.status_code == 400
        assert "No data provided" in res_empty.get_json()["error"]

        # 2. Malformed JSON payload
        res_malformed = client.post(
            "/api/cases/2026-08-01__Software__Doe__John/Invoice__Doe__2026-08-01.pdf/edit",
            data="not-json",
            content_type="application/json",
        )
        assert res_malformed.status_code == 400

        # 3. Valid payload with move=False
        res_valid = client.post(
            "/api/cases/2026-08-01__Software__Doe__John/Invoice__Doe__2026-08-01.pdf/edit",
            json={"Document": "Invoice", "Nachname": "Doe", "move": False},
        )
        assert res_valid.status_code == 200
    finally:
        DashboardState.config.target_base_dir = orig_target_base


def test_api_inbox_auto_assign_domain_agnostic(client, tmp_path):
    """POST /api/inbox/<filename>/auto_assign succeeds with non-person domain metadata."""
    orig_watch = DashboardState.config.watch_dir
    orig_target_base = DashboardState.config.target_base_dir
    orig_folder_structure = DashboardState.config.folder_structure
    orig_doc_types = DashboardState.config.document_types

    inbox_dir = tmp_path / "inbox"
    cases_dir = tmp_path / "cases"
    inbox_dir.mkdir(parents=True, exist_ok=True)
    cases_dir.mkdir(parents=True, exist_ok=True)

    DashboardState.config.watch_dir = str(inbox_dir)
    DashboardState.config.target_base_dir = str(cases_dir)
    DashboardState.config.folder_structure = ["{Category}"]
    DashboardState.config.document_types = {
        "Recipe": {
            "routing": {
                "filename_template": "{Document}__{Category}",
            }
        }
    }

    try:
        scan_file = inbox_dir / "Scan_Cake.pdf"
        scan_file.write_text("%PDF-1.4 dummy", encoding="utf-8")
        meta_file = inbox_dir / "Scan_Cake.pdf.meta"
        meta_file.write_text(
            json.dumps({"extracted": {"Document": "Recipe", "Category": "Cakes"}}),
            encoding="utf-8",
        )

        # 1. Successful domain-agnostic auto-assign
        res = client.post("/api/inbox/Scan_Cake.pdf/auto_assign")
        assert res.status_code == 200
        assert res.get_json()["status"] == "ok"
        assert not scan_file.exists()
        assert not meta_file.exists()
        expected_target = cases_dir / "Cakes" / "Recipe__Cakes.pdf"
        assert expected_target.exists()

        # 2. Negative test: file with insufficient metadata rejected
        blank_file = inbox_dir / "Unknown.pdf"
        blank_file.write_text("%PDF-1.4 dummy", encoding="utf-8")
        blank_meta = inbox_dir / "Unknown.pdf.meta"
        blank_meta.write_text(
            json.dumps({"extracted": {"Document": "Recipe", "IrrelevantKey": "Value"}}),
            encoding="utf-8",
        )
        res_insufficient = client.post("/api/inbox/Unknown.pdf/auto_assign")
        assert res_insufficient.status_code == 400
        assert "sufficient data" in res_insufficient.get_json()["error"]
    finally:
        DashboardState.config.watch_dir = orig_watch
        DashboardState.config.target_base_dir = orig_target_base
        DashboardState.config.folder_structure = orig_folder_structure
        DashboardState.config.document_types = orig_doc_types


def test_api_skills_pending_cases_and_run_batch(client, tmp_path):
    orig_target_base = DashboardState.config.target_base_dir
    DashboardState.config.target_base_dir = str(tmp_path)

    # Erstelle freigegebenen Testfall mit PDF
    c_folder = tmp_path / "2026-08-14__Software__Test__Patient"
    c_folder.mkdir(parents=True, exist_ok=True)
    (c_folder / ".approved").write_text("Approved", encoding="utf-8")
    pdf = c_folder / "Befund__Software__2026.pdf"
    pdf.write_text("dummy", encoding="utf-8")
    meta = c_folder / "Befund__Software__2026.pdf.meta"
    meta.write_text('{"Document": "Befund"}', encoding="utf-8")

    try:
        # Create test export skill
        skill_payload = {
            "id": "test_batch_skill",
            "name": "Test Batch Skill",
            "type": "export",
            "enabled": True,
            "document_types": ["Befund"],
            "steps": [],
        }
        client.post("/api/skills", json=skill_payload)

        # GET /api/skills/<id>/pending_cases
        res_pending = client.get("/api/skills/test_batch_skill/pending_cases")
        assert res_pending.status_code == 200
        data_p = res_pending.get_json()
        assert data_p["count"] == 1
        assert data_p["cases"][0]["folder_name"] == "2026-08-14__Software__Test__Patient"

        # POST /api/skills/<id>/run_batch
        res_batch = client.post("/api/skills/test_batch_skill/run_batch")
        assert res_batch.status_code == 200
        data_b = res_batch.get_json()
        assert data_b["status"] == "queued_and_started"
        assert data_b["queued_count"] == 1

        # Clean up skill
        client.delete("/api/skills/test_batch_skill")
    finally:
        DashboardState.config.target_base_dir = orig_target_base


def test_api_skills_refine_step(client):
    # Test typing text with enter
    res1 = client.post(
        "/api/skills/refine_step",
        json={"instruction": "Tippe {Nachname} ein und drücke Enter", "step": {"id": "step_1"}},
    )
    assert res1.status_code == 200
    step1 = res1.get_json()["step"]
    assert step1["action_type"] == "TYPE_TEXT"
    assert step1["text"] == "{Nachname}"
    assert step1["press_enter"] is True

    # Test file upload
    res2 = client.post(
        "/api/skills/refine_step", json={"instruction": "Lade die Datei PDF hoch", "step": {"id": "step_2"}}
    )
    assert res2.status_code == 200
    step2 = res2.get_json()["step"]
    assert step2["action_type"] == "TYPE_FILE_PATH"

    # Test clicking button
    res3 = client.post("/api/skills/refine_step", json={"instruction": "Klicke auf Suchen", "step": {"id": "step_3"}})
    assert res3.status_code == 200
    step3 = res3.get_json()["step"]
    assert step3["action_type"] == "CLICK"
    assert "Suchen" in str(step3.get("locator", {}).get("prompt", ""))

    # Test conditional fallback routine
    res4 = client.post(
        "/api/skills/refine_step",
        json={
            "instruction": "Prüfe ob {Nachname} sichtbar ist, wenn nicht führe routine patient_anlegen aus",
            "step": {"id": "step_4"},
        },
    )
    assert res4.status_code == 200
    step4 = res4.get_json()["step"]
    assert step4["action_type"] == "VERIFY_SCREEN"
    assert step4["on_failure_action"] == "run_skill"
    assert "patient_anlegen" in step4["on_failure_skill"]


def test_is_ordinflow_running(monkeypatch):
    import http.client
    from main import is_ordinflow_running

    class MockResp:
        status = 200

    class MockConn:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, *args, **kwargs):
            pass

        def getresponse(self):
            return MockResp()

        def close(self):
            pass

    monkeypatch.setattr(http.client, "HTTPConnection", MockConn)
    assert is_ordinflow_running(8080) is True

    class FailingConn:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, *args, **kwargs):
            raise OSError("Connection refused")

    monkeypatch.setattr(http.client, "HTTPConnection", FailingConn)
    assert is_ordinflow_running(8080) is False


def test_api_skills_queue_pause_resume(client):
    # Ensure clean initial state
    client.post("/api/skills/queue/stop")
    client.post("/api/skills/queue/clear")

    # Test pause when not running
    res_pause = client.post("/api/skills/queue/pause")
    assert res_pause.status_code == 200
    assert res_pause.get_json()["status"] == "not_running"

    # Add item and start
    client.post("/api/skills/queue/add", json={"skill_id": "test_skill", "context": {}})
    res_start = client.post("/api/skills/queue/start")
    assert res_start.status_code == 200

    # Pause
    res_pause2 = client.post("/api/skills/queue/pause")
    assert res_pause2.status_code == 200

    # Resume
    res_resume = client.post("/api/skills/queue/resume")
    assert res_resume.status_code == 200
    assert res_resume.get_json()["is_paused"] is False

    # Stop
    res_stop = client.post("/api/skills/queue/stop")
    assert res_stop.status_code == 200
    assert res_stop.get_json()["is_running"] is False


def test_api_log_stats_computation():
    from routes.api.system_api import _compute_log_stats

    dummy_lines = [
        "2026-08-19 10:00:01,100 [INFO] [*] Starting Vision-LLM Tier 1...",
        "2026-08-19 10:00:02,100 [INFO] [+] Page 1 classification: Rezept",
        "2026-08-19 10:00:03,100 [INFO] [+] Page 2 classification: Befundbogen",
        "2026-08-19 10:00:04,100 [INFO] [+] All 5 field(s) validated with >= 2 measurements. Finalizing document.",
        "2026-08-19 10:00:04,150 [INFO] [*] Splitting batch PDF 'doc1.pdf' into 2 separate files...",
        "2026-08-19 10:00:04,200 [INFO] [+] Partial PDF 'doc1_a.pdf' (pages [1]) saved successfully.",
        "2026-08-19 10:00:04,250 [INFO] [+] Partial PDF 'doc1_b.pdf' (pages [2]) saved successfully.",
        "2026-08-19 10:00:05,100 [INFO] [+] Processing of 'doc1.pdf' completed successfully after 4.20 seconds.",
        "2026-08-19 10:00:10,100 [INFO] [*] Starting Vision-LLM Tier 1...",
        "2026-08-19 10:00:11,100 [INFO] [+] Page 1 classification: Rezept",
        "2026-08-19 10:00:12,100 [INFO] [*] Starting Vision-LLM Tier 2 for pending fields: ['Signed']...",
        "2026-08-19 10:00:13,100 [INFO] [+] Moving file 'doc2.pdf' -> 'target/doc2.pdf'",
        "2026-08-19 10:00:14,100 [INFO] [+] Processing of 'doc2.pdf' completed successfully after 8.50 seconds.",
        "2026-08-19 10:00:20,100 [INFO] [*] Starting Vision-LLM Tier 1...",
        "2026-08-19 10:00:21,100 [INFO] [+] Page 1 classification: Notiz",
        "2026-08-19 10:00:22,100 [INFO] [*] Starting Vision-LLM Tier 2 for pending fields: ['Datum']...",
        "2026-08-19 10:00:23,100 [INFO] [*] Disagreement in field(s) ['Datum'] detected. Starting Vision-LLM Tier 3 Tiebreaker...",
        "2026-08-19 10:00:25,100 [WARNING] [-] Processing of 'doc3.pdf' incomplete (5.10s) — Reason: Validation failed.",
    ]

    stats = _compute_log_stats(dummy_lines)

    assert stats["totalFiles"] == 3
    assert stats["completedFiles"] == 2
    assert stats["manualReviewFiles"] == 1
    assert stats["splitBatches"] == 1
    assert stats["partialDocsSaved"] == 2
    assert stats["directDocsMoved"] == 1
    assert stats["totalArchivedDocs"] == 3
    assert stats["totalPages"] == 4
    assert stats["categoryCounts"]["Rezept"] == 2
    assert stats["categoryCounts"]["Befundbogen"] == 1
    assert stats["categoryCounts"]["Notiz"] == 1
    assert stats["tier1Count"] == 3  # 3 total documents executed Tier 1
    assert stats["tier1DirectConsensus"] == 1  # 1 document finalized directly in Tier 1
    assert stats["tier2Count"] == 2  # 2 documents escalated to Tier 2
    assert stats["tier2Resolved"] == 1  # 1 document resolved in Tier 2
    assert stats["tier3Count"] == 1  # 1 document escalated to Tier 3 Tiebreaker
    assert stats["tier3Resolved"] == 1  # 1 document resolved in Tier 3
    assert stats["infoCount"] == 17
    assert stats["warnCount"] == 1
    assert stats["errorCount"] == 0
    assert float(stats["totalProcessingTime"]) == 17.8


def test_compute_log_stats_empty_files():
    """Verifies that compute_log_stats counts empty page trash/deletion log messages in emptyFiles."""
    from core.logging_service import compute_log_stats

    # Current processor message format
    current_log = [
        "2026-08-19 10:00:30,100 [INFO] [-] 'empty_scan.pdf' consists only of empty pages and will be moved to trash."
    ]
    stats_current = compute_log_stats(current_log)
    assert stats_current["emptyFiles"] == 1
    assert stats_current["totalFiles"] == 1

    # Legacy processor message format
    legacy_log = [
        "2026-08-19 10:00:31,100 [INFO] [-] 'legacy_scan.pdf' consists only of empty pages and will be deleted."
    ]
    stats_legacy = compute_log_stats(legacy_log)
    assert stats_legacy["emptyFiles"] == 1
    assert stats_legacy["totalFiles"] == 1

    # Negative assertion: unrelated log message does not increment emptyFiles
    unrelated_log = [
        "2026-08-19 10:00:32,100 [INFO] [+] Processing of 'regular.pdf' completed successfully after 2.00 seconds."
    ]
    stats_unrelated = compute_log_stats(unrelated_log)
    assert stats_unrelated["emptyFiles"] == 0
    assert stats_unrelated["totalFiles"] == 1


def test_api_log_endpoints(client, tmp_path, monkeypatch):
    import os

    log_file = tmp_path / "main.log"
    log_file.write_text("2026-08-19 10:00:01 [INFO] Test line\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)

    # Test GET /api/log/stats
    res = client.get("/api/log/stats")
    assert res.status_code == 200
    data = res.get_json()
    assert data["recordsCount"] == 1
    assert data["infoCount"] == 1

    # Test POST /api/log/clear
    res_clear = client.post("/api/log/clear")
    assert res_clear.status_code == 200
    assert res_clear.get_json()["status"] == "cleared"

    # Verify log file is empty
    assert os.path.getsize(str(log_file)) == 0


def test_api_system_browse(client):
    """POST /api/system/browse returns disabled status pointing clients to fs_list."""
    res = client.post("/api/system/browse", json={"picker_type": "folder", "title": "Select Folder"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "disabled"
    assert data["path"] is None
    assert "/api/system/fs_list" in data["message"]


def test_api_skills_test_run(client, monkeypatch):
    from core.skills.exceptions import SkillActionError

    skill_def = {
        "name": "API Test Skill",
        "tasks": [
            {
                "id": "t1",
                "title": "Test Task",
                "actions": [
                    {
                        "id": "act_1",
                        "action_type": "SLEEP",
                        "duration_s": 0.05,
                        "description": "Short pause",
                    }
                ],
            }
        ],
    }

    # Valid test run
    res = client.post("/api/skills/test_run", json={"skill": skill_def})
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "ok"
    assert data["success"] is True
    assert data["total_actions"] == 1
    assert "duration_seconds" in data

    # Invalid input: no skill
    res_bad = client.post("/api/skills/test_run", json={})
    assert res_bad.status_code == 400

    # Skill requiring document_fullpath but none provided -> must fail fast with 400
    doc_req_skill = {
        "name": "Doc Required Skill",
        "tasks": [
            {
                "id": "t1",
                "actions": [
                    {
                        "id": "act_ps",
                        "action_type": "POWERSHELL",
                        "command": "Write-Output '{document_fullpath}'",
                    }
                ],
            }
        ],
    }
    res_missing_doc = client.post("/api/skills/test_run", json={"skill": doc_req_skill, "context": {}})
    assert res_missing_doc.status_code == 400
    assert "document_fullpath" in res_missing_doc.get_json()["error"]

    def raise_sensitive_error(*args, **kwargs):
        raise SkillActionError("act_1", "Rejected private path C:\\Private\\patient.pdf", "TYPE_FILE_PATH")

    monkeypatch.setattr("routes.api.skills_api.ExportEngine.execute_actions", raise_sensitive_error)
    res_failed = client.post("/api/skills/test_run", json={"skill": skill_def})
    assert res_failed.status_code == 200
    failed_data = res_failed.get_json()
    assert failed_data["status"] == "failed"
    assert "patient.pdf" not in failed_data["error"]


def test_api_skills_pick_element(client, monkeypatch):
    from PIL import Image

    from core.skills.grounder import SoMGrounder

    # Mock screen capture
    def mock_capture(win):
        return Image.new("RGB", (100, 100), color="white")

    monkeypatch.setattr(SoMGrounder, "capture_screen", mock_capture)

    res = client.post("/api/skills/pick_element", json={"delay_seconds": 0.0})
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "ok"
    assert "cursor" in data
    assert "locator" in data
    assert "prompt" in data["locator"]


def test_api_config_get_and_put(client):
    # 1. GET /api/config
    res_get = client.get("/api/config")
    assert res_get.status_code == 200
    cfg_data = res_get.get_json()
    assert "folder_delimiter" in cfg_data

    # 2. PUT /api/config valid update
    res_put = client.put("/api/config", json={"folder_delimiter": "__test__"})
    assert res_put.status_code == 200
    assert res_put.get_json()["status"] == "ok"
    assert "folder_delimiter" in res_put.get_json()["changed"]

    # 3. Verify updated config
    res_get2 = client.get("/api/config")
    assert res_get2.get_json()["folder_delimiter"] == "__test__"


def test_api_system_status_and_lifecycle(client):
    # 1. GET /api/status
    res_status = client.get("/api/status")
    assert res_status.status_code == 200
    data = res_status.get_json()
    assert "paused" in data
    assert "skill_queue" in data

    # 2. POST /api/router/pause and resume
    res_pause = client.post("/api/router/pause")
    assert res_pause.status_code == 200
    assert res_pause.get_json()["status"] == "paused"

    res_resume = client.post("/api/router/resume")
    assert res_resume.status_code == 200
    assert res_resume.get_json()["status"] in ("active", "resumed")

    # 3. GET /api/system/fs_list
    res_fs = client.get("/api/system/fs_list")
    assert res_fs.status_code == 200
    fs_data = res_fs.get_json()
    assert "entries" in fs_data
    assert "drives" in fs_data
    assert "truncated" in fs_data


def test_api_system_fs_list_modes_and_capping(client, tmp_path):
    """Verifies fs_list folder vs file modes, system dir filtering, and truncation."""
    test_root = tmp_path / "browser_test"
    test_root.mkdir()

    # Create subfolders
    (test_root / "Folder_B").mkdir()
    (test_root / "Folder_A").mkdir()
    (test_root / "recovery").mkdir()  # blocked system dir name
    (test_root / "$recycle.bin").mkdir()  # blocked system dir name

    # Create files
    (test_root / "model_alpha.gguf").touch()
    (test_root / "notes.txt").touch()

    # 1. Folder picker mode: files and blocked system dirs must be excluded
    res_folder = client.get(f"/api/system/fs_list?path={test_root}&type=folder")
    assert res_folder.status_code == 200
    data_folder = res_folder.get_json()
    entry_names = [e["name"] for e in data_folder["entries"]]
    assert entry_names == ["Folder_A", "Folder_B"]
    assert "model_alpha.gguf" not in entry_names
    assert "recovery" not in entry_names
    assert "$recycle.bin" not in entry_names
    assert data_folder["truncated"] is False

    # 2. File picker mode with .gguf filter: folders first, then matching files
    res_file = client.get(f"/api/system/fs_list?path={test_root}&type=file&filter=.gguf")
    assert res_file.status_code == 200
    data_file = res_file.get_json()
    entries_file = data_file["entries"]
    assert len(entries_file) == 3
    assert entries_file[0]["name"] == "Folder_A"
    assert entries_file[0]["is_dir"] is True
    assert entries_file[1]["name"] == "Folder_B"
    assert entries_file[1]["is_dir"] is True
    assert entries_file[2]["name"] == "model_alpha.gguf"
    assert entries_file[2]["is_dir"] is False
    assert "notes.txt" not in [e["name"] for e in entries_file]


def test_api_cases_crud_and_approval(client, tmp_path):
    DashboardState.config.target_base_dir = str(tmp_path)
    case_folder = tmp_path / "2026-08-22__Einlagen__Mustermann__Max"
    case_folder.mkdir()
    pdf_file = case_folder / "Fußscan.pdf"
    pdf_file.touch()

    # 1. Approve case folder
    res_app = client.post(
        "/api/cases/approve", json={"folder": "2026-08-22__Einlagen__Mustermann__Max", "approved": True}
    )
    assert res_app.status_code == 200
    assert (case_folder / ".approved").exists()

    # 2. Revoke approval
    res_rev = client.post(
        "/api/cases/approve", json={"folder": "2026-08-22__Einlagen__Mustermann__Max", "approved": False}
    )
    assert res_rev.status_code == 200
    assert not (case_folder / ".approved").exists()

    # 3. Edit / Rename Case Folder
    res_rename = client.put(
        "/api/cases/2026-08-22__Einlagen__Mustermann__Max",
        json={"Datum": "2026-08-23", "Produkt": "Schuhe", "Person": "Muster, Erika"},
    )
    assert res_rename.status_code == 200

    # 4. Delete individual case file
    # Re-create file in updated folder or original
    cur_folders = [f for f in tmp_path.iterdir() if f.is_dir()]
    assert len(cur_folders) >= 1
    active_folder = cur_folders[0]
    (active_folder / "test_doc.pdf").touch()

    res_del_file = client.delete(f"/api/cases/{active_folder.name}/test_doc.pdf")
    assert res_del_file.status_code == 200
    assert not (active_folder / "test_doc.pdf").exists()

    # 5. Delete entire case folder
    res_del_folder = client.delete(f"/api/cases/{active_folder.name}")
    assert res_del_folder.status_code == 200


def test_api_split_inspector_submit_cases_and_security(client, tmp_path):
    DashboardState.config.watch_dir = str(tmp_path / "inbox")
    DashboardState.config.target_base_dir = str(tmp_path / "cases")
    (tmp_path / "inbox").mkdir(exist_ok=True)
    (tmp_path / "cases").mkdir(exist_ok=True)

    # 1. Path traversal security rejection
    res_sec = client.post(
        "/api/split_inspector/submit",
        json={
            "context": "inbox",
            "filename": "../../../Windows/explorer.exe",
            "documents": [{"document": "Rezept"}],
        },
    )
    assert res_sec.status_code in (400, 403, 404)

    # 2. Valid submit moving non-PDF file
    src_file = tmp_path / "inbox" / "scan_note.txt"
    src_file.write_text("Hello text document", encoding="utf-8")

    res_valid = client.post(
        "/api/split_inspector/submit",
        json={
            "context": "inbox",
            "filename": "scan_note.txt",
            "documents": [
                {
                    "document": "Rezept",
                    "Datum": "2026-08-22",
                    "Produkt": "Einlagen",
                    "Person": "Mustermann, Max",
                }
            ],
        },
    )
    assert res_valid.status_code == 200
    data = res_valid.get_json()
    assert data["status"] == "ok"
    assert len(data["results"]) == 1


def test_api_cases_detail_file_url(client, tmp_path):
    """GET /api/cases/<folder> returns file_url for consistent document preview contracts."""
    orig_target_base = DashboardState.config.target_base_dir
    test_folder = tmp_path / "2026-09-01__Software__Mueller__Hans"
    test_folder.mkdir(parents=True, exist_ok=True)
    test_file = test_folder / "Befund 01.pdf"
    test_file.write_text("sample content", encoding="utf-8")

    DashboardState.config.target_base_dir = str(tmp_path)
    try:
        res = client.get("/api/cases/2026-09-01__Software__Mueller__Hans")
        assert res.status_code == 200
        data = res.get_json()
        assert data["folder"] == "2026-09-01__Software__Mueller__Hans"
        assert len(data["files"]) == 1
        file_item = data["files"][0]
        assert file_item["name"] == "Befund 01.pdf"
        assert file_item["file_url"] == "/api/file/cases/2026-09-01__Software__Mueller__Hans/Befund%2001.pdf"
    finally:
        DashboardState.config.target_base_dir = orig_target_base


def test_api_file_meta_cases_nested(client, tmp_path):
    """GET /api/file/meta/cases/<path:folder>/<filename> correctly loads metadata from nested case directories."""
    orig_target_base = DashboardState.config.target_base_dir
    nested_folder = tmp_path / "2026" / "Software__Mueller__Hans"
    nested_folder.mkdir(parents=True, exist_ok=True)
    doc = nested_folder / "Report.pdf"
    doc.write_text("dummy", encoding="utf-8")
    meta = nested_folder / "Report.pdf.meta"
    meta.write_text(json.dumps({"Document": "Report", "extracted": {"Patient": "Mueller"}}), encoding="utf-8")

    DashboardState.config.target_base_dir = str(tmp_path)
    try:
        res = client.get("/api/file/meta/cases/2026/Software__Mueller__Hans/Report.pdf")
        assert res.status_code == 200
        data = res.get_json()
        assert data["Document"] == "Report"
        assert data["extracted"]["Patient"] == "Mueller"
    finally:
        DashboardState.config.target_base_dir = orig_target_base


def test_api_cases_nested_and_delimiter_discovery_and_approval(client, tmp_path):
    """GET /api/cases and POST /api/cases/approve support both standard delimiter and nested case folders."""
    orig_target_base = DashboardState.config.target_base_dir
    orig_delimiter = DashboardState.config.folder_delimiter
    DashboardState.config.target_base_dir = str(tmp_path)
    DashboardState.config.folder_delimiter = "__"

    try:
        # 1. Standard top-level folder with delimiter
        std_folder = tmp_path / "2026-03-13__Software__Muster, Max"
        std_folder.mkdir(parents=True, exist_ok=True)
        (std_folder / "Vertrag.pdf").write_text("standard content", encoding="utf-8")

        # 2. Hierarchical / nested case folder
        nested_folder = tmp_path / "2026" / "Muster__Max"
        nested_folder.mkdir(parents=True, exist_ok=True)
        (nested_folder / "Report.pdf").write_text("nested content", encoding="utf-8")

        # 3. Intermediate folder without delimiter or case files
        empty_intermediate = tmp_path / "2027"
        empty_intermediate.mkdir(parents=True, exist_ok=True)

        # GET /api/cases discovery verification
        res_cases = client.get("/api/cases")
        assert res_cases.status_code == 200
        cases_data = res_cases.get_json()
        discovered_folders = [item["folder"] for item in cases_data]

        assert "2026-03-13__Software__Muster, Max" in discovered_folders
        assert "2026/Muster__Max" in discovered_folders
        assert "2026" not in discovered_folders
        assert "2027" not in discovered_folders

        # Verify summary payload structure for nested folder
        nested_summary = next(item for item in cases_data if item["folder"] == "2026/Muster__Max")
        assert nested_summary["file_count"] == 1
        assert nested_summary["is_approved"] is False

        # POST /api/cases/approve on nested folder
        res_app = client.post("/api/cases/approve", json={"folder": "2026/Muster__Max", "approved": True})
        assert res_app.status_code == 200
        assert res_app.get_json()["is_approved"] is True
        assert (nested_folder / ".approved").exists()

        # POST /api/cases/approve revocation
        res_rev = client.post("/api/cases/approve", json={"folder": "2026/Muster__Max", "approved": False})
        assert res_rev.status_code == 200
        assert res_rev.get_json()["is_approved"] is False
        assert not (nested_folder / ".approved").exists()

        # Security: rejection of path traversal in approve
        res_sec = client.post("/api/cases/approve", json={"folder": "../escape", "approved": True})
        assert res_sec.status_code in (400, 403, 404)
    finally:
        DashboardState.config.target_base_dir = orig_target_base
        DashboardState.config.folder_delimiter = orig_delimiter

