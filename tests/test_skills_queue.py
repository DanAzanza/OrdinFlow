import os
import shutil
import tempfile
import pytest

from core.config import AppConfig
from core.skills_engine import SkillManager, SkillQueueManager


@pytest.fixture
def temp_skills_env():
    temp_dir = tempfile.mkdtemp()
    skills_dir = os.path.join(temp_dir, "settings", "skills")
    docs_dir = os.path.join(temp_dir, "settings", "documents")
    os.makedirs(skills_dir, exist_ok=True)
    os.makedirs(docs_dir, exist_ok=True)

    # Create sample import and export skills
    sm = SkillManager(skills_dir=skills_dir)
    sm.save_skill({
        "id": "import_eingang",
        "name": "Inbox Folder Import",
        "type": "import",
        "watch_dir": "./Inbox",
    })
    sm.save_skill({
        "id": "sample_export",
        "name": "Sample Export",
        "type": "export",
        "target_window": "Remote Desktop*",
    })

    yield temp_dir, sm
    shutil.rmtree(temp_dir)


def test_per_skill_document_types_structure(temp_skills_env):
    temp_dir, _ = temp_skills_env
    config = AppConfig(base_dir=temp_dir)
    settings_dir = os.path.join(temp_dir, "settings")

    doc_types = {
        "Rezept": {"emoji": "📑", "classification_desc": "Arzneiverordnung"},
        "Befundbogen": {"emoji": "🔬", "classification_desc": "Laborbefund"},
    }

    # Save document types for import_eingang
    config.save_document_types_for_skill("import_eingang", doc_types, settings_dir=settings_dir)

    # Verify single skill file settings/skills/import_eingang.yaml
    skill_file = os.path.join(settings_dir, "skills", "import_eingang.yaml")
    assert os.path.exists(skill_file)

    # Load back
    loaded = config.get_document_types_for_skill("import_eingang", settings_dir=settings_dir)
    assert "Rezept" in loaded
    assert "Befundbogen" in loaded
    assert loaded["Rezept"]["emoji"] == "📑"


def test_skill_queue_manager_add_remove_reorder(temp_skills_env):
    _, sm = temp_skills_env
    qm = SkillQueueManager(sm)

    # Add 2 items
    item1 = qm.add_to_queue("import_eingang")
    item2 = qm.add_to_queue("sample_export")

    state = qm.get_queue_state()
    assert len(state["items"]) == 2
    assert state["items"][0]["skill_id"] == "import_eingang"
    assert state["items"][0]["skill_type"] == "import"
    assert state["items"][1]["skill_id"] == "sample_export"

    # Reorder
    reordered_ids = [item2["id"], item1["id"]]
    success = qm.reorder_queue(reordered_ids)
    assert success is True

    state_after = qm.get_queue_state()
    assert state_after["items"][0]["id"] == item2["id"]
    assert state_after["items"][1]["id"] == item1["id"]

    # Remove item
    removed = qm.remove_from_queue(item1["id"])
    assert removed is True
    assert len(qm.get_queue_state()["items"]) == 1
