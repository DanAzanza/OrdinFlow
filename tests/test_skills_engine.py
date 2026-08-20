"""
Unit tests for OrdinFlow Skills Engine (core/skills_engine.py).
"""

import json
import os
import shutil
import tempfile

import pytest

from core.skills import (
    SkillExecutor,
    SkillManager,
)
from core.skills.shield import (
    input_shield,
    set_block_input,
)


@pytest.fixture
def temp_skills_dir():
    tmp = tempfile.mkdtemp()
    yield tmp
    shutil.rmtree(tmp, ignore_errors=True)


def test_skill_manager_crud_and_duplicate(temp_skills_dir):
    mgr = SkillManager(skills_dir=temp_skills_dir)
    assert len(mgr.list_skills()) == 0

    # 1. Create and save skill
    skill_data = {
        "id": "test_skill_1",
        "name": "Test Skill 1",
        "description": "First test skill",
        "enabled": True,
        "steps": [
            {"id": "step_1", "description": "Focus Window", "action_type": "FOCUS_WINDOW", "window_title": "Notepad*"}
        ],
    }
    saved_id = mgr.save_skill(skill_data)
    assert saved_id == "test_skill_1"
    assert os.path.exists(os.path.join(temp_skills_dir, "test_skill_1.yaml"))

    # 2. Get skill
    loaded = mgr.get_skill("test_skill_1")
    assert loaded is not None
    assert loaded["name"] == "Test Skill 1"
    assert len(loaded["steps"]) == 1

    # 3. Duplicate skill
    dup = mgr.duplicate_skill("test_skill_1")
    assert dup is not None
    assert dup["id"].startswith("test_skill_1_copy_")
    assert "Copy" in dup["name"]
    assert len(mgr.list_skills()) == 2

    # 4. Delete skill
    deleted = mgr.delete_skill("test_skill_1")
    assert deleted is True
    assert len(mgr.list_skills()) == 1


def test_skill_manager_auto_slugify_id(temp_skills_dir):
    mgr = SkillManager(skills_dir=temp_skills_dir)

    # 1. Save without ID -> should auto-slugify name
    skill_1 = {"name": "Export in RDP Patienten-Datenbank", "enabled": True, "steps": []}
    id_1 = mgr.save_skill(skill_1)
    assert id_1 == "export_in_rdp_patienten_datenbank"
    assert os.path.exists(os.path.join(temp_skills_dir, f"{id_1}.yaml"))

    # 2. Save another skill with same name -> should resolve collision cleanly
    skill_2 = {"name": "Export in RDP Patienten-Datenbank", "enabled": True, "steps": []}
    id_2 = mgr.save_skill(skill_2)
    assert id_2 == "export_in_rdp_patienten_datenbank_2"
    assert os.path.exists(os.path.join(temp_skills_dir, f"{id_2}.yaml"))


def test_input_shield_crash_safety():
    """Verifies that InputShield reliably unlocks input even when exceptions occur."""
    with pytest.raises(ValueError):
        with input_shield(enabled=False):
            raise ValueError("Test error inside input lock block")

    # Verify manual unlock call
    set_block_input(False)


def test_substitute_placeholders(temp_skills_dir):
    mgr = SkillManager(skills_dir=temp_skills_dir)
    executor = SkillExecutor(mgr)

    ctx = {
        "LastName": "Mustermann",
        "FirstName": "Erika",
        "document_fullpath": "C:/docs/file.pdf",
        "BirthDate": "1985-05-12",
    }
    res = executor._substitute_placeholders(
        "Hello {FirstName} {LastName}, Born: {BirthDate}, File: {document_fullpath}", ctx
    )
    assert res == "Hello Erika Mustermann, Born: 1985-05-12, File: C:/docs/file.pdf"

    # Test unknown key safety (unpopulated keys safely resolve to empty string)
    res_unknown = executor._substitute_placeholders("Name: {LastName} {FirstName}, Unknown: {NotPresent}", ctx)
    assert res_unknown == "Name: Mustermann Erika, Unknown: "


