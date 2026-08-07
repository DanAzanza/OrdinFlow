import sys
from pathlib import Path

# Ensure project root is in sys.path for cross-platform imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from flask import Flask

from core.config import AppConfig
from routes.api import api_bp
from routes.state import DashboardState


@pytest.fixture
def app():
    """Erstellt eine isolierte Flask-App mit registriertem API Blueprint."""
    app = Flask(__name__)
    app.register_blueprint(api_bp)

    # Setup mock config (alle Tests nutzen dasselbe Config-Objekt)
    config = AppConfig()
    config.load_from_yaml()
    DashboardState.config = config
    return app


@pytest.fixture
def client(app):
    """Flask Test Client für API-Tests."""
    return app.test_client()


@pytest.fixture
def processor():
    """DocumentProcessor mit Standard-Konfiguration."""
    from core.processor import DocumentProcessor

    config = AppConfig()
    config.load_from_yaml()
    return DocumentProcessor(config)
