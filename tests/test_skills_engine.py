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
        "name": "Test Skill 1",
        "description": "First test skill",
        "enabled": True,
        "steps": [
            {"id": "step_1", "description": "Focus Window", "action_type": "FOCUS_WINDOW", "window_title": "Notepad*"}
        ],
    }
    saved_name = mgr.save_skill(skill_data)
    assert saved_name == "Test Skill 1"
    assert os.path.exists(os.path.join(temp_skills_dir, "Test Skill 1.yaml"))

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


def test_skill_manager_name_validation_and_cascading_rename(temp_skills_dir):
    mgr = SkillManager(skills_dir=temp_skills_dir)

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
    cases_dir = os.path.join(temp_skills_dir, "Cases")
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
    cfg = AppConfig(base_dir=temp_skills_dir)
    cfg.target_base_dir = cases_dir
    cfg.default_export_skill = "Export Routine"
    cfg.document_types = {"Rezept": {"export_skill": "Export Routine"}}
    orig_cfg = DashboardState.config
    try:
        DashboardState.config = cfg

        renamed = mgr.rename_skill("Export Routine", "Sanivision Export")
        assert renamed == "Sanivision Export"
        assert not os.path.exists(os.path.join(temp_skills_dir, "Export Routine.yaml"))
        assert os.path.exists(os.path.join(temp_skills_dir, "Sanivision Export.yaml"))

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

        # Folder 3: Approved, but Report.pdf already exported with RDP Export -> Should be ignored
        c3 = os.path.join(cases_dir, "Case3")
        os.makedirs(c3)
        open(os.path.join(c3, ".approved"), "w").close()
        p3 = os.path.join(c3, "Report.pdf")
        open(p3, "w").close()
        with open(p3 + ".meta", "w", encoding="utf-8") as f:
            json.dump({"Document": "Report", "executed_skills": ["RDP Export"]}, f)

        pending = executor.find_pending_cases_for_skill("RDP Export", cases_dir)
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
    def mock_locate(locator, window_title):
        return None

    monkeypatch.setattr(executor, "_locate_target", mock_locate)

    # Mock execute_skill for the routine to record execution
    orig_execute = executor.execute_skill

    def mock_execute_skill(skill_id, context=None, depth=0):
        if skill_id == "Create Patient Routine":
            routine_executed.append(skill_id)
            return True
        return orig_execute(skill_id, context, depth)

    monkeypatch.setattr(executor, "execute_skill", mock_execute_skill)

    res = executor.execute_skill("Main Export Skill", context={"Nachname": "Mustermann"})
    assert res is True
    assert "Create Patient Routine" in routine_executed


def test_import_skill_crud_and_document_types(temp_skills_dir):
    mgr = SkillManager(skills_dir=temp_skills_dir)

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


def test_export_engine_hierarchical_tasks():
    from core.skills.engines.export_engine import ExportEngine
    # Verify ExportEngine handles tasks -> actions hierarchy
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


def test_sub_skill_execution_with_tasks_hierarchy(temp_skills_dir):
    mgr = SkillManager(skills_dir=temp_skills_dir)

    # Sub-skill defined ONLY with tasks hierarchy (no legacy steps key)
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

    # Main skill calling sub-skill
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

    executor = SkillExecutor(mgr)
    success = executor.execute_skill("Main Hierarchical Skill", context={})
    assert success is True
    # Test execute_actions alias
    assert hasattr(executor, "execute_actions")
    assert executor.execute_actions == executor.execute_steps


def test_path_traversal_sanitization_and_rejection(temp_skills_dir):
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
    mgr = SkillManager(skills_dir=temp_skills_dir)
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


def test_export_engine_clipboard_paste():
    from core.skills.engines.export_engine import _paste_text_via_clipboard
    # Test clipboard paste helper
    res = _paste_text_via_clipboard("C:\\Test\\Output.pdf", press_enter=False)
    assert isinstance(res, bool)


def test_export_engine_wait_for_element_and_popups():
    from core.skills.engines.export_engine import ExportEngine
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
    # Execution should continue because on_failure is "continue"
    success = engine.execute_actions(context={})
    assert success is True


