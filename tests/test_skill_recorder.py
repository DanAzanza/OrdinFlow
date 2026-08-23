from core.skill_recorder import SkillRecorder


def test_skill_recorder_singleton_and_status():
    recorder = SkillRecorder.get_instance()
    assert recorder is not None
    status = recorder.get_status()
    assert "is_recording" in status
    assert status["is_recording"] is False


def test_skill_recorder_synthesis():
    recorder = SkillRecorder.get_instance()
    recorder.skill_name = "Test Workflow"
    recorder.target_window = "Test Window*"
    recorder.steps = [
        {"id": "step_1", "description": "Focus window", "action_type": "FOCUS_WINDOW", "window_title": "Test Window*"},
        {
            "id": "step_2",
            "description": "Click search",
            "action_type": "CLICK",
            "locator": {"type": "ocr_contains", "prompt": "Search"},
        },
    ]

    skill_obj = recorder._synthesize_skill()
    assert skill_obj["name"] == "Test Workflow"
    assert len(skill_obj["steps"]) == 2
    assert skill_obj["steps"][0]["action_type"] == "FOCUS_WINDOW"
    assert skill_obj["steps"][1]["action_type"] == "CLICK"


def test_recorder_api_endpoints(client):
    # Check status
    resp = client.get("/api/skills/recorder/status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "is_recording" in data

    # Stop when not recording
    resp_stop = client.post("/api/skills/recorder/stop")
    assert resp_stop.status_code == 200
    data_stop = resp_stop.get_json()
    assert data_stop.get("status") == "stopped"


def test_skill_recorder_event_handling():
    recorder = SkillRecorder()
    recorder.is_recording = True
    recorder.steps = []
    recorder.last_click_time = 0.0
    recorder.last_click_coords = (0, 0)
    recorder._keyboard_buffer = []
    recorder._active_modifiers = set()
    recorder._active_hotkey_keys = set()

    # 1. Simulate normal keypresses
    class DummyKey:
        char = "a"

    recorder._on_key_press(DummyKey())
    assert recorder._keyboard_buffer == ["a"]

    # 2. Simulate mouse click (left button)
    from core.skill_recorder import mouse

    btn = mouse.Button.left if mouse else "left"
    recorder._on_mouse_click(100, 200, btn, True)

    # Should have flushed keyboard buffer and added click step
    assert len(recorder.steps) >= 2
    types = [s["action_type"] for s in recorder.steps]
    assert "TYPE_TEXT" in types
    assert "CLICK" in types


def test_skill_recorder_hotkey_recording_and_modifiers():
    recorder = SkillRecorder()
    recorder.is_recording = True
    recorder.steps = []
    recorder._keyboard_buffer = []
    recorder._active_modifiers = set()
    recorder._active_hotkey_keys = set()

    from core.skill_recorder import keyboard

    # 1. Press Ctrl modifier
    ctrl_key = getattr(keyboard.Key, "ctrl_l", keyboard.Key.ctrl) if keyboard else "ctrl_l"
    recorder._on_key_press(ctrl_key)
    assert "ctrl" in recorder._active_modifiers

    # 2. Press 's' while Ctrl is active (Windows sends \x13 control character)
    class CtrlSKey:
        char = "\x13"

    recorder._on_key_press(CtrlSKey())

    # Should generate HOTKEY action with keys ["ctrl", "s"]
    assert len(recorder.steps) == 1
    hotkey_step = recorder.steps[0]
    assert hotkey_step["action_type"] == "HOTKEY"
    assert "ctrl" in hotkey_step["keys"]
    assert "s" in hotkey_step["keys"]

    # 3. Test debounce: repeated press of 's' while held down is ignored
    recorder._on_key_press(CtrlSKey())
    assert len(recorder.steps) == 1

    # 4. Release 's' and release Ctrl
    recorder._on_key_release(CtrlSKey())
    assert "s" not in recorder._active_hotkey_keys
    recorder._on_key_release(ctrl_key)
    assert "ctrl" not in recorder._active_modifiers

    # 5. Test AltGr special character (e.g. '@' on German keyboard)
    # AltGr fires Ctrl+Alt modifiers internally in Win32
    alt_key = getattr(keyboard.Key, "alt_r", keyboard.Key.alt) if keyboard else "alt_r"
    recorder._on_key_press(ctrl_key)
    recorder._on_key_press(alt_key)
    assert "ctrl" in recorder._active_modifiers
    assert "alt" in recorder._active_modifiers

    class AtKey:
        char = "@"

    # Typing '@' with AltGr should be treated as text input into buffer, NOT a hotkey!
    recorder._on_key_press(AtKey())
    assert "@" in recorder._keyboard_buffer
    assert len(recorder.steps) == 1  # No extra hotkey step added

    recorder._on_key_release(ctrl_key)
    recorder._on_key_release(alt_key)


def test_skill_synthesizer_heuristics():
    from core.skills.synthesizer import SkillSynthesizer

    raw_steps = [
        {"action_type": "FOCUS_WINDOW", "window_title": "CAD Program*"},
        {"action_type": "CLICK", "description": "Menü Datei"},
        {"action_type": "HOTKEY", "description": "HotKey Ctrl+O", "keys": ["ctrl", "o"]},
        {"action_type": "TYPE_TEXT", "text": "C:\\Cases\\Mueller\\Fußscan.pdf"},
        {"action_type": "WAIT_FOR_ELEMENT", "locator": {"type": "ocr_exact", "prompt": "OK"}, "timeout_s": 12.0},
        {"action_type": "CLICK", "description": "Speichern"},
    ]

    synthesis = SkillSynthesizer.synthesize(
        raw_steps=raw_steps,
        user_instruction="Exportiere Fußscan als CDR",
        existing_doc_types=["Fußscan", "Rezept"],
    )

    assert "tasks" in synthesis
    assert len(synthesis["tasks"]) > 0
    assert "Fußscan" in synthesis["suggested_document_types"]

    # Check all synthesized actions
    all_actions = []
    for t in synthesis["tasks"]:
        all_actions.extend(t.get("actions", []))

    # Verify TYPE_FILE_PATH variable substitution
    filepath_actions = [a for a in all_actions if a.get("action_type") == "TYPE_FILE_PATH"]
    assert len(filepath_actions) >= 1
    assert filepath_actions[0]["file_path"] == "{document_fullpath}"

    # Verify HOTKEY preserves keys attribute
    hotkey_actions = [a for a in all_actions if a.get("action_type") == "HOTKEY"]
    assert len(hotkey_actions) == 1
    assert hotkey_actions[0]["keys"] == ["ctrl", "o"]

    # Verify WAIT_FOR_ELEMENT preserves locator and timeout
    wait_actions = [a for a in all_actions if a.get("action_type") == "WAIT_FOR_ELEMENT"]
    assert len(wait_actions) == 1
    assert wait_actions[0]["locator"]["prompt"] == "OK"
    assert wait_actions[0]["locator"]["type"] == "ocr_exact"
    assert wait_actions[0]["timeout_s"] == 12.0


def test_synthesize_api_endpoint(client):
    payload = {
        "steps": [
            {"action_type": "FOCUS_WINDOW", "window_title": "Sanivision*"},
            {"action_type": "CLICK", "description": "Import"},
        ],
        "user_instruction": "Workflow für Rezepte",
    }
    resp = client.post("/api/skills/synthesize", json=payload)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data.get("status") == "ok"
    assert "synthesis" in data
    assert "tasks" in data["synthesis"]


def test_ai_modify_and_yaml_api_endpoints(client):
    skill = {
        "id": "test_yaml_skill",
        "name": "Test YAML Skill",
        "type": "export",
        "tasks": [
            {
                "id": "task_1",
                "title": "Task 1",
                "actions": [
                    {"id": "act_1", "action_type": "FOCUS_WINDOW", "window_title": "Sanivision*"}
                ],
            }
        ],
    }

    # 1. Test to_yaml
    res_to_yaml = client.post("/api/skills/to_yaml", json={"skill": skill})
    assert res_to_yaml.status_code == 200
    yaml_str = res_to_yaml.get_json()["yaml"]
    assert "name: Test YAML Skill" in yaml_str

    # 2. Test from_yaml
    res_from_yaml = client.post("/api/skills/from_yaml", json={"yaml": yaml_str})
    assert res_from_yaml.status_code == 200
    parsed = res_from_yaml.get_json()["skill"]
    assert parsed["id"] == "test_yaml_skill"

    # 3. Test ai_modify
    res_mod = client.post("/api/skills/ai_modify", json={
        "skill": skill,
        "instruction": "Füge am Ende einen Klick auf Speichern ein"
    })
    assert res_mod.status_code == 200
    mod_skill = res_mod.get_json()["skill"]
    assert "tasks" in mod_skill
    actions = mod_skill["tasks"][0]["actions"]
    assert any(a.get("action_type") == "CLICK" for a in actions)

    # 4. Save and GET/POST skill yaml
    client.post("/api/skills", json=skill)
    res_get_yaml = client.get("/api/skills/Test YAML Skill/yaml")
    assert res_get_yaml.status_code == 200
    assert "name: Test YAML Skill" in res_get_yaml.get_json()["yaml"]

    res_put_yaml = client.post("/api/skills/Test YAML Skill/yaml", json={"yaml": yaml_str})
    assert res_put_yaml.status_code == 200

    # 5. Test validation rejection for forbidden character
    res_invalid = client.post("/api/skills", json={"name": "Invalid:Skill:Name"})
    assert res_invalid.status_code == 400
    assert "forbidden" in res_invalid.get_json()["error"]

    # 6. Test rename via API
    res_rename = client.post("/api/skills", json={
        "name": "Renamed YAML Skill",
        "original_name": "Test YAML Skill",
        "type": "export"
    })
    assert res_rename.status_code == 200
    assert res_rename.get_json()["name"] == "Renamed YAML Skill"

    # Clean up
    client.delete("/api/skills/Renamed YAML Skill")
    client.delete("/api/skills/Test YAML Skill")



