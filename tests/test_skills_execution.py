"""Unit tests for Skill action execution, locators, conditions, and grounders."""

from __future__ import annotations

import os
import pytest

from core.skills.action_executor import execute_type_file_path
from core.skills.engines.export_engine import ExportEngine
from core.skills.exceptions import SkillActionError
from core.skills.grounder import SoMGrounder
from core.skills.manager import SkillManager
from core.skills.models import SkillTask
from core.skills.shield import input_shield, set_block_input
from core.skills.text_helpers import substitute_placeholders


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
    with pytest.raises(SkillActionError) as exc_info:
        engine.execute_actions(context={})
    assert "document_fullpath" in str(exc_info.value)

    with pytest.raises(SkillActionError) as exc_info:
        engine.execute_actions(context={"document_fullpath": "C:/NonExistentPath/File.pdf"})
    assert "document_fullpath" in str(exc_info.value)


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
    with pytest.raises(SkillActionError) as exc_info:
        engine.execute_actions(context={})
    assert "empty or unresolved" in str(exc_info.value)

    with pytest.raises(SkillActionError) as exc_info:
        engine.execute_actions(context={"document_fullpath": "C:/NonExistent/Doc.pdf"})
    assert "Doc.pdf" in str(exc_info.value) or "invalid" in str(exc_info.value)


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
    with pytest.raises(SkillActionError) as exc_info:
        engine.execute_actions(context={})
    assert "Nachname" in str(exc_info.value)


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


def test_export_engine_folder_metadata_auto_extraction(tmp_path):
    case_folder = tmp_path / "Mustermann__Erika__1985-05-12"
    case_folder.mkdir(parents=True)
    pdf_file = case_folder / "Befund__2026.pdf"
    pdf_file.touch()

    skill_def = {
        "id": "meta_extractor_skill",
        "name": "Meta Extractor Skill",
        "steps": [
            {
                "id": "set_last",
                "action_type": "SET_VARIABLE",
                "variable": "saved_last",
                "value": "{Nachname}",
            },
            {
                "id": "set_first",
                "action_type": "SET_VARIABLE",
                "variable": "saved_first",
                "value": "{Vorname}",
            },
        ],
    }
    engine = ExportEngine(skill_def)
    task = SkillTask(
        id="task_meta",
        skill_id="meta_extractor_skill",
        skill_name="Meta Extractor",
        skill_type="export",
        context={"folder_path": str(case_folder)},
    )
    result = engine.execute(task)
    assert result.success is True
    assert result.data.get("status") == "completed"


def test_type_file_path_save_mode_and_rdp(tmp_path, monkeypatch):
    dest_dir = tmp_path / "sub_exports"
    dest_file = dest_dir / "target_output.cdr"
    assert not dest_dir.exists()

    pasted_values: list[str] = []
    monkeypatch.setattr(
        "core.skills.action_executor.paste_text_via_clipboard",
        lambda text, *args, **kwargs: pasted_values.append(text) or True,
    )

    step = {
        "id": "save_as_file",
        "action_type": "TYPE_FILE_PATH",
        "mode": "save",
        "file_path": str(dest_file),
    }

    ok = execute_type_file_path(
        step=step,
        step_id="save_as_file",
        context={},
        target_window=None,
        rdp_prefix=r"\\tsclient\G",
        substitute_fn=substitute_placeholders,
    )
    assert ok is True
    assert dest_dir.is_dir()
    assert len(pasted_values) == 1
    assert "target_output.cdr" in pasted_values[0]


def test_skill_action_error_bubbling_to_task_result(tmp_path):
    case_folder = tmp_path / "Muster_Case"
    case_folder.mkdir()
    pdf_file = case_folder / "Doc__1.pdf"
    pdf_file.touch()

    skill_def = {
        "id": "failing_skill",
        "name": "Failing Skill",
        "steps": [
            {
                "id": "broken_step",
                "action_type": "TYPE_TEXT",
                "text": "{NonExistentPlaceholder}",
                "on_failure": "stop",
            }
        ],
    }
    engine = ExportEngine(skill_def)
    task = SkillTask(
        id="task_fail",
        skill_id="failing_skill",
        skill_name="Failing Skill",
        skill_type="export",
        context={"folder_path": str(case_folder)},
    )
    result = engine.execute(task)
    assert result.success is False
    assert result.error is not None
    assert "broken_step" in result.error
    assert "NonExistentPlaceholder" in result.error
    assert result.data.get("status") == "failed"


def test_export_engine_execute_skill_delegates_without_mutating_self():
    class DummyManager:
        def __init__(self):
            self.skills = {
                "child_skill": {
                    "id": "child_skill",
                    "name": "Child Skill",
                    "type": "export",
                    "actions": [
                        {"id": "c1", "action_type": "SET_VARIABLE", "variable": "child_ran", "value": "true"}
                    ],
                }
            }

        def get_skill(self, sid):
            return self.skills.get(sid)

        def get_skill_engine(self, sid, vision_extractor=None):
            s = self.skills.get(sid)
            return ExportEngine(s, skill_manager=self, vision_extractor=vision_extractor) if s else None

    mgr = DummyManager()
    parent_engine = ExportEngine(
        {"id": "parent_skill", "name": "Parent Skill", "type": "export", "target_window": "ParentWindow"},
        skill_manager=mgr,
    )

    ctx = {}
    ok = parent_engine.execute_skill("child_skill", context=ctx)
    assert ok is True
    assert ctx["child_ran"] == "true"

    # Crucial: parent_engine instance must NOT have mutated its identity or target window
    assert parent_engine.id == "parent_skill"
    assert parent_engine.name == "Parent Skill"
    assert parent_engine.target_window == "ParentWindow"