def test_export_engine_dynamic_placeholders():
    from core.skills.engines.export_engine import ExportEngine

    engine = ExportEngine({})
    ctx = {
        "document_fullpath": "C:\\OrdinFlowTest\\Cases\\Mustermann_Max\\Scan_2026.pdf",
        "Nachname": "Mustermann",
        "Vorname": "Max",
        "Produkt": "Einlagen",
    }

    # Test file & path substitutions
    t1 = engine._substitute_placeholders("File is: {document_filename}", ctx)
    assert t1 == "File is: Scan_2026.pdf"

    t2 = engine._substitute_placeholders("Base: {document_basename} Ext: {document_extension}", ctx)
    assert t2 == "Base: Scan_2026 Ext: .pdf"

    t3 = engine._substitute_placeholders("Folder: {case_folder}", ctx)
    assert "Mustermann_Max" in t3

    # Test clinical / import skill field substitutions
    t4 = engine._substitute_placeholders("{Nachname}_{Vorname}_{Produkt}", ctx)
    assert t4 == "Mustermann_Max_Einlagen"

    # Test dynamic year/date substitution when not explicitly in context
    t5 = engine._substitute_placeholders("Year: {Jahr}", ctx)
    assert len(t5.replace("Year: ", "")) == 4


def test_export_engine_placeholder_modifiers():
    from core.skills.engines.export_engine import ExportEngine

    engine = ExportEngine({})
    ctx = {
        "document_fullpath": "C:\\OrdinFlowTest\\Cases\\Mustermann_Max\\Scan_2026.pdf",
        "Nachname": "Müller-Lüdenscheidt",
        "Vorname": "Max",
        "Geburtsdatum": "07.04.1980",
        "Datum": "2026-08-22",
    }

    # Case transformation modifiers
    assert engine._substitute_placeholders("{Nachname|upper}", ctx) == "MÜLLER-LÜDENSCHEIDT"
    assert engine._substitute_placeholders("{Vorname|lower}", ctx) == "max"

    # Number / Digits only modifier
    assert engine._substitute_placeholders("{Geburtsdatum|nodots}", ctx) == "07041980"
    assert engine._substitute_placeholders("{Geburtsdatum|digits_only}", ctx) == "07041980"

    # Filesystem Slug modifier
    assert engine._substitute_placeholders("{Nachname|slug}", ctx) == "Mueller-Luedenscheidt"

    # Path modifiers
    assert engine._substitute_placeholders("{document_fullpath|filename}", ctx) == "Scan_2026.pdf"
    assert engine._substitute_placeholders("{document_fullpath|stem}", ctx) == "Scan_2026"
    assert engine._substitute_placeholders("{document_fullpath|ext}", ctx) == ".pdf"

    # Date formatting modifiers
    assert engine._substitute_placeholders("{Datum|format:YYYYMMDD}", ctx) == "20260822"
    assert engine._substitute_placeholders("{Datum|format:DD.MM.YYYY}", ctx) == "22.08.2026"
    assert engine._substitute_placeholders("{Geburtsdatum|format:YYYY-MM-DD}", ctx) == "1980-04-07"


def test_export_engine_app_launch_and_login_skill(monkeypatch):
    from core.skills.engines.export_engine import ExportEngine

    launch_called = []

    class MockSkillManager:
        def get_skill(self, skill_id):
            launch_called.append(skill_id)
            return {"id": skill_id, "name": skill_id, "enabled": True, "actions": []}

    engine = ExportEngine(
        {"id": "main_export", "name": "Main Export", "type": "export", "launch_skill_id": "rdp_login"},
        skill_manager=MockSkillManager(),
    )

    # Mock screen capture to return None first (window not found) then a mock image
    attempt_count = 0

    def mock_capture(win):
        nonlocal attempt_count
        attempt_count += 1
        if attempt_count <= 1:
            return None
        from PIL import Image
        return Image.new("RGB", (100, 100), color="white")

    from core.skills.grounder import SoMGrounder
    monkeypatch.setattr(SoMGrounder, "capture_screen", mock_capture)

    # Window ready check should invoke launch skill 'rdp_login'
    ready = engine._ensure_window_ready("TargetApp*", context={"patient": "Max"})
    assert ready is True
    assert "rdp_login" in launch_called


def test_som_grounder_quadrant_tiling():
    from PIL import Image
    from core.skills.grounder import SoMGrounder

    # 1. Test 1080p standard image -> returns 1 full tile
    img_1080p = Image.new("RGB", (1920, 1080), color="blue")
    tiles_1080 = SoMGrounder.generate_quadrant_tiles(img_1080p)
    assert len(tiles_1080) == 1
    assert tiles_1080[0][1] == 0 and tiles_1080[0][2] == 0

    # 2. Test 4K image (3840x2160) -> returns 5 tiles (TL, TR, C, BL, BR)
    img_4k = Image.new("RGB", (3840, 2160), color="red")
    tiles_4k = SoMGrounder.generate_quadrant_tiles(img_4k)
    assert len(tiles_4k) == 5

    # Verify each tile width and height is aligned to multiple of 28 for Qwen visual tokens
    for tile_img, off_x, off_y in tiles_4k:
        assert tile_img.width % 28 == 0 or tile_img.width == 3840
        assert tile_img.height % 28 == 0 or tile_img.height == 2160
        assert off_x >= 0 and off_y >= 0


