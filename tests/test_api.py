from routes.state import DashboardState


def test_api_eingang(client, tmp_path):
    # Setze temporäres watch_dir auf tmp_path
    DashboardState.config.watch_dir = str(tmp_path)

    # Erstelle eine Dummy PDF-Datei und eine .meta Datei
    dummy_pdf = tmp_path / "test_person.pdf"
    dummy_pdf.touch()
    dummy_meta = tmp_path / "test_person.pdf.meta"
    dummy_meta.touch()

    response = client.get("/api/inbox")
    assert response.status_code == 200
    data = response.get_json()

    # Es sollte nur die PDF-Datei gelistet werden, die .meta wird ignoriert
    assert len(data) == 1
    assert data[0]["name"] == "test_person.pdf"
    # Die Datei hat eine .meta Sidecar → "grund" ist vorhanden (früher: is_pruefen=True)
    assert "grund" in data[0]
    assert "preview_url" in data[0]
    # Überprüfe, ob die URL korrekt URL-encoded wurde
    assert "/api/inbox/preview/test_person.pdf" in data[0]["preview_url"]


def test_api_vorgaenge(client, tmp_path):
    # Setze temporäres target_base_dir auf tmp_path
    DashboardState.config.target_base_dir = str(tmp_path)
    DashboardState.config.folder_structure = ["{Datum}", "{Produkt}", "{Person}"]

    # Erstelle Dummy-Ordner und PDF + .meta Datei
    person_folder = tmp_path / "2026-03-13__Software__Muster, Max"
    person_folder.mkdir()
    dummy_file = person_folder / "Vertrag__Software__2026-03-13.pdf"
    dummy_file.touch()
    dummy_meta = person_folder / "Vertrag__Software__2026-03-13.pdf.meta"
    dummy_meta.touch()

    # Teste /api/cases
    response = client.get("/api/cases")
    assert response.status_code == 200
    data = response.get_json()
    assert len(data) == 1
    assert data[0]["person"] == "Muster, Max"
    # Der file_count darf .meta-Dateien nicht mitzählen (nur 1 PDF)
    assert data[0]["file_count"] == 1

    # Teste /api/cases/<folder_name> (Detail)
    response_detail = client.get("/api/cases/2026-03-13__Software__Muster%2C%20Max")
    assert response_detail.status_code == 200
    data_detail = response_detail.get_json()
    # Nur das PDF darf gelistet werden
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
    assert res_save.get_json()["skill_id"] == "test_api_skill_1"

    # 3. POST /api/skills/<id>/duplicate (Duplizieren)
    res_dup = client.post("/api/skills/test_api_skill_1/duplicate")
    assert res_dup.status_code == 200
    dup_skill = res_dup.get_json()["skill"]
    assert dup_skill["id"].startswith("test_api_skill_1_copy_")
    assert "Copy" in dup_skill["name"] or "Kopie" in dup_skill["name"]

    # 4. DELETE /api/skills/<id> (Löschen)
    res_del1 = client.delete("/api/skills/test_api_skill_1")
    assert res_del1.status_code == 200
    res_del2 = client.delete(f"/api/skills/{dup_skill['id']}")
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
    import urllib.request
    from urllib.error import URLError

    from main import is_ordinflow_running

    class MockResp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=1.5: MockResp())
    assert is_ordinflow_running(8080) is True

    def raise_err(req, timeout=1.5):
        raise URLError("Connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", raise_err)
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
        "2026-08-19 10:00:05,100 [INFO] [+] Processing of 'doc1.pdf' completed successfully after 4.20 seconds.",
        "2026-08-19 10:00:10,100 [INFO] [*] Starting Vision-LLM Tier 1...",
        "2026-08-19 10:00:11,100 [INFO] [+] Page 1 classification: Rezept",
        "2026-08-19 10:00:12,100 [INFO] [*] Starting Vision-LLM Tier 2 for pending fields: ['Signed']...",
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
    assert stats["totalPages"] == 4
    assert stats["categoryCounts"]["Rezept"] == 2
    assert stats["categoryCounts"]["Befundbogen"] == 1
    assert stats["categoryCounts"]["Notiz"] == 1
    assert stats["tier1Count"] == 1  # 1 document finalized directly in Tier 1
    assert stats["tier2Count"] == 2  # 2 documents escalated to Tier 2
    assert stats["tier3Count"] == 1  # 1 document escalated to Tier 3 Tiebreaker
    assert stats["infoCount"] == 13
    assert stats["warnCount"] == 1
    assert stats["errorCount"] == 0
    assert float(stats["totalProcessingTime"]) == 17.8


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
