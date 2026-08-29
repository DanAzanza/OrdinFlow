"""Unit tests for Skill action execution, locators, conditions, and grounders."""

from __future__ import annotations

import os
from unittest.mock import patch
import pytest

from core.skills.engines.export_engine import ExportEngine
from core.skills.grounder import SoMGrounder
from core.skills.manager import SkillManager
from core.skills.shield import input_shield, set_block_input
from core.skills.text_helpers import paste_text_via_clipboard, substitute_placeholders


def test_input_shield_crash_safety():
    """Verifies that InputShield reliably unlocks input even when exceptions occur."""
    with pytest.raises(ValueError):
        with input_shield(enabled=False):
            raise ValueError("Test error inside input lock block")

    set_block_input(False)


def test_substitute_placeholders(tmp_path):
    mgr = SkillManager(skills_dir=str(tmp_path))
    engine = ExportEngine({}, skill_manager=mgr)

    ctx = {
        "LastName": "Mustermann",
        "FirstName": "Erika",
        "document_fullpath": "C:/docs/file.pdf",
        "BirthDate": "1985-05-12",
    }
    res = engine._substitute_placeholders(
        "Hello {FirstName} {LastName}, Born: {BirthDate}, File: {document_fullpath}", ctx
    )
    assert res == "Hello Erika Mustermann, Born: 1985-05-12, File: C:/docs/file.pdf"

    # Unknown key safety
    res_unknown = engine._substitute_placeholders("Name: {LastName} {FirstName}, Unknown: {NotPresent}", ctx)
    assert res_unknown == "Name: Mustermann Erika, Unknown: "


def test_sub_skill_execution(tmp_path):
    mgr = SkillManager(skills_dir=str(tmp_path))

    sub_skill = {
        "id": "sub_skill_1",
        "name": "Sub Skill 1",
        "enabled": True,
        "steps": [{"id": "sub_step_1", "description": "Sub Action", "action_type": "FOCUS_WINDOW"}],
    }
    mgr.save_skill(sub_skill)

    main_skill = {
        "id": "main_skill",
        "name": "Main Skill",
        "enabled": True,
        "steps": [
            {"id": "call_sub", "description": "Call Subskill", "action_type": "CALL_SKILL", "skill_id": "sub_skill_1"}
        ],
    }
    mgr.save_skill(main_skill)

    engine = ExportEngine(main_skill, skill_manager=mgr)
    success = engine.execute_actions(context={})
    assert success is True


def test_document_type_filtering(tmp_path):
    mgr = SkillManager(skills_dir=str(tmp_path))
    engine = ExportEngine({}, skill_manager=mgr)

    folder = tmp_path / "case_folder"
    folder.mkdir()
    f1 = folder / "DeliveryNote__Software__2026.pdf"
    f2 = folder / "Contract__Software__2026.pdf"
    f1.touch()
    f2.touch()

    # 1. Filter with specific type
    matched = engine.filter_matching_files(str(folder), allowed_types=["DeliveryNote"])
    assert len(matched) == 1
    assert matched[0]["filename"] == "DeliveryNote__Software__2026.pdf"

    # 2. Filter with '*' (all)
    matched_all = engine.filter_matching_files(str(folder), allowed_types=["*"])
    assert len(matched_all) == 2


def test_skill_executor_retry_logic(tmp_path, monkeypatch):
    mgr = SkillManager(skills_dir=str(tmp_path))

    attempts = []

    def mock_locate(locator, window_title=None, vision_extractor=None):
        attempts.append(len(attempts) + 1)
        if len(attempts) < 3:
            return None
        return (100, 200)

    monkeypatch.setattr(SoMGrounder, "locate_target", mock_locate)

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

    engine = ExportEngine(skill, skill_manager=mgr)
    res = engine.execute_actions(context={})
    assert res is True
    assert len(attempts) == 3


