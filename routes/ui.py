import os
import secrets

from flask import Blueprint, jsonify, redirect, render_template, request

from routes.state import DashboardState

ui_bp = Blueprint("ui", __name__)

_ALLOWED_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}


@ui_bp.before_request
def check_ui_security():
    raw_host = request.host.split(":")[0].strip().lower()
    if raw_host not in _ALLOWED_HOSTS:
        return jsonify({"error": "Forbidden: Invalid Host header"}), 403

    path = request.path.rstrip("/") or "/"
    if path in ("/favicon.ico", "/auth/bootstrap"):
        return None

    expected_token = DashboardState.session_token
    if not expected_token or not isinstance(expected_token, str):
        return jsonify({"error": "Unauthorized: Session token not initialized"}), 403

    token = request.headers.get("X-OrdinFlow-Token") or request.cookies.get("ordinflow_session")
    if not token or not isinstance(token, str) or not secrets.compare_digest(token, expected_token):
        return (
            jsonify(
                {
                    "error": "Unauthorized: Invalid or missing session credentials. Launch OrdinFlow via Start_OrdinFlow to establish a session."
                }
            ),
            403,
        )
    return None


@ui_bp.route("/auth/bootstrap")
def auth_bootstrap():
    nonce = request.args.get("nonce", "")
    expected_token = DashboardState.session_token
    if not expected_token or not DashboardState.consume_bootstrap_token(nonce):
        return jsonify({"error": "Forbidden: Invalid or expired bootstrap nonce"}), 403

    resp = redirect("/")
    resp.set_cookie(
        "ordinflow_session",
        expected_token,
        httponly=True,
        samesite="Strict",
        path="/",
    )
    return resp


@ui_bp.route("/")
def index():
    app_version = getattr(DashboardState.config, "app_version", "0.9.0") if DashboardState.config else "0.9.0"
    return render_template(
        "index.html",
        session_token=DashboardState.session_token,
        app_version=app_version,
    )


@ui_bp.route("/favicon.ico")
def favicon():
    return "", 204


#  STATUS & PROCESS CONTROL


@ui_bp.route("/api/legal/<doc_name>")
def api_legal(doc_name: str):
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    valid = {
        "license": os.path.join(root_dir, "LICENSE"),
        "thirdparty": os.path.join(root_dir, "THIRD_PARTY_LICENSES.md"),
        "privacy": os.path.join(root_dir, "docs", "legal", "PRIVACY_POLICY.md"),
        "checklist": os.path.join(root_dir, "docs", "legal", "COMPLIANCE_CHECKLIST.md"),
    }
    if doc_name not in valid:
        return jsonify({"error": "Not found"}), 404

    path = valid[doc_name]
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return jsonify({"status": "ok", "content": f.read()})
    return jsonify({"error": "File not found on server"}), 404

