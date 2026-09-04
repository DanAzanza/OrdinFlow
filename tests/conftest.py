import os
import shutil
import sys
import tempfile
from pathlib import Path

# Ensure project root is in sys.path for cross-platform imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from flask import Flask

import core.skills.queue as queue_mod
from core.config import AppConfig
from core.skills.manager import SkillManager
from core.skills.queue import get_skill_queue_manager
from routes.api import api_bp
import routes.api.cases_api as cases_api_mod
import routes.api.skills_api as skills_api_mod
from routes.state import DashboardState


@pytest.fixture
def test_sandbox():
    """Provides a completely isolated sandbox filesystem for tests."""
    tmp_dir = tempfile.mkdtemp(prefix="ordinflow_test_")
    settings_dir = os.path.join(tmp_dir, "settings")
    skills_dir = os.path.join(settings_dir, "skills")
    inbox_dir = os.path.join(tmp_dir, "Inbox")
    cases_dir = os.path.join(tmp_dir, "Cases")

    os.makedirs(skills_dir, exist_ok=True)
    os.makedirs(inbox_dir, exist_ok=True)
    os.makedirs(cases_dir, exist_ok=True)

    config = AppConfig(base_dir=tmp_dir)
    config.watch_dir = inbox_dir
    config.target_base_dir = cases_dir
    config.folder_structure = ["{Datum}", "{Produkt}", "{Person}"]
    config.folder_delimiter = "__"
    config.document_types = {
        "Rezept": {"emoji": "💊", "routing": {"archive": True, "filename_template": "{Dokument}__{Person}__{Datum}"}},
        "Befund": {"emoji": "📋", "routing": {"archive": True, "filename_template": "{Dokument}__{Person}__{Datum}"}},
    }
    config.save_to_yaml()

    skill_mgr = SkillManager(skills_dir=skills_dir)
    default_import = {
        "id": "import_eingang",
        "name": "Inbox Folder Import",
        "type": "import",
        "enabled": True,
        "document_types": config.document_types,
    }
    skill_mgr.save_skill(default_import)

    # Wire up isolated singleton state
    DashboardState.config = config
    skills_api_mod._SKILL_MANAGER = skill_mgr
    cases_api_mod._SKILL_MANAGER = skill_mgr
    queue_mod._SKILL_QUEUE_MANAGER = get_skill_queue_manager(skill_mgr)

    yield tmp_dir, config, skill_mgr

    # Teardown
    if queue_mod._SKILL_QUEUE_MANAGER is not None:
        queue_mod._SKILL_QUEUE_MANAGER.stop_queue()
        queue_mod._SKILL_QUEUE_MANAGER = None

    skills_api_mod._SKILL_MANAGER = None
    cases_api_mod._SKILL_MANAGER = None
    DashboardState.config = None
    DashboardState.processor = None

    shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.fixture
def app(test_sandbox):
    """Creates an isolated Flask test application with registered API Blueprint and sandbox configuration."""
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(api_bp)
    return app


@pytest.fixture
def client(app):
    """Flask test client fixture for API tests."""
    return app.test_client()


@pytest.fixture
def processor(test_sandbox):
    """DocumentProcessor fixture configured with isolated sandbox environment."""
    from core.processor import DocumentProcessor

    _, config, _ = test_sandbox
    return DocumentProcessor(config)


@pytest.fixture
def create_test_pdf():
    """Factory fixture to create real/minimal valid multi-page PDF files."""

    def _creator(filepath: str, num_pages: int = 1, text: str = "Test Page") -> str:
        import fitz

        doc = fitz.open()
        for i in range(num_pages):
            page = doc.new_page(width=595, height=842)
            page.insert_text((50, 50), f"{text} (Page {i + 1})")
        doc.save(filepath)
        doc.close()
        return filepath

    return _creator


@pytest.fixture
def create_test_image():
    """Factory fixture to create test PIL images."""

    def _creator(filepath: str, width: int = 800, height: int = 600, color: str = "white") -> str:
        from PIL import Image

        img = Image.new("RGB", (width, height), color=color)
        img.save(filepath)
        return filepath

    return _creator
