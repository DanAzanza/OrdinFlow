"""Unit tests for DMSService, state resolution, and dashboard application factory."""

import threading
import time
from flask import Flask

from core.config import AppConfig
from core.state import (
    DMSService,
    DashboardState,
    create_dms_service,
    dms_service,
    get_current_dms,
    set_current_dms,
)
from dashboard import create_app


def test_create_dms_service_factory():
    """create_dms_service returns an isolated DMSService with configured attributes."""
    cfg = AppConfig()
    dummy_proc = object()
    svc = create_dms_service(config=cfg, processor=dummy_proc)

    assert isinstance(svc, DMSService)
    assert svc.config is cfg
    assert svc.processor is dummy_proc
    assert isinstance(svc._shutdown_event, threading.Event)
    assert isinstance(svc._last_heartbeat, float)
    assert svc.session_token is None


def test_get_and_set_current_dms():
    """get_current_dms falls back to process global and honors set_current_dms."""
    orig_dms = get_current_dms()
    custom_dms = create_dms_service()

    try:
        set_current_dms(custom_dms)
        assert get_current_dms() is custom_dms
    finally:
        set_current_dms(orig_dms)


def test_flask_context_dms_resolution():
    """get_current_dms resolves from current_app.extensions['dms'] inside app context."""
    custom_dms = create_dms_service()
    app = Flask(__name__)
    app.extensions["dms"] = custom_dms

    # Outside app context -> resolves global dms_service
    assert get_current_dms() is dms_service

    # Inside app context -> resolves extension instance
    with app.app_context():
        assert get_current_dms() is custom_dms

    # Back outside -> resolves global dms_service
    assert get_current_dms() is dms_service


def test_dashboard_state_meta_properties():
    """DashboardState metaclass dynamically delegates to active DMSService."""
    orig_cfg = DashboardState.config
    orig_proc = DashboardState.processor
    orig_token = DashboardState.session_token
    orig_hb = DashboardState.last_heartbeat

    try:
        cfg = AppConfig()
        DashboardState.config = cfg
        assert DashboardState.config is cfg
        assert get_current_dms().config is cfg

        dummy_proc = "mock_proc"
        DashboardState.processor = dummy_proc
        assert DashboardState.processor == "mock_proc"
        assert get_current_dms().processor == "mock_proc"

        now = time.time() + 100.0
        DashboardState.last_heartbeat = now
        assert DashboardState.last_heartbeat == now
        assert get_current_dms()._last_heartbeat == now

        DashboardState.session_token = "test_token_123"
        assert DashboardState.session_token == "test_token_123"
        assert get_current_dms().session_token == "test_token_123"

        assert isinstance(DashboardState.shutdown_event, threading.Event)
    finally:
        DashboardState.config = orig_cfg
        DashboardState.processor = orig_proc
        DashboardState.session_token = orig_token
        DashboardState.last_heartbeat = orig_hb


def test_create_app_factory():
    """create_app creates an operational Flask application with injected DMSService."""
    custom_dms = create_dms_service()
    flask_app = create_app(dms=custom_dms)

    assert flask_app.extensions["dms"] is custom_dms
    assert custom_dms.session_token is not None
    assert len(custom_dms.session_token) > 20

    # Verify blueprints are registered
    assert "api" in flask_app.blueprints
    assert "api.api_system_and_config" in flask_app.blueprints
    assert "ui" in flask_app.blueprints

    # Verify host header validation
    client = flask_app.test_client()
    resp_valid = client.get("/api/status", headers={"Host": "127.0.0.1:8080"})
    assert resp_valid.status_code in (200, 401)  # Depends on session token / auth

    resp_invalid = client.get("/api/status", headers={"Host": "evil.com"})
    assert resp_invalid.status_code == 403
