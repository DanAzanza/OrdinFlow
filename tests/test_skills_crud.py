"""Unit tests for SkillManager CRUD, YAML serialization, and validation."""

from __future__ import annotations

import json
import os
import pytest

from core.skills.manager import SkillManager


def test_skill_manager_crud_and_duplicate(tmp_path):
    mgr = SkillManager(skills_dir=str(tmp_path))
    assert len(mgr.list_skills()) == 0

    # 1. Create and save skill
    skill_data = {
        "name": "Test Skill 1",
        "description": "First test skill",
        "enabled": True,
        "steps": [
            {"id": "step_1", "description": "Focus Window", "action_type": "FOCUS_WINDOW", "window_title": "Notepad*"}
        ],
    }
    saved_name = mgr.save_skill(skill_data)
    assert saved_name == "Test Skill 1"
    assert os.path.exists(os.path.join(str(tmp_path), "Test Skill 1.yaml"))

    # 2. Get skill
    loaded = mgr.get_skill("Test Skill 1")
    assert loaded is not None
    assert loaded["name"] == "Test Skill 1"
    assert loaded["id"] == "Test Skill 1"
    assert len(loaded["steps"]) == 1

    # 3. Duplicate skill
    dup = mgr.duplicate_skill("Test Skill 1")
    assert dup is not None
    assert dup["name"] == "Test Skill 1 (Copy)"
    assert dup["id"] == "Test Skill 1 (Copy)"
    assert len(mgr.list_skills()) == 2

    # 4. Delete skill
    deleted = mgr.delete_skill("Test Skill 1")
    assert deleted is True
    assert len(mgr.list_skills()) == 1


def test_skill_manager_name_validation_and_cascading_rename(tmp_path):
    mgr = SkillManager(skills_dir=str(tmp_path))

    # 1. Name validation
    is_valid, err = mgr.validate_name("")
    assert not is_valid
    is_valid, err = mgr.validate_name("Invalid:Path")
    assert not is_valid
    assert ":" in err
    is_valid, err = mgr.validate_name("Valid Skill Name")
    assert is_valid

    # 2. Setup skill A and skill B (which calls A)
    skill_a = {
        "name": "Export Routine",
        "enabled": True,
        "tasks": [
            {"id": "t1", "title": "Task 1", "actions": [{"action_type": "FOCUS_WINDOW", "window_title": "RDP*"}]}
        ],
    }
    mgr.save_skill(skill_a)

    skill_b = {
        "name": "Master Workflow",
        "enabled": True,
        "tasks": [
            {
                "id": "t1",
                "title": "Call Sub",
                "actions": [{"action_type": "CALL_SKILL", "skill_id": "Export Routine"}],
            }
        ],
        "document_types": {
            "Rezept": {"export_skill": "Export Routine"}
        }
    }
    mgr.save_skill(skill_b)

    # 3. Setup mock case .meta file in a temp cases dir
    cases_dir = os.path.join(str(tmp_path), "Cases")
    os.makedirs(cases_dir, exist_ok=True)
    meta_path = os.path.join(cases_dir, "test.meta")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({
            "executed_skills": ["Export Routine", "Other Skill"],
            "skill_execution_history": {"Export Routine": 12345.0}
        }, f)

    # 4. Perform cascading rename
    from routes.state import DashboardState
    from core.config import AppConfig
    cfg = AppConfig(base_dir=str(tmp_path))
    cfg.target_base_dir = cases_dir
    cfg.default_export_skill = "Export Routine"
    cfg.document_types = {"Rezept": {"export_skill": "Export Routine"}}
    orig_cfg = DashboardState.config
    try:
        DashboardState.config = cfg

        renamed = mgr.rename_skill("Export Routine", "Sanivision Export")
        assert renamed == "Sanivision Export"
        assert not os.path.exists(os.path.join(str(tmp_path), "Export Routine.yaml"))
        assert os.path.exists(os.path.join(str(tmp_path), "Sanivision Export.yaml"))

        # Verify skill B was cascaded
        loaded_b = mgr.get_skill("Master Workflow")
        assert loaded_b is not None
        assert loaded_b["tasks"][0]["actions"][0]["skill_id"] == "Sanivision Export"
        assert loaded_b["document_types"]["Rezept"]["export_skill"] == "Sanivision Export"

        # Verify config was cascaded
        assert DashboardState.config.default_export_skill == "Sanivision Export"
        assert DashboardState.config.document_types["Rezept"]["export_skill"] == "Sanivision Export"

        # Verify .meta file was cascaded
        with open(meta_path, "r", encoding="utf-8") as f:
            updated_meta = json.load(f)
        assert "Sanivision Export" in updated_meta["executed_skills"]
        assert "Export Routine" not in updated_meta["executed_skills"]
        assert "Sanivision Export" in updated_meta["skill_execution_history"]
    finally:
        DashboardState.config = orig_cfg


