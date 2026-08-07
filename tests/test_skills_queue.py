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
