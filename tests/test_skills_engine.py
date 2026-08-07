"""
Unit Tests für OrdinFlow Skills Engine (core/skills_engine.py)
"""
import os
import shutil
import tempfile

import pytest

from core.skills_engine import (
    SkillExecutor,
    SkillManager,
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

    # 1. Create / Save Skill
    skill_data = {
        "id": "test_skill_1",
        "name": "Test Skill 1",
        "description": "Erster Test Skill",
        "enabled": True,
        "steps": [
            {
                "id": "step_1",
                "description": "Fokussiere Fenster",
                "action_type": "FOCUS_WINDOW",
                "window_title": "Notepad*"
            }
        ]
    }
    saved_id = mgr.save_skill(skill_data)
    assert saved_id == "test_skill_1"
    assert os.path.exists(os.path.join(temp_skills_dir, "test_skill_1.yaml"))

    # 2. Get Skill
    loaded = mgr.get_skill("test_skill_1")
    assert loaded is not None
    assert loaded["name"] == "Test Skill 1"
    assert len(loaded["steps"]) == 1

    # 3. Duplicate Skill
    dup = mgr.duplicate_skill("test_skill_1")
    assert dup is not None
    assert dup["id"].startswith("test_skill_1_copy_")
    assert "Copy" in dup["name"] or "Kopie" in dup["name"]
    assert len(mgr.list_skills()) == 2

    # 4. Delete Skill
    deleted = mgr.delete_skill("test_skill_1")
    assert deleted is True
    assert len(mgr.list_skills()) == 1


def test_input_shield_crash_safety():
    """Stellt sicher, dass InputShield auch bei Exceptions zuverlässig freigibt."""
    with pytest.raises(ValueError):
        with input_shield(enabled=False):  # In Tests ohne Win32 UI
            raise ValueError("Test-Fehler innerhalb der Sperre")

    # Prüfe manuellen Call
    set_block_input(False)


def test_substitute_placeholders(temp_skills_dir):
    mgr = SkillManager(skills_dir=temp_skills_dir)
    executor = SkillExecutor(mgr)

    ctx = {"Nachname": "Mustermann", "Vorname": "Erika", "document_fullpath": "C:/docs/file.pdf"}
    res = executor._substitute_placeholders("Hallo {Vorname} {Nachname}, Datei: {document_fullpath}", ctx)
    assert res == "Hallo Erika Mustermann, Datei: C:/docs/file.pdf"


def test_sub_skill_execution(temp_skills_dir):
    mgr = SkillManager(skills_dir=temp_skills_dir)

    # Sub-Skill anlegen
    sub_skill = {
        "id": "sub_skill_1",
        "name": "Sub Skill 1",
        "enabled": True,
        "steps": [
            {"id": "sub_step_1", "description": "Sub Action", "action_type": "FOCUS_WINDOW"}
        ]
    }
    mgr.save_skill(sub_skill)

    # Haupt-Skill anlegen
    main_skill = {
        "id": "main_skill",
        "name": "Main Skill",
        "enabled": True,
        "steps": [
            {"id": "call_sub", "description": "Call Subskill", "action_type": "CALL_SKILL", "skill_id": "sub_skill_1"}
        ]
    }
    mgr.save_skill(main_skill)

    executor = SkillExecutor(mgr)
    success = executor.execute_skill("main_skill", context={})
    assert success is True


def test_document_type_filtering(temp_skills_dir):
    mgr = SkillManager(skills_dir=temp_skills_dir)
    executor = SkillExecutor(mgr)

    # Erstelle temporäre Test-Dateien
    folder = tempfile.mkdtemp()
    try:
        f1 = os.path.join(folder, "Lieferschein__Software__2026.pdf")
        f2 = os.path.join(folder, "Vertrag__Software__2026.pdf")
        open(f1, "w").close()
        open(f2, "w").close()

        # 1. Filter mit spezifischem Typ
        matched = executor.filter_matching_files(folder, allowed_types=["Lieferschein"])
        assert len(matched) == 1
        assert matched[0]["filename"] == "Lieferschein__Software__2026.pdf"

        # 2. Filter mit '*' (alle)
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
                "locator": {"type": "ocr_exact", "value": "Suchen"},
                "max_retries": 3,
                "retry_delay_s": 0.01,
            }
        ],
    }
    mgr.save_skill(skill)

    res = executor.execute_skill("retry_skill", context={})
    assert res is True
    assert len(attempts) == 3