def test_import_skill_crud_and_document_types(tmp_path):
    mgr = SkillManager(skills_dir=str(tmp_path))

    import_skill_data = {
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
    assert saved_id == "Scanner Import"

    # 2. Retrieve document types
    doc_types = mgr.get_document_types_for_skill("Scanner Import")
    assert "Rezept" in doc_types
    assert doc_types["Rezept"]["emoji"] == "💊"

    # 3. Modify and save document types
    doc_types["Befund"] = {"emoji": "📋", "classification_desc": "Befundbericht", "extraction_fields": {}}
    success = mgr.save_document_types_for_skill("Scanner Import", doc_types)
    assert success is True

    # 4. Verify updated document types
    reloaded = mgr.get_document_types_for_skill("Scanner Import")
    assert "Befund" in reloaded
    assert len(reloaded) == 2


def test_path_traversal_sanitization_and_rejection(tmp_path):
    from core.utils import sanitize_safe_path

    # 1. Traversal sequences rejected
    is_safe, _ = sanitize_safe_path("..\\..\\Windows\\System32\\cmd.exe")
    assert not is_safe
    is_safe, _ = sanitize_safe_path("../../etc/passwd")
    assert not is_safe
    is_safe, _ = sanitize_safe_path("C:\\Cases\\..\\..\\malicious.exe")
    assert not is_safe

    # 2. Null byte rejected
    is_safe, _ = sanitize_safe_path("C:\\safe\\path\x00.exe")
    assert not is_safe

    # 3. Valid paths accepted and normalized
    is_safe, clean = sanitize_safe_path("C:\\Users\\danie\\Desktop\\output.pdf")
    assert is_safe
    assert "output.pdf" in clean

    # 4. SkillManager rejects saving skill with path traversal in TYPE_FILE_PATH
    mgr = SkillManager(skills_dir=str(tmp_path))
    malicious_skill = {
        "name": "Malicious Traversal Skill",
        "tasks": [
            {
                "id": "t1",
                "title": "Unsafe Task",
                "actions": [
                    {
                        "id": "act_1",
                        "action_type": "TYPE_FILE_PATH",
                        "file_path": "..\\..\\sensitive_file.txt",
                    }
                ],
            }
        ],
    }
    with pytest.raises(ValueError, match="Security error: Invalid path with directory traversal"):
        mgr.save_skill(malicious_skill)


def test_sensitive_credential_detection_and_masking():
    from core.utils import is_sensitive_credential_text
    from core.skills.engines.export_engine import ExportEngine

    # 1. Detection
    assert is_sensitive_credential_text("mySecretPassword123", "Enter Password") is True
    assert is_sensitive_credential_text("1234", "PIN Eingabe") is True
    assert is_sensitive_credential_text("sk-live-12345", "API Token") is True
    assert is_sensitive_credential_text("Normal text", "Click on Button") is False

    # 2. ExportEngine execution masks sensitive credential
    skill_def = {
        "name": "Credential Masking Skill",
        "tasks": [
            {
                "id": "task_1",
                "title": "Login Task",
                "actions": [
                    {
                        "id": "act_sec",
                        "action_type": "TYPE_TEXT",
                        "description": "Enter user password",
                        "text": "SuperSecretPass!",
                        "is_secret": True,
                    }
                ],
            }
        ],
    }
    engine = ExportEngine(skill_def)
    assert len(engine.actions) == 1
    assert engine.actions[0]["is_secret"] is True


def test_gui_workflow_skill_structure(tmp_path):
    sm = SkillManager(skills_dir=str(tmp_path))
    skill_data = {
        "name": "Generic GUI Workflow Skill",
        "type": "export",
        "target_window": "TargetApp*",
        "tasks": [
            {
                "id": "t1",
                "actions": [
                    {"id": "a1", "action_type": "FOCUS_WINDOW", "window_title": "TargetApp*"},
                    {"id": "a2", "action_type": "HOTKEY", "keys": ["ctrl", "o"]},
                    {"id": "a3", "action_type": "TYPE_FILE_PATH", "file_path": "{document_fullpath}"},
                    {"id": "a4", "action_type": "TYPE_TEXT", "text": "sample"},
                ],
            }
        ],
    }
    sm.save_skill(skill_data)
    loaded = sm.get_skill("Generic GUI Workflow Skill")
    assert loaded is not None
    assert loaded.get("type") == "export"
    assert loaded.get("target_window") == "TargetApp*"
    all_action_types = [
        act.get("action_type")
        for task in loaded.get("tasks", [])
        for act in task.get("actions", [])
    ]
    assert "FOCUS_WINDOW" in all_action_types
    assert "HOTKEY" in all_action_types
    assert "TYPE_FILE_PATH" in all_action_types
    assert "TYPE_TEXT" in all_action_types
    assert "POWERSHELL" not in all_action_types
