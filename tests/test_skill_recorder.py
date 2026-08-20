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

    # 1. Simulate keypresses
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


def test_skill_synthesizer_heuristics():
    from core.skills.synthesizer import SkillSynthesizer

    raw_steps = [
        {"action_type": "FOCUS_WINDOW", "window_title": "CAD Program*"},
        {"action_type": "CLICK", "description": "Menü Datei"},
        {"action_type": "TYPE_TEXT", "text": "C:\\Cases\\Mueller\\Fußscan.pdf"},
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
    # Check that file path was converted to {document_fullpath}
    all_actions = []
    for t in synthesis["tasks"]:
        all_actions.extend(t.get("actions", []))

    filepath_actions = [a for a in all_actions if a.get("action_type") == "TYPE_FILE_PATH"]
    assert len(filepath_actions) >= 1
    assert filepath_actions[0]["file_path"] == "{document_fullpath}"


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

