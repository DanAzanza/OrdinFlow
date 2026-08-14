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
        {"id": "step_2", "description": "Click search", "action_type": "CLICK", "locator": {"type": "ocr_contains", "prompt": "Search"}}
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
