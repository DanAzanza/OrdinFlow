import json
import os
import shutil
import tempfile
import time

import pytest

from core.skills.base import BaseSkill
from core.skills.manager import SkillManager
from core.skills.models import SkillTask, TaskProgress, TaskResult, TaskStatus
from core.skills.queue import SkillQueueManager


@pytest.fixture
def temp_skills_env():
    tmp_dir = tempfile.mkdtemp()
    skills_dir = os.path.join(tmp_dir, "settings", "skills")
    os.makedirs(skills_dir, exist_ok=True)

    yield tmp_dir, skills_dir

    shutil.rmtree(tmp_dir, ignore_errors=True)


def test_queue_manager_enqueue(temp_skills_env):
    tmp_dir, skills_dir = temp_skills_env

    skill_mgr = SkillManager(skills_dir=skills_dir)
    queue_mgr = SkillQueueManager(skill_manager=skill_mgr)

    s1 = {
        "id": "import_eingang",
        "name": "Eingangs-Import",
        "type": "import",
        "enabled": True,
    }
    skill_mgr.save_skill(s1)

    item = queue_mgr.add_to_queue("import_eingang")
    assert item.skill_id == "import_eingang"
    assert item.status == TaskStatus.PENDING

    state = queue_mgr.get_queue_state()
    assert len(state["items"]) == 1


def test_load_doctypes_from_import_skill(temp_skills_env):
    tmp_dir, skills_dir = temp_skills_env
    skill_mgr = SkillManager(skills_dir=skills_dir)

    import_skill = {
        "id": "import_eingang",
        "type": "import",
        "document_types": {
            "Vertrag": {"emoji": "📜", "classification_desc": "Vertragsdokument"},
            "Lieferschein": {"emoji": "📦", "classification_desc": "Liefernachweis"},
        },
    }
    skill_mgr.save_skill(import_skill)

    loaded = skill_mgr.get_document_types_for_skill("import_eingang")
    assert "Vertrag" in loaded
    assert "Lieferschein" in loaded
    assert loaded["Vertrag"]["emoji"] == "📜"


def test_queue_manager_reorder_and_remove(temp_skills_env):
    _tmp_dir, skills_dir = temp_skills_env
    skill_mgr = SkillManager(skills_dir=skills_dir)
    queue_mgr = SkillQueueManager(skill_manager=skill_mgr)

    s1 = {"id": "skill_1", "name": "Skill 1", "type": "export"}
    s2 = {"id": "skill_2", "name": "Skill 2", "type": "export"}
    skill_mgr.save_skill(s1)
    skill_mgr.save_skill(s2)

    item1 = queue_mgr.add_to_queue("skill_1")
    item2 = queue_mgr.add_to_queue("skill_2")

    # Reorder
    queue_mgr.reorder_queue([item2.id, item1.id])
    state = queue_mgr.get_queue_state()
    assert state["items"][0]["id"] == item2.id
    assert state["items"][1]["id"] == item1.id

    # Remove
    success = queue_mgr.remove_from_queue(item1.id)
    assert success is True
    state_after = queue_mgr.get_queue_state()
    assert len(state_after["items"]) == 1
    assert state_after["items"][0]["id"] == item2.id


def test_queue_manager_execution_with_custom_engine(temp_skills_env, monkeypatch):
    _tmp_dir, skills_dir = temp_skills_env
    skill_mgr = SkillManager(skills_dir=skills_dir)
    queue_mgr = SkillQueueManager(skill_manager=skill_mgr)

    s1 = {"id": "test_s1", "name": "Test Skill", "type": "export"}
    skill_mgr.save_skill(s1)

    executed_tasks = []

    class DummyEngine(BaseSkill):
        def execute(self, task: SkillTask, reporter=None) -> TaskResult:
            executed_tasks.append(task.id)
            if reporter:
                reporter(TaskProgress(current=1, total=1, message="Done", percent=100.0))
            return TaskResult(success=True, data={"result": "ok"})

    monkeypatch.setattr(skill_mgr, "get_skill_engine", lambda skill_id, **kw: DummyEngine({"id": skill_id, "name": skill_id}))

    item = queue_mgr.add_to_queue("test_s1")
    queue_mgr.start_queue()

    # Wait for completion
    for _ in range(20):
        if not queue_mgr.is_running:
            break
        time.sleep(0.1)

    state = queue_mgr.get_queue_state()
    assert state["items"][0]["status"] == "completed"
    assert item.id in executed_tasks


def test_queue_manager_persistence_and_recovery(temp_skills_env):
    _tmp_dir, skills_dir = temp_skills_env
    skill_mgr = SkillManager(skills_dir=skills_dir)
    queue_mgr = SkillQueueManager(skill_manager=skill_mgr)

    s1 = {"id": "skill_p1", "name": "Persistent Skill 1", "type": "export"}
    s2 = {"id": "skill_p2", "name": "Persistent Skill 2", "type": "export"}
    skill_mgr.save_skill(s1)
    skill_mgr.save_skill(s2)

    item1 = queue_mgr.add_to_queue("skill_p1")
    item2 = queue_mgr.add_to_queue("skill_p2")

    # Verify queue_state.json exists on disk
    queue_file = os.path.join(skills_dir, "queue_state.json")
    assert os.path.isfile(queue_file)

    # Instantiate a brand new SkillQueueManager to simulate server/browser reload
    new_queue_mgr = SkillQueueManager(skill_manager=skill_mgr)
    new_state = new_queue_mgr.get_queue_state()
    assert len(new_state["items"]) == 2
    assert new_state["items"][0]["id"] == item1.id
    assert new_state["items"][1]["id"] == item2.id
    assert new_state["items"][0]["status"] == "pending"

    # Simulate an interrupted running state in file
    with open(queue_file, "w", encoding="utf-8") as f:
        json.dump({"items": [{"id": "q_crash", "skill_id": "skill_p1", "status": "running"}]}, f)

    reloaded_mgr = SkillQueueManager(skill_manager=skill_mgr)
    reloaded_state = reloaded_mgr.get_queue_state()
    assert len(reloaded_state["items"]) == 1
    # Interrupted running items must be reset to pending
    assert reloaded_state["items"][0]["status"] == "pending"