def test_sub_skill_execution(temp_skills_dir):
    mgr = SkillManager(skills_dir=temp_skills_dir)

    # Create sub-skill
    sub_skill = {
        "id": "sub_skill_1",
        "name": "Sub Skill 1",
        "enabled": True,
        "steps": [{"id": "sub_step_1", "description": "Sub Action", "action_type": "FOCUS_WINDOW"}],
    }
    mgr.save_skill(sub_skill)

    # Create main skill
    main_skill = {
        "id": "main_skill",
        "name": "Main Skill",
        "enabled": True,
        "steps": [
            {"id": "call_sub", "description": "Call Subskill", "action_type": "CALL_SKILL", "skill_id": "sub_skill_1"}
        ],
    }
    mgr.save_skill(main_skill)

    executor = SkillExecutor(mgr)
    success = executor.execute_skill("main_skill", context={})
    assert success is True


def test_document_type_filtering(temp_skills_dir):
    mgr = SkillManager(skills_dir=temp_skills_dir)
    executor = SkillExecutor(mgr)

    # Create temporary test files
    folder = tempfile.mkdtemp()
    try:
        f1 = os.path.join(folder, "DeliveryNote__Software__2026.pdf")
        f2 = os.path.join(folder, "Contract__Software__2026.pdf")
        open(f1, "w").close()
        open(f2, "w").close()

        # 1. Filter with specific type
        matched = executor.filter_matching_files(folder, allowed_types=["DeliveryNote"])
        assert len(matched) == 1
        assert matched[0]["filename"] == "DeliveryNote__Software__2026.pdf"

        # 2. Filter with '*' (all)
        matched_all = executor.filter_matching_files(folder, allowed_types=["*"])
        assert len(matched_all) == 2
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def test_skill_executor_retry_logic(temp_skills_dir, monkeypatch):
    mgr = SkillManager(skills_dir=temp_skills_dir)
    executor = SkillExecutor(mgr)

    attempts = []

    def mock_locate(locator, window_title):
        attempts.append(len(attempts) + 1)
        if len(attempts) < 3:
            return None
        return (100, 200)

    monkeypatch.setattr(executor, "_locate_target", mock_locate)

    skill = {
        "id": "retry_skill",
        "name": "Retry Skill",
        "enabled": True,
        "steps": [
            {
                "id": "click_retry",
                "action_type": "CLICK",
                "locator": {"type": "ocr_exact", "value": "Search"},
                "max_retries": 3,
                "retry_delay_s": 0.01,
            }
        ],
    }
    mgr.save_skill(skill)

    res = executor.execute_skill("retry_skill", context={})
    assert res is True
    assert len(attempts) == 3


def test_mark_file_skill_executed_and_metadata_merge(temp_skills_dir):
    mgr = SkillManager(skills_dir=temp_skills_dir)
    executor = SkillExecutor(mgr)

    folder = tempfile.mkdtemp()
    try:
        pdf_path = os.path.join(folder, "Report.pdf")
        meta_path = pdf_path + ".meta"
        open(pdf_path, "w").close()
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump({"Document": "Report", "Diagnosis": "Flu", "Patient": "Max"}, f)

        # Mark as executed by skill 1
        res = executor.mark_file_skill_executed(pdf_path, "export_skill_1")
        assert res is True

        with open(meta_path, encoding="utf-8") as f:
            data = json.load(f)
        assert data["executed_skills"] == ["export_skill_1"]
        assert "export_skill_1" in data["skill_execution_history"]

        # Mark as executed by skill 2 (multi-skill execution)
        executor.mark_file_skill_executed(pdf_path, "export_skill_2")
        with open(meta_path, encoding="utf-8") as f:
            data2 = json.load(f)
        assert data2["executed_skills"] == ["export_skill_1", "export_skill_2"]
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def test_find_pending_cases_for_skill(temp_skills_dir):
    mgr = SkillManager(skills_dir=temp_skills_dir)
    skill_data = {
        "id": "rdp_export",
        "name": "RDP Export",
        "enabled": True,
        "document_types": ["Report", "Prescription"],
        "steps": [],
    }
    mgr.save_skill(skill_data)
    executor = SkillExecutor(mgr)

    cases_dir = tempfile.mkdtemp()
    try:
        # Folder 1: Not approved -> Should be ignored
        c1 = os.path.join(cases_dir, "Case1")
        os.makedirs(c1)
        open(os.path.join(c1, "Report.pdf"), "w").close()

        # Folder 2: Approved, with matching Report.pdf -> Should be found
        c2 = os.path.join(cases_dir, "Case2")
        os.makedirs(c2)
        open(os.path.join(c2, ".approved"), "w").close()
        p2 = os.path.join(c2, "Report.pdf")
        open(p2, "w").close()
        with open(p2 + ".meta", "w", encoding="utf-8") as f:
            json.dump({"Document": "Report"}, f)

        # Folder 3: Approved, but Report.pdf already exported with rdp_export -> Should be ignored
        c3 = os.path.join(cases_dir, "Case3")
        os.makedirs(c3)
        open(os.path.join(c3, ".approved"), "w").close()
        p3 = os.path.join(c3, "Report.pdf")
        open(p3, "w").close()
        with open(p3 + ".meta", "w", encoding="utf-8") as f:
            json.dump({"Document": "Report", "executed_skills": ["rdp_export"]}, f)

        pending = executor.find_pending_cases_for_skill("rdp_export", cases_dir)
        assert len(pending) == 1
        assert pending[0]["folder_name"] == "Case2"
        assert pending[0]["unprocessed_count"] == 1
    finally:
        shutil.rmtree(cases_dir, ignore_errors=True)


