"""Real security layer tests for OrdinFlow REST API without TESTING bypass.

Verifies:
- Host header validation against DNS rebinding
- Fail-closed token authentication on API endpoints
- Header (X-OrdinFlow-Token) authentication
- Query parameter (?token=...) authentication for iframe previews
- Timing-safe secrets.compare_digest verification
"""

from __future__ import annotations

import pytest
from flask import Flask

from core.state import DashboardState
from routes.api import api_bp


@pytest.fixture
def real_sec_app():
    """Flask application configured with active security (TESTING=False)."""
    app = Flask(__name__)
    app.config["TESTING"] = False
    app.register_blueprint(api_bp)
    token = "test_secret_token_12345"
    DashboardState.session_token = token
    yield app, token
    DashboardState.session_token = None


def test_invalid_host_header_returns_403(real_sec_app):
    app, token = real_sec_app
    with app.test_client() as client:
        # Request with malicious / rebinding host header
        resp = client.get(
            "/api/status",
            headers={"Host": "attacker.com"},
        )
        assert resp.status_code == 403
        data = resp.get_json()
        assert "Invalid Host" in data["error"]


def test_public_heartbeat_allows_unauthenticated(real_sec_app):
    app, _ = real_sec_app
    with app.test_client() as client:
        resp = client.post("/api/heartbeat", headers={"Host": "localhost"})
        # Heartbeat endpoint should succeed without token
        assert resp.status_code == 200


def test_missing_token_returns_403_unauthorized(real_sec_app):
    app, _ = real_sec_app
    with app.test_client() as client:
        # Protected endpoint without token
        resp = client.get("/api/config", headers={"Host": "127.0.0.1"})
        assert resp.status_code == 403
        data = resp.get_json()
        assert "Unauthorized" in data["error"]


def test_invalid_token_returns_403(real_sec_app):
    app, _ = real_sec_app
    with app.test_client() as client:
        resp = client.get(
            "/api/config",
            headers={"Host": "127.0.0.1", "X-OrdinFlow-Token": "wrong_token"},
        )
        assert resp.status_code == 403


def test_valid_header_token_succeeds(real_sec_app):
    app, token = real_sec_app
    with app.test_client() as client:
        resp = client.get(
            "/api/config",
            headers={"Host": "127.0.0.1", "X-OrdinFlow-Token": token},
        )
        assert resp.status_code == 200


def test_valid_query_param_token_succeeds_for_iframes(real_sec_app):
    """Iframes cannot set custom headers; query parameter token MUST authenticate properly."""
    app, token = real_sec_app
    with app.test_client() as client:
        resp = client.get(
            f"/api/config?token={token}",
            headers={"Host": "localhost"},
        )
        assert resp.status_code == 200


def test_uninitialized_session_token_fails_closed(real_sec_app):
    app, _ = real_sec_app
    # Simulate uninitialized token
    DashboardState.session_token = None
    with app.test_client() as client:
        resp = client.get(
            "/api/config?token=any_token",
            headers={"Host": "localhost"},
        )
        assert resp.status_code == 403
        data = resp.get_json()
        assert "not initialized" in data["error"]


def test_file_endpoints_authenticate_with_query_token(real_sec_app, tmp_path):
    """File serving endpoints allow iframe preview access via query token under active security."""
    app, token = real_sec_app
    dummy_file = tmp_path / "test.txt"
    dummy_file.write_text("secure file content", encoding="utf-8")

    from core.config import AppConfig

    cfg = AppConfig()
    cfg.watch_dir = str(tmp_path)
    DashboardState.config = cfg

    with app.test_client() as client:
        # Without token -> 403
        res_no_tok = client.get("/api/file/inbox/test.txt", headers={"Host": "localhost"})
        assert res_no_tok.status_code == 403

        # With query token -> 200
        res_with_tok = client.get(f"/api/file/inbox/test.txt?token={token}", headers={"Host": "localhost"})
        assert res_with_tok.status_code == 200
        assert res_with_tok.get_data(as_text=True) == "secure file content"