def test_queue_manager_pause_and_resume(temp_skills_env, monkeypatch):
    _tmp_dir, skills_dir = temp_skills_env
    skill_mgr = SkillManager(skills_dir=skills_dir)
    queue_mgr = SkillQueueManager(skill_manager=skill_mgr)

    s1 = {"id": "skill_p1", "name": "P1", "type": "export"}
    s2 = {"id": "skill_p2", "name": "P2", "type": "export"}
    skill_mgr.save_skill(s1)
    skill_mgr.save_skill(s2)

    executed_items = []

    class SlowEngine(BaseSkill):
        def execute(self, task: SkillTask, reporter=None) -> TaskResult:
            executed_items.append(task.id)
            time.sleep(0.3)
            return TaskResult(success=True)

    monkeypatch.setattr(skill_mgr, "get_skill_engine", lambda skill_id, **kw: SlowEngine({"id": skill_id, "name": skill_id}))

    item1 = queue_mgr.add_to_queue("skill_p1")
    item2 = queue_mgr.add_to_queue("skill_p2")

    # Start queue and pause immediately
    queue_mgr.start_queue()
    assert queue_mgr.is_running is True
    queue_mgr.pause_queue()
    assert queue_mgr.is_paused is True

    # Item 1 should execute, but item 2 should stay pending while paused
    time.sleep(0.5)
    state = queue_mgr.get_queue_state()
    assert item1.id in executed_items
    assert item2.id not in executed_items
    assert state["is_paused"] is True

    # Resume queue
    queue_mgr.resume_queue()
    assert queue_mgr.is_paused is False

    # Wait for item 2 to complete
    for _ in range(30):
        if not queue_mgr.is_running:
            break
        time.sleep(0.1)

    assert item2.id in executed_items
    final_state = queue_mgr.get_queue_state()
    assert final_state["items"][0]["status"] == "completed"
    assert final_state["items"][1]["status"] == "completed"


def test_queue_manager_auto_repeat(temp_skills_env):
    _tmp_dir, skills_dir = temp_skills_env
    skill_mgr = SkillManager(skills_dir=skills_dir)
    queue_mgr = SkillQueueManager(skill_manager=skill_mgr)

    res = queue_mgr.set_auto_repeat(True, interval_seconds=120)
    assert res["auto_repeat_enabled"] is True
    assert res["auto_repeat_interval_seconds"] == 120

    state = queue_mgr.get_queue_state()
    assert state["auto_repeat_enabled"] is True
    assert state["auto_repeat_interval_seconds"] == 120


def test_import_engine_live_pause_and_stop(temp_skills_env, monkeypatch):
    tmp_dir, skills_dir = temp_skills_env
    skill_mgr = SkillManager(skills_dir=skills_dir)
    queue_mgr = SkillQueueManager(skill_manager=skill_mgr)

    import core.skills.queue as q_mod

    monkeypatch.setattr(q_mod, "_SKILL_QUEUE_MANAGER", queue_mgr)

    s1 = {
        "id": "import_eingang",
        "name": "Eingangs-Import",
        "type": "import",
        "enabled": True,
    }
    skill_mgr.save_skill(s1)

    processed_files = []
    from core.config import AppConfig
    from core.processor import DocumentProcessor
    from core.skills.engines.import_engine import ImportEngine

    cfg = AppConfig(base_dir=tmp_dir)
    inbox = os.path.join(tmp_dir, "Inbox")
    os.makedirs(inbox, exist_ok=True)
    cfg.watch_dir = inbox

    # Create 5 dummy files
    for i in range(1, 6):
        fp = os.path.join(inbox, f"doc_{i}.pdf")
        with open(fp, "w") as f:
            f.write("dummy")

    proc = DocumentProcessor(cfg)

    def mock_process(fp):
        processed_files.append(fp)
        time.sleep(0.15)
        return True

    monkeypatch.setattr(proc, "process_and_route_file", mock_process)

    engine = ImportEngine(s1, processor=proc)
    monkeypatch.setattr(skill_mgr, "get_skill_engine", lambda skill_id, **kw: engine)

    queue_mgr.add_to_queue("import_eingang")
    queue_mgr.start_queue()
    time.sleep(0.05)

    # Pause after ~1 file
    queue_mgr.pause_queue()
    assert queue_mgr.is_paused is True
    time.sleep(0.3)
    count_paused = len(processed_files)
    assert count_paused <= 2

    # Verify no more files processed while paused
    time.sleep(0.3)
    assert len(processed_files) == count_paused

    # Stop queue while paused
    queue_mgr.stop_queue()
    assert queue_mgr.is_stopped is True
    time.sleep(0.3)
    # Remaining files must NOT be processed
    assert len(processed_files) < 5