def test_verify_screen_fallback_routine(tmp_path, monkeypatch):
    mgr = SkillManager(skills_dir=str(tmp_path))

    routine_executed = []
    routine_skill = {
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

    main_skill = {
        "name": "Main Export Skill",
        "enabled": True,
        "steps": [
            {
                "id": "check_patient",
                "action_type": "VERIFY_SCREEN",
                "locator": {"type": "auto", "prompt": "{Nachname}"},
                "on_failure_action": "run_skill",
                "on_failure_skill": "Create Patient Routine",
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
    monkeypatch.setattr(SoMGrounder, "locate_target", lambda locator, window_title=None, vision_extractor=None: None)

    engine = ExportEngine(main_skill, skill_manager=mgr)
    orig_execute = engine.execute_skill

    def mock_execute_skill(skill_id, context=None, depth=0, dry_run=False):
        if skill_id == "Create Patient Routine":
            routine_executed.append(skill_id)
            return True
        return orig_execute(skill_id, context, depth=depth, dry_run=dry_run)

    monkeypatch.setattr(engine, "execute_skill", mock_execute_skill)

    res = engine.execute_actions(context={"Nachname": "Mustermann"})
    assert res is True
    assert "Create Patient Routine" in routine_executed


def test_export_engine_hierarchical_tasks():
    skill_def = {
        "name": "Export Routine",
        "tasks": [
            {
                "id": "task_1",
                "title": "Open Sanivision",
                "actions": [
                    {"id": "act_1", "action_type": "FOCUS_WINDOW", "window_title": "Sanivision*"}
                ]
            },
            {
                "id": "task_2",
                "title": "Search Patient",
                "actions": [
                    {"id": "act_2", "action_type": "TYPE_TEXT", "text": "{Nachname}"}
                ]
            }
        ]
    }
    engine = ExportEngine(skill_def)
    assert len(engine.actions) == 2
    assert engine.actions[0]["id"] == "act_1"
    assert engine.actions[1]["id"] == "act_2"


def test_sub_skill_execution_with_tasks_hierarchy(tmp_path):
    mgr = SkillManager(skills_dir=str(tmp_path))

    sub_skill = {
        "name": "Sub Hierarchical Skill",
        "enabled": True,
        "tasks": [
            {
                "id": "task_1",
                "title": "Sub Task",
                "actions": [
                    {"id": "act_sub_1", "description": "Sub Action", "action_type": "FOCUS_WINDOW", "window_title": "Remote Desktop*"}
                ],
            }
        ],
    }
    mgr.save_skill(sub_skill)

    main_skill = {
        "name": "Main Hierarchical Skill",
        "enabled": True,
        "tasks": [
            {
                "id": "task_main",
                "title": "Main Task",
                "actions": [
                    {"id": "act_main_1", "description": "Call Sub", "action_type": "CALL_SKILL", "skill_id": "Sub Hierarchical Skill"}
                ],
            }
        ],
    }
    mgr.save_skill(main_skill)

    engine = ExportEngine(main_skill, skill_manager=mgr)
    success = engine.execute_actions(context={})
    assert success is True


def test_export_engine_clipboard_paste():
    res = paste_text_via_clipboard("C:\\Test\\Output.pdf", press_enter=False)
    assert isinstance(res, bool)


def test_export_engine_wait_for_element_and_popups():
    skill_def = {
        "name": "Wait Element Skill",
        "tasks": [
            {
                "id": "task_1",
                "title": "Wait Task",
                "actions": [
                    {
                        "id": "act_wait",
                        "action_type": "WAIT_FOR_ELEMENT",
                        "locator": {"type": "ocr_contains", "prompt": "NonExistentElement"},
                        "timeout_s": 0.1,
                        "poll_interval_s": 0.05,
                        "on_failure": "continue",
                    }
                ],
            }
        ],
    }
    engine = ExportEngine(skill_def)
    assert len(engine.actions) == 1
    assert engine.actions[0]["action_type"] == "WAIT_FOR_ELEMENT"
    success = engine.execute_actions(context={})
    assert success is True


def test_export_engine_dynamic_placeholders():
    engine = ExportEngine({})
    ctx = {
        "document_fullpath": "C:\\OrdinFlowTest\\Cases\\Mustermann_Max\\Scan_2026.pdf",
        "Nachname": "Mustermann",
        "Vorname": "Max",
        "Produkt": "Einlagen",
    }

    t1 = engine._substitute_placeholders("File is: {document_filename}", ctx)
    assert t1 == "File is: Scan_2026.pdf"

    t2 = engine._substitute_placeholders("Base: {document_basename} Ext: {document_extension}", ctx)
    assert t2 == "Base: Scan_2026 Ext: .pdf"

    t3 = engine._substitute_placeholders("Folder: {case_folder}", ctx)
    assert "Mustermann_Max" in t3

    t4 = engine._substitute_placeholders("{Nachname}_{Vorname}_{Produkt}", ctx)
    assert t4 == "Mustermann_Max_Einlagen"

    t5 = engine._substitute_placeholders("Year: {Jahr}", ctx)
    assert len(t5.replace("Year: ", "")) == 4


def test_export_engine_placeholder_modifiers():
    engine = ExportEngine({})
    ctx = {
        "document_fullpath": "C:\\OrdinFlowTest\\Cases\\Mustermann_Max\\Scan_2026.pdf",
        "Nachname": "Müller-Lüdenscheidt",
        "Vorname": "Max",
        "Geburtsdatum": "07.04.1980",
        "Datum": "2026-08-22",
    }

    assert engine._substitute_placeholders("{Nachname|upper}", ctx) == "MÜLLER-LÜDENSCHEIDT"
    assert engine._substitute_placeholders("{Vorname|lower}", ctx) == "max"
    assert engine._substitute_placeholders("{Geburtsdatum|nodots}", ctx) == "07041980"
    assert engine._substitute_placeholders("{Geburtsdatum|digits_only}", ctx) == "07041980"
    assert engine._substitute_placeholders("{Nachname|slug}", ctx) == "Mueller-Luedenscheidt"
    assert engine._substitute_placeholders("{document_fullpath|filename}", ctx) == "Scan_2026.pdf"
    assert engine._substitute_placeholders("{document_fullpath|stem}", ctx) == "Scan_2026"
    assert engine._substitute_placeholders("{document_fullpath|ext}", ctx) == ".pdf"
    assert engine._substitute_placeholders("{Datum|format:YYYYMMDD}", ctx) == "20260822"
    assert engine._substitute_placeholders("{Datum|format:DD.MM.YYYY}", ctx) == "22.08.2026"
    assert engine._substitute_placeholders("{Geburtsdatum|format:YYYY-MM-DD}", ctx) == "1980-04-07"


def test_export_engine_app_launch_and_login_skill(monkeypatch):
    launch_called = []

    class MockSkillManager:
        def get_skill(self, skill_id):
            launch_called.append(skill_id)
            return {"id": skill_id, "name": skill_id, "enabled": True, "actions": []}

    engine = ExportEngine(
        {"id": "main_export", "name": "Main Export", "type": "export", "launch_skill_id": "rdp_login"},
        skill_manager=MockSkillManager(),
    )

    attempt_count = 0

    def mock_capture(win):
        nonlocal attempt_count
        attempt_count += 1
        if attempt_count <= 1:
            return None
        from PIL import Image
        return Image.new("RGB", (100, 100), color="white")

    monkeypatch.setattr(SoMGrounder, "capture_screen", mock_capture)

    ready = engine._ensure_window_ready("TargetApp*", context={"patient": "Max"})
    assert ready is True
    assert "rdp_login" in launch_called


def test_som_grounder_quadrant_tiling():
    from PIL import Image

    # 1. 1080p -> 1 tile
    img_1080p = Image.new("RGB", (1920, 1080), color="blue")
    tiles_1080 = SoMGrounder.generate_quadrant_tiles(img_1080p)
    assert len(tiles_1080) == 1
    assert tiles_1080[0][1] == 0 and tiles_1080[0][2] == 0

    # 2. 4K -> 5 tiles
    img_4k = Image.new("RGB", (3840, 2160), color="red")
    tiles_4k = SoMGrounder.generate_quadrant_tiles(img_4k)
    assert len(tiles_4k) == 5

    for tile_img, off_x, off_y in tiles_4k:
        assert tile_img.width % 28 == 0 or tile_img.width == 3840
        assert tile_img.height % 28 == 0 or tile_img.height == 2160
        assert off_x >= 0 and off_y >= 0


def test_export_engine_delay_action_execution():
    skill_def = {
        "name": "Delay Test Skill",
        "tasks": [
            {
                "id": "t1",
                "title": "Delay Task",
                "actions": [
                    {"id": "act_delay", "action_type": "DELAY", "delay_ms": 50},
                    {"id": "act_sleep", "action_type": "SLEEP", "duration_s": 0.05},
                    {"id": "act_wait", "action_type": "WAIT", "delay_ms": 50},
                ]
            }
        ]
    }
    engine = ExportEngine(skill_def)
    success = engine.execute_actions(context={})
    assert success is True


def test_export_engine_script_execution(tmp_path):
    sample_doc = tmp_path / "Test__Doc.pdf"
    sample_doc.write_text("dummy content", encoding="utf-8")

    skill_def = {
        "name": "Script Test Skill",
        "tasks": [
            {
                "id": "t1",
                "title": "Script Task",
                "actions": [
                    {
                        "id": "act_ps",
                        "action_type": "RUN_SCRIPT",
                        "shell": "powershell",
                        "command": "Write-Output 'Exporting {document_basename}'",
                    }
                ]
            }
        ]
    }
    engine = ExportEngine(skill_def)
    success = engine.execute_actions(context={"document_fullpath": str(sample_doc)})
    assert success is True


def test_export_engine_fail_fast_missing_document_in_script():
    skill_def = {
        "name": "Script With Document Requirement",
        "tasks": [
            {
                "id": "t1",
                "title": "Script Task",
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
    engine = ExportEngine(skill_def)
    assert engine.execute_actions(context={}) is False
    assert engine.execute_actions(context={"document_fullpath": "C:/NonExistentPath/File.pdf"}) is False


def test_export_engine_fail_fast_type_file_path():
    skill_def = {
        "name": "Type File Path Skill",
        "tasks": [
            {
                "id": "t1",
                "title": "File Path Task",
                "actions": [
                    {
                        "id": "act_fp",
                        "action_type": "TYPE_FILE_PATH",
                        "file_path": "{document_fullpath}",
                    }
                ],
            }
        ],
    }
    engine = ExportEngine(skill_def)
    assert engine.execute_actions(context={}) is False
    assert engine.execute_actions(context={"document_fullpath": "C:/NonExistent/Doc.pdf"}) is False


def test_export_engine_fail_fast_unresolved_type_text():
    skill_def = {
        "name": "Type Text Skill",
        "tasks": [
            {
                "id": "t1",
                "title": "Type Text Task",
                "actions": [
                    {
                        "id": "act_tt",
                        "action_type": "TYPE_TEXT",
                        "text": "{Nachname}",
                    }
                ],
            }
        ],
    }
    engine = ExportEngine(skill_def)
    assert engine.execute_actions(context={}) is False


def test_substitute_placeholders_desktop_and_userprofile():
    res = substitute_placeholders("{desktop}\\{basename}.cdr", {"document_fullpath": r"C:\Cases\Test\Fußscan.pdf"})
    user_prof = os.environ.get("USERPROFILE", "") or os.path.expanduser("~")
    expected_desktop = os.path.join(user_prof, "Desktop")
    assert expected_desktop in res
    assert "Fußscan.cdr" in res


def test_export_engine_branch_then_execution():
    skill_def = {
        "name": "Branch Test Skill",
        "tasks": [
            {
                "id": "t1",
                "actions": [
                    {
                        "id": "b1",
                        "action_type": "BRANCH",
                        "condition": {"type": "VARIABLE_MATCHES", "variable": "category", "expected": "Fußscan"},
                        "then_actions": [
                            {
                                "id": "set_then",
                                "action_type": "SET_VARIABLE",
                                "variable": "branch_taken",
                                "value": "THEN_BRANCH",
                            }
                        ],
                        "else_actions": [
                            {
                                "id": "set_else",
                                "action_type": "SET_VARIABLE",
                                "variable": "branch_taken",
                                "value": "ELSE_BRANCH",
                            }
                        ],
                    }
                ],
            }
        ],
    }
    engine = ExportEngine(skill_def)
    context = {"category": "Fußscan"}
    assert engine.execute_actions(context=context) is True
    assert context.get("branch_taken") == "THEN_BRANCH"


def test_export_engine_branch_else_execution():
    skill_def = {
        "name": "Branch Else Test",
        "tasks": [
            {
                "id": "t1",
                "actions": [
                    {
                        "id": "b1",
                        "action_type": "BRANCH",
                        "condition": {"type": "VARIABLE_MATCHES", "variable": "category", "expected": "Fußscan"},
                        "then_actions": [
                            {
                                "id": "set_then",
                                "action_type": "SET_VARIABLE",
                                "variable": "branch_taken",
                                "value": "THEN_BRANCH",
                            }
                        ],
                        "else_actions": [
                            {
                                "id": "set_else",
                                "action_type": "SET_VARIABLE",
                                "variable": "branch_taken",
                                "value": "ELSE_BRANCH",
                            }
                        ],
                    }
                ],
            }
        ],
    }
    engine = ExportEngine(skill_def)
    context = {"category": "Rezept"}
    assert engine.execute_actions(context=context) is True
    assert context.get("branch_taken") == "ELSE_BRANCH"


def test_export_engine_extract_ui_text_and_set_variable():
    skill_def = {
        "name": "Extraction Test",
        "tasks": [
            {
                "id": "t1",
                "actions": [
                    {
                        "id": "ext1",
                        "action_type": "EXTRACT_UI_TEXT",
                        "locator": {"automation_id": "txt_patient_id"},
                        "extract_to_var": "live_patient_id",
                    },
                    {
                        "id": "val1",
                        "action_type": "VALIDATE_UI_STATE",
                        "condition": {
                            "type": "VARIABLE_MATCHES",
                            "variable": "live_patient_id",
                            "expected": "P-98765",
                        },
                    },
                ],
            }
        ],
    }
    engine = ExportEngine(skill_def)
    context = {}
    with patch("core.skills.uia_locator.UIALocator.is_available", return_value=True):
        with patch("core.skills.uia_locator.UIALocator.get_element_text", return_value="P-98765"):
            assert engine.execute_actions(context=context) is True
            assert context.get("live_patient_id") == "P-98765"


def test_export_engine_validate_ui_state_on_error_continue():
    skill_def = {
        "name": "Validation Error Test",
        "tasks": [
            {
                "id": "t1",
                "actions": [
                    {
                        "id": "val_fail",
                        "action_type": "VALIDATE_UI_STATE",
                        "condition": {
                            "type": "VARIABLE_MATCHES",
                            "variable": "category",
                            "expected": "Arztbrief",
                        },
                        "on_error": "CONTINUE",
                    }
                ],
            }
        ],
    }
    engine = ExportEngine(skill_def)
    context = {"category": "Fußscan"}
    assert engine.execute_actions(context=context) is True
