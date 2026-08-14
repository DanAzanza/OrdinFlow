import os
import shutil
import tempfile

import pytest

from core.config import AppConfig
from core.skills_engine import SkillManager, SkillQueueManager


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
    assert item["skill_id"] == "import_eingang"
    assert item["status"] == "pending"

    state = queue_mgr.get_queue_state()
    assert len(state["items"]) == 1


def test_load_doctypes_from_import_skill(temp_skills_env):
    tmp_dir, skills_dir = temp_skills_env
    config = AppConfig(base_dir=tmp_dir)

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

    loaded = config.get_document_types_for_skill("import_eingang")
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
    queue_mgr.reorder_queue([item2["id"], item1["id"]])
    state = queue_mgr.get_queue_state()
    assert state["items"][0]["id"] == item2["id"]
    assert state["items"][1]["id"] == item1["id"]

    # Remove
    success = queue_mgr.remove_from_queue(item1["id"])
    assert success is True
    state_after = queue_mgr.get_queue_state()
    assert len(state_after["items"]) == 1
    assert state_after["items"][0]["id"] == item2["id"]


def test_queue_manager_execution_with_handlers(temp_skills_env):
    import time
    _tmp_dir, skills_dir = temp_skills_env
    skill_mgr = SkillManager(skills_dir=skills_dir)
    queue_mgr = SkillQueueManager(skill_manager=skill_mgr)

    s1 = {"id": "import_s1", "name": "Import 1", "type": "import"}
    skill_mgr.save_skill(s1)

    executed_items = []
    def dummy_import_handler(item):
        executed_items.append(item["id"])
        return True

    queue_mgr.set_handlers(import_handler=dummy_import_handler)
    item = queue_mgr.add_to_queue("import_s1")
    queue_mgr.start_queue()

    # Wait for completion
    for _ in range(20):
        if not queue_mgr.is_running:
            break
        time.sleep(0.1)

    state = queue_mgr.get_queue_state()
    assert state["items"][0]["status"] == "completed"
    assert item["id"] in executed_items

