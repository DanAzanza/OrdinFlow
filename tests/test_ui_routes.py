"""Unit tests for HTML UI routes and legal documents API in routes/ui.py."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from flask import Flask

from routes.state import DashboardState
from routes.ui import ui_bp

ROOT_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture
def ui_client():
    """Provides a Flask test client configured with root templates and ui_bp."""
    app = Flask(__name__, template_folder=str(ROOT_DIR / "templates"))
    app.config["TESTING"] = True
    app.register_blueprint(ui_bp)

    DashboardState.session_token = "test-token-12345"
    DashboardState.bootstrap_token = None
    with app.test_client() as client:
        client.environ_base["HTTP_X_ORDINFLOW_TOKEN"] = "test-token-12345"
        client.environ_base["HTTP_HOST"] = "localhost"
        yield client
    DashboardState.session_token = None
    DashboardState.bootstrap_token = None


def test_index_route(ui_client):
    """Verifies that authenticated GET / renders index.html with the active session token injected."""
    res = ui_client.get("/")
    assert res.status_code == 200
    assert "text/html" in res.content_type

    html = res.get_data(as_text=True)
    assert 'content="test-token-12345"' in html
    assert "OrdinFlow" in html


def test_index_route_unauthenticated_and_bootstrap_flow():
    """Verifies that GET / rejects unauthenticated requests (403) and /auth/bootstrap sets a single-use HttpOnly cookie."""
    app = Flask(__name__, template_folder=str(ROOT_DIR / "templates"))
    app.register_blueprint(ui_bp)
    DashboardState.session_token = "secret-session-tok-999"
    nonce = DashboardState.issue_bootstrap_token()

    try:
        with app.test_client() as anon_client:
            # 1. Unauthenticated GET / MUST return 403 and NEVER leak the token
            res_unauth = anon_client.get("/", headers={"Host": "127.0.0.1:8080"})
            assert res_unauth.status_code == 403
            assert "secret-session-tok-999" not in res_unauth.get_data(as_text=True)

            # 2. Invalid bootstrap nonce returns 403 and does NOT consume the valid nonce
            res_bad_nonce = anon_client.get("/auth/bootstrap?nonce=wrong_nonce", headers={"Host": "127.0.0.1:8080"})
            assert res_bad_nonce.status_code == 403

            # 3. Valid bootstrap nonce redirects to / and sets HttpOnly SameSite=Strict cookie
            res_boot = anon_client.get(f"/auth/bootstrap?nonce={nonce}", headers={"Host": "127.0.0.1:8080"})
            assert res_boot.status_code == 302
            set_cookie_hdr = res_boot.headers.get("Set-Cookie", "")
            assert "ordinflow_session=secret-session-tok-999" in set_cookie_hdr
            assert "HttpOnly" in set_cookie_hdr
            assert "SameSite=Strict" in set_cookie_hdr

            # 4. Replaying the same bootstrap nonce MUST fail (single-use)
            res_replay = anon_client.get(f"/auth/bootstrap?nonce={nonce}", headers={"Host": "127.0.0.1:8080"})
            assert res_replay.status_code == 403

            # 5. Subsequent GET / with the established session cookie succeeds
            res_authed = anon_client.get("/", headers={"Host": "127.0.0.1:8080"})
            assert res_authed.status_code == 200
            assert 'content="secret-session-tok-999"' in res_authed.get_data(as_text=True)
    finally:
        DashboardState.session_token = None
        DashboardState.bootstrap_token = None


def test_favicon_route(ui_client):
    """Verifies that GET /favicon.ico returns 204 No Content."""
    res = ui_client.get("/favicon.ico")
    assert res.status_code == 204
    assert res.get_data() == b""


def test_api_legal_valid_docs(ui_client):
    """Verifies that all registered legal documents return 200 with their content."""
    for doc_name in ["license", "thirdparty", "privacy", "checklist"]:
        res = ui_client.get(f"/api/legal/{doc_name}")
        assert res.status_code == 200
        data = res.get_json()
        assert data is not None
        assert data["status"] == "ok"
        assert len(data["content"]) > 0


def test_api_legal_invalid_doc_returns_404(ui_client):
    """Verifies that querying an unregistered legal document key returns 404."""
    res = ui_client.get("/api/legal/non_existent_doc_key")
    assert res.status_code == 404
    assert res.get_json() == {"error": "Not found"}


def test_api_legal_missing_file_on_disk_returns_404(ui_client, monkeypatch):
    """Verifies that querying a registered legal doc whose file is missing on disk returns 404."""
    orig_exists = os.path.exists

    def fake_exists(path: str) -> bool:
        if path.endswith("LICENSE"):
            return False
        return orig_exists(path)

    monkeypatch.setattr(os.path, "exists", fake_exists)

    res = ui_client.get("/api/legal/license")
    assert res.status_code == 404
    assert res.get_json() == {"error": "File not found on server"}
