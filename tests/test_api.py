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
    person_folder = tmp_path / "2026-03-13__Einlagen__Muster, Max"
    person_folder.mkdir()
    dummy_file = person_folder / "Rezept__Einlagen__2026-03-13.pdf"
    dummy_file.touch()
    dummy_meta = person_folder / "Rezept__Einlagen__2026-03-13.pdf.meta"
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
    response_detail = client.get("/api/cases/2026-03-13__Einlagen__Muster%2C%20Max")
    assert response_detail.status_code == 200
    data_detail = response_detail.get_json()
    # Nur das PDF darf gelistet werden
    assert len(data_detail["files"]) == 1
    assert data_detail["files"][0]["name"] == "Rezept__Einlagen__2026-03-13.pdf"
    assert "preview_url" in data_detail["files"][0]
    assert "Muster%2C%20Max" in data_detail["files"][0]["preview_url"]

def test_api_eingang_retry_and_delete(client, tmp_path):
    import queue

    from core.processor import DocumentProcessor
    DashboardState.config.watch_dir = str(tmp_path)
    DashboardState.file_queue = queue.Queue()
    DashboardState.processor = DocumentProcessor(DashboardState.config)

    # Erstelle Dummy PDF und Meta in einem Unterordner
    subfolder = tmp_path / "Subfolder Name"
    subfolder.mkdir()
    pdf = subfolder / "scan_001.pdf"
    pdf.touch()
    meta = subfolder / "scan_001.pdf.meta"
    meta.touch()

    # Teste Retry (wieder verarbeiten)
    resp_retry = client.post("/api/inbox/Subfolder%20Name/scan_001.pdf/retry")
    assert resp_retry.status_code == 200
    assert not meta.exists()  # .meta Datei muss gelöscht sein
    assert DashboardState.file_queue.qsize() == 1  # Muss in die Queue gelegt worden sein

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
                "filename_template": "{Dokument}_{Kunde}_{Datum}",
            }
        }
    }
    data = {"Abteilung": "Finanzen", "Kunde": "Acme AG", "Datum": "2026-07-09"}
    folder = _render_target_folder(data, "CustomDoc")
    filename = _render_target_filename(data, "CustomDoc", ".pdf")

    assert folder == "Finanzen__Acme AG"
    assert filename == "CustomDoc_Acme AG_2026-07-09.pdf"


def test_api_pydantic_schema_validation():
    from routes.schemas import AssignDocumentSchema, validate_schema

    valid_payload = {"dokument": "Rechnung", "Betrag": "100.00 EUR"}
    model, err = validate_schema(AssignDocumentSchema, valid_payload)
    assert err is None
    assert model is not None
    clean = model.to_clean_dict()
    assert clean["dokument"] == "Rechnung"
    assert clean["Betrag"] == "100.00 EUR"

    model_bad, err_bad = validate_schema(AssignDocumentSchema, ["Kein Dict"])  # type: ignore[arg-type]
    assert model_bad is None
    assert err_bad is not None


def test_background_job_queue_sequential_fifo(client):
    import time

    from core.jobs import job_queue

    execution_order = []

    def dummy_task(n):
        execution_order.append(n)
        return f"Done-{n}"

    job_id = job_queue.submit("Task 1", dummy_task, 1)
    _job2_id = job_queue.submit("Task 2", dummy_task, 2)

    # Warte kurz, bis Worker abgearbeitet hat
    time.sleep(0.5)

    assert execution_order == [1, 2]  # Strikt sequenzielles FIFO!
    res = client.get(f"/api/jobs/{job_id}")
    assert res.status_code == 200
    assert res.get_json()["status"] == "DONE"
    assert res.get_json()["result"] == "Done-1"


def test_api_config_get_and_put(client, tmp_path):
    orig_watch = DashboardState.config.watch_dir
    orig_base = DashboardState.config.base_dir
    orig_rules = DashboardState.config.vision_base_rules

    try:
        DashboardState.config.watch_dir = str(tmp_path)
        DashboardState.config.base_dir = str(tmp_path)
        DashboardState.config.vision_base_rules = "Test Vision System Prompt"

        # 1. Test GET config
        res_get = client.get("/api/config")
        assert res_get.status_code == 200
        data_get = res_get.get_json()
        assert data_get["vision_base_rules"] == "Test Vision System Prompt"

        # 2. Test PUT config
        new_rules = "Updated Vision System Prompt\nWith Multiple Lines"
        res_put = client.put("/api/config", json={
            "vision_base_rules": new_rules
        })
        assert res_put.status_code == 200

        # Verify updated in config class
        assert DashboardState.config.vision_base_rules == new_rules
    finally:
        DashboardState.config.watch_dir = orig_watch
        DashboardState.config.base_dir = orig_base
        DashboardState.config.vision_base_rules = orig_rules


def test_api_skills_crud_and_duplicate(client):
    # 1. GET /api/skills
    res_get = client.get("/api/skills")
    assert res_get.status_code == 200
    assert "skills" in res_get.get_json()

    # 2. POST /api/skills (Erstellen)
    skill_payload = {
        "id": "test_api_skill_1",
        "name": "API Test Skill",
        "description": "Skill über API angelegt",
        "enabled": True,
        "steps": [{"id": "s1", "action_type": "FOCUS_WINDOW", "window_title": "Notepad*"}]
    }
    res_post = client.post("/api/skills", json=skill_payload)
    assert res_post.status_code == 200
    assert res_post.get_json()["skill_id"] == "test_api_skill_1"

    # 3. POST /api/skills/<id>/duplicate (Duplizieren)
    res_dup = client.post("/api/skills/test_api_skill_1/duplicate")
    assert res_dup.status_code == 200
    dup_skill = res_dup.get_json()["skill"]
    assert "Copy" in dup_skill["name"] or "Kopie" in dup_skill["name"]

    # 4. DELETE /api/skills/<id> (Löschen)
    res_del1 = client.delete("/api/skills/test_api_skill_1")
    assert res_del1.status_code == 200
    res_del2 = client.delete(f"/api/skills/{dup_skill['id']}")
    assert res_del2.status_code == 200


def test_api_vorgaenge_approval_status(client, tmp_path):
    orig_target_base = DashboardState.config.target_base_dir
    test_folder = tmp_path / "2026-07-29__Einlagen__Mustermann__Erika"
    test_folder.mkdir(parents=True, exist_ok=True)

    DashboardState.config.target_base_dir = str(tmp_path)

    try:
        # Before approval
        res = client.get("/api/cases")
        assert res.status_code == 200
        data = res.get_json()
        assert len(data) == 1
        assert data[0]["is_approved"] is False

        # Add .approved marker
        (test_folder / ".approved").write_text("Approved", encoding="utf-8")
        res_approved = client.get("/api/cases")
        assert res_approved.status_code == 200
        data_approved = res_approved.get_json()
        assert data_approved[0]["is_approved"] is True
    finally:
        DashboardState.config.target_base_dir = orig_target_base