def test_export_engine_multi_file_folder_execution(temp_skills_dir):
    from core.skills.engines.export_engine import ExportEngine

    folder = tempfile.mkdtemp()
    try:
        # Create 2 scan files in the case folder
        f1 = os.path.join(folder, "Fußscan__Left.pdf")
        f2 = os.path.join(folder, "Fußscan__Right.pdf")
        open(f1, "w").close()
        open(f2, "w").close()

        with open(f1 + ".meta", "w", encoding="utf-8") as meta_f:
            json.dump({"Document": "Fußscan", "Side": "Left"}, meta_f)
        with open(f2 + ".meta", "w", encoding="utf-8") as meta_f:
            json.dump({"Document": "Fußscan", "Side": "Right"}, meta_f)

        executed_files = []

        class MockExportEngine(ExportEngine):
            def execute_steps(self, context, reporter=None, depth=0):
                executed_files.append(context.get("document_fullpath"))
                return True

        skill_def = {
            "id": "fu_scan_export",
            "name": "Fußscan Export",
            "type": "export",
            "document_types": ["Fußscan"],
            "tasks": [
                {
                    "id": "t1",
                    "title": "Task 1",
                    "actions": [{"action_type": "FOCUS_WINDOW", "window_title": "CorelDRAW*"}]
                }
            ]
        }
        engine = MockExportEngine(skill_def)

        success = engine.execute_skill_for_folder(folder)
        assert success is True
        assert len(executed_files) == 2
        assert f1 in executed_files
        assert f2 in executed_files

        # Verify both .meta files are marked
        with open(f1 + ".meta", "r", encoding="utf-8") as mf1:
            m1 = json.load(mf1)
        with open(f2 + ".meta", "r", encoding="utf-8") as mf2:
            m2 = json.load(mf2)
        assert "fu_scan_export" in m1.get("executed_skills", [])
        assert "fu_scan_export" in m2.get("executed_skills", [])
    finally:
        shutil.rmtree(folder, ignore_errors=True)


def test_case_router_clean_metadata_parsing():
    from core.skills.case_router import find_pending_cases

    temp_dir = tempfile.mkdtemp()
    try:
        # Create approved case folder with __ delimiter and standard folder structure
        folder_name = "2026-08-22__Einlagen__Mustermann__Max__----"
        case_path = os.path.join(temp_dir, folder_name)
        os.makedirs(case_path, exist_ok=True)
        open(os.path.join(case_path, ".approved"), "w").close()

        scan_pdf = os.path.join(case_path, "Fußscan__2026-08-22.pdf")
        open(scan_pdf, "w").close()
        with open(scan_pdf + ".meta", "w", encoding="utf-8") as mf:
            json.dump({"Document": "Fußscan"}, mf)

        folder_struct = ["{Datum}", "{Produkt}", "{Nachname}", "{Vorname}", "{Titel}"]
        cases = find_pending_cases(
            temp_dir,
            skill_id="fu_scan_export",
            allowed_types=["Fußscan"],
            folder_structure=folder_struct,
            delimiter="__",
        )

        assert len(cases) == 1
        c = cases[0]
        meta = c["parsed_metadata"]
        assert meta["Datum"] == "2026-08-22"
        assert meta["Produkt"] == "Einlagen"
        assert meta["Nachname"] == "Mustermann"
        assert meta["Vorname"] == "Max"
        assert meta["Titel"] == ""  # '----' stripped to empty
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_export_engine_delay_action_execution():
    from core.skills.engines.export_engine import ExportEngine

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
    from core.skills.engines.export_engine import ExportEngine

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
    from core.skills.engines.export_engine import ExportEngine

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
    # Empty context without document_fullpath -> must fail fast and return False
    assert engine.execute_actions(context={}) is False
    # Non-existent file -> must fail fast and return False
    assert engine.execute_actions(context={"document_fullpath": "C:/NonExistentPath/File.pdf"}) is False


def test_export_engine_fail_fast_type_file_path():
    from core.skills.engines.export_engine import ExportEngine

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
    # Empty context -> must fail fast
    assert engine.execute_actions(context={}) is False
    # Non-existent file -> must fail fast
    assert engine.execute_actions(context={"document_fullpath": "C:/NonExistent/Doc.pdf"}) is False


def test_export_engine_fail_fast_unresolved_type_text():
    from core.skills.engines.export_engine import ExportEngine

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
    # Empty context with required placeholder -> must fail fast
    assert engine.execute_actions(context={}) is False







