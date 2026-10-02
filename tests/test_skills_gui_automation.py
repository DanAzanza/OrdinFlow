"""Unit tests for GUI automation, UI locators, screen verification, and element waiting in RPA skills."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from PIL import Image

from core.skills.action_executor import execute_mouse_click
from core.skills.engines.export_engine import ExportEngine
from core.skills.grounder import SoMGrounder
from core.skills.manager import SkillManager
from core.skills.text_helpers import paste_text_via_clipboard, substitute_placeholders


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


def test_export_engine_clipboard_paste(monkeypatch):
    typed: list[str] = []
    monkeypatch.setattr("core.skills.text_helpers.type_unicode_text", lambda t, press_enter=False: typed.append(t))

    # 1. Non-win32 fallback branch
    monkeypatch.setattr("core.skills.text_helpers.sys.platform", "linux")
    res_linux = paste_text_via_clipboard("C:\\Test\\Output.pdf", press_enter=False)
    assert res_linux is True
    assert typed == ["C:\\Test\\Output.pdf"]

    # 2. Win32 isolated branch with mocked API calls (no keystroke injection / no clipboard locking)
    mock_user32 = MagicMock()
    mock_kernel32 = MagicMock()
    mock_windll = MagicMock(user32=mock_user32, kernel32=mock_kernel32)

    monkeypatch.setattr("core.skills.text_helpers.sys.platform", "win32")
    monkeypatch.setattr("core.skills.text_helpers._open_clipboard_with_retry", lambda u: True)
    monkeypatch.setattr("core.skills.text_helpers._get_clipboard_unicode", lambda u, k: None)
    monkeypatch.setattr("core.skills.text_helpers._set_clipboard_unicode", lambda u, k, t: True)
    monkeypatch.setattr("core.skills.text_helpers.ctypes.windll", mock_windll, raising=False)
    monkeypatch.setattr("time.sleep", lambda s: None)

    res_win = paste_text_via_clipboard("C:\\Test\\Output.pdf", press_enter=False)
    assert res_win is True
    assert mock_user32.keybd_event.called


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
                        "timeout_s": 0.02,
                        "poll_interval_s": 0.01,
                        "on_failure": "continue",
                    }
                ],
            }
        ],
    }
    engine = ExportEngine(skill_def)
    assert len(engine.actions) == 1
    assert engine.actions[0]["action_type"] == "WAIT_FOR_ELEMENT"

    # Completely isolate boundary calls to eliminate un-mocked GDI BitBlt and ONNX RapidOCR executions
    with (
        patch("core.skills.grounder.SoMGrounder.locate_target", return_value=None),
        patch("core.skills.engines.export_engine._handle_known_dialog_popups_fn", return_value=False),
        patch("core.skills.action_executor.handle_known_dialog_popups", return_value=False),
        patch("core.skills.grounder.SoMGrounder.capture_screen", return_value=None),
    ):
        success = engine.execute_actions(context={})
        assert success is True


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
        return Image.new("RGB", (100, 100), color="white")

    monkeypatch.setattr(SoMGrounder, "capture_screen", mock_capture)

    ready = engine._ensure_window_ready("TargetApp*", context={"patient": "Max"})
    assert ready is True
    assert "rdp_login" in launch_called


def test_som_grounder_quadrant_tiling():
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
    with (
        patch("core.skills.uia_locator.UIALocator.is_available", return_value=True),
        patch("core.skills.uia_locator.UIALocator.get_element_text", return_value="P-98765"),
    ):
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


def test_mouse_click_uia_fast_path(monkeypatch):
    click_coords: list[tuple[int, int]] = []
    monkeypatch.setattr(
        "core.skills.uia_locator.UIALocator.is_available",
        lambda: True,
    )
    monkeypatch.setattr(
        "core.skills.uia_locator.UIALocator.find_element",
        lambda locator, window_title=None, timeout_s=0.5: {"center": (350, 450)},
    )
    monkeypatch.setattr(
        "core.skills.action_executor.send_native_click",
        lambda x, y, button="left", double=False: click_coords.append((x, y)) or True,
    )

    step = {
        "id": "uia_btn_click",
        "action_type": "CLICK",
        "locator": {"automation_id": "btn_confirm", "control_type": "Button"},
    }

    ok = execute_mouse_click(
        step=step,
        step_id="uia_btn_click",
        action_type="CLICK",
        context={},
        target_window="TestApp",
        substitute_fn=substitute_placeholders,
        locate_fn=lambda loc, win: None,
        wait_for_queue_fn=lambda: True,
        sleep_fn=lambda s: True,
    )
    assert ok is True
    assert click_coords == [(350, 450)]