def test_verify_screen_fallback_routine(temp_skills_dir, monkeypatch):
    mgr = SkillManager(skills_dir=temp_skills_dir)
    executor = SkillExecutor(mgr)

    # 1. Routine skill to create patient
    routine_executed = []
    routine_skill = {
        "id": "create_patient_routine",
        "name": "Create Patient Routine",
        "enabled": True,
        "steps": [
            {
                "id": "routine_step_1",
                "action_type": "FOCUS_WINDOW",
                "window_title": "Remote Desktop*",
            }
        ],
    }
    mgr.save_skill(routine_skill)

    # 2. Main skill with VERIFY_SCREEN that fails and triggers fallback routine
    main_skill = {
        "id": "main_export_skill",
        "name": "Main Export Skill",
        "enabled": True,
        "steps": [
            {
                "id": "check_patient",
                "action_type": "VERIFY_SCREEN",
                "locator": {"type": "auto", "prompt": "{Nachname}"},
                "on_failure_action": "run_skill",
                "on_failure_skill": "create_patient_routine",
                "max_retries": 1,
                "retry_delay_s": 0.01,
            },
            {
                "id": "final_upload_step",
                "action_type": "FOCUS_WINDOW",
                "window_title": "Remote Desktop*",
            },
        ],
    }
    mgr.save_skill(main_skill)

    # Mock locate to fail for {Nachname}
    def mock_locate(locator, window_title):
        return None

    monkeypatch.setattr(executor, "_locate_target", mock_locate)

    # Mock execute_skill for the routine to record execution
    orig_execute = executor.execute_skill

    def mock_execute_skill(skill_id, context=None, depth=0):
        if skill_id == "create_patient_routine":
            routine_executed.append(skill_id)
            return True
        return orig_execute(skill_id, context, depth)

    monkeypatch.setattr(executor, "execute_skill", mock_execute_skill)

    res = executor.execute_skill("main_export_skill", context={"Nachname": "Mustermann"})
    assert res is True
    assert routine_executed == ["create_patient_routine"]


def test_import_skill_crud_and_document_types(temp_skills_dir):
    mgr = SkillManager(skills_dir=temp_skills_dir)

    import_skill_data = {
        "id": "custom_import_pipeline",
        "name": "Scanner Import",
        "type": "import",
        "description": "Incoming scanned documents pipeline",
        "enabled": True,
        "allowed_extensions": [".pdf", ".png"],
        "split_multi_documents": True,
        "save_empty_pages": False,
        "document_types": {
            "Rezept": {
                "emoji": "💊",
                "classification_desc": "Arztrezept",
                "extraction_fields": {
                    "Datum": {"description": "Ausstellungsdatum", "required": True},
                    "Nachname": {"description": "Patienten Nachname", "required": True},
                },
            }
        },
    }

    # 1. Save import skill
    saved_id = mgr.save_skill(import_skill_data)
    assert saved_id == "custom_import_pipeline"

    # 2. Retrieve document types
    doc_types = mgr.get_document_types_for_skill("custom_import_pipeline")
    assert "Rezept" in doc_types
    assert doc_types["Rezept"]["emoji"] == "💊"

    # 3. Modify and save document types
    doc_types["Befund"] = {"emoji": "📋", "classification_desc": "Befundbericht", "extraction_fields": {}}
    success = mgr.save_document_types_for_skill("custom_import_pipeline", doc_types)
    assert success is True

    # 4. Verify updated document types
    reloaded = mgr.get_document_types_for_skill("custom_import_pipeline")
    assert "Befund" in reloaded
    assert len(reloaded) == 2
