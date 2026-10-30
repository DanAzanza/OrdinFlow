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


def test_all_url_map_routes_enforce_auth():
    """Iterates over every route in create_app().url_map and asserts 403 for unauthenticated requests."""
    import re
    from core.state import create_dms_service
    from dashboard import create_app

    dms = create_dms_service()
    dms.session_token = "audit-token-xyz-987"
    app = create_app(dms=dms)

    public_exempt_rules = {
        "/favicon.ico",
        "/api/health",
        "/api/heartbeat",
        "/auth/bootstrap",
        "/static/<path:filename>",
    }

    with app.test_client() as anon_client:
        checked_count = 0
        for rule in app.url_map.iter_rules():
            if rule.rule in public_exempt_rules:
                continue
            # Build concrete path by replacing route parameters (<path:x>, <x>) with "dummy"
            concrete_path = re.sub(r"<[^>]+>", "dummy", rule.rule)
            methods = [m for m in (rule.methods or set()) if m not in ("HEAD", "OPTIONS")]
            for method in methods:
                resp = anon_client.open(concrete_path, method=method, headers={"Host": "127.0.0.1:8080"})
                assert resp.status_code == 403, (
                    f"Route {method} {rule.rule} ({concrete_path}) returned {resp.status_code} instead of 403 without auth!"
                )
                checked_count += 1
        assert checked_count >= 25


def test_config_api_redacts_server_api_key_and_rejects_external_server_url(real_sec_app):
    """Verifies that server_api_key is masked on GET, preserved when masked on PUT, and server_url enforces loopback."""
    from core.config import AppConfig

    app, token = real_sec_app
    cfg = AppConfig()
    cfg.server_api_key = "sk-real-secret-key-999"
    cfg.server_url = "http://127.0.0.1:8081/v1"
    DashboardState.config = cfg

    headers = {"Host": "localhost", "X-OrdinFlow-Token": token}
    with app.test_client() as client:
        # 1. GET /api/config must mask server_api_key
        get_resp = client.get("/api/config", headers=headers)
        assert get_resp.status_code == 200
        body = get_resp.get_json()
        assert body["server_api_key"] == "********"
        assert "sk-real-secret-key-999" not in get_resp.get_data(as_text=True)

        # 2. PUT /api/config with masked "********" must preserve the underlying secret key
        put_masked = client.put("/api/config", json={"server_api_key": "********"}, headers=headers)
        assert put_masked.status_code == 200
        assert DashboardState.config.server_api_key == "sk-real-secret-key-999"

        # 3. PUT /api/config with external non-loopback server_url must fail with 400
        put_ext = client.put(
            "/api/config",
            json={"server_url": "https://attacker.example.com/v1"},
            headers=headers,
        )
        assert put_ext.status_code == 400
        assert "loopback" in put_ext.get_json()["error"].lower()

        # 4. PUT /api/config with embedded credentials in server_url must fail with 400
        put_cred = client.put(
            "/api/config",
            json={"server_url": "http://user:pass@127.0.0.1:8081/v1"},
            headers=headers,
        )
        assert put_cred.status_code == 400


def test_security_headers_and_no_store_cache_control():
    """Verifies CSP, X-Frame-Options, X-Content-Type-Options, and Cache-Control: private, no-store."""
    from core.state import create_dms_service
    from dashboard import create_app

    dms = create_dms_service()
    dms.session_token = "hdr-test-token"
    app = create_app(dms=dms)

    with app.test_client() as client:
        resp = client.get(
            "/api/health",
            headers={"Host": "127.0.0.1:8080"},
        )
        assert resp.status_code == 200
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "SAMEORIGIN"
        assert resp.headers.get("Referrer-Policy") == "no-referrer"
        assert "default-src 'self'" in (resp.headers.get("Content-Security-Policy") or "")
        assert resp.headers.get("Cache-Control") == "private, no-store"


def test_start_dashboard_aborts_before_open_browser_on_bind_failure(monkeypatch):
    """Verifies that if make_server fails to bind, open_browser is NEVER called."""
    import dashboard
    from core.config import AppConfig

    browser_called = False

    def fake_open_browser(*args, **kwargs):
        nonlocal browser_called
        browser_called = True

    def failing_make_server(*args, **kwargs):
        raise OSError("Address already in use")

    monkeypatch.setattr(dashboard, "open_browser", fake_open_browser)
    monkeypatch.setattr(dashboard, "make_server", failing_make_server)

    cfg = AppConfig()
    cfg.dashboard_port = 8080
    DashboardState.shutdown_event.clear()
    try:
        dashboard.start_dashboard(None, cfg)
        assert browser_called is False
        assert DashboardState.shutdown_event.is_set() is True
    finally:
        DashboardState.shutdown_event.clear()


def test_user_session_file_and_port_allocation(tmp_path, monkeypatch):
    """Verifies per-user session persistence, cleanup, and ephemeral port allocation."""
    import main

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    base_dir = str(tmp_path / "app_root")

    # 1. Save, load, and remove session file
    main._save_user_session(base_dir, 8123, "tok_abc_123")
    loaded = main._load_user_session(base_dir)
    assert loaded["port"] == 8123
    assert loaded["session_token"] == "tok_abc_123"
    assert isinstance(loaded["pid"], int)

    main._remove_user_session(base_dir)
    assert main._load_user_session(base_dir) == {}

    # 2. Ephemeral port allocation returns a valid unreserved port > 1024
    free_port = main.find_free_port()
    assert 1024 < free_port <= 65535


