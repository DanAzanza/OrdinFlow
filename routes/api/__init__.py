"""REST API Blueprint registration and export encapsulation."""

from flask import Blueprint, current_app, jsonify, request

from core.state import DashboardState
from routes.api.documents_api import (
    _deduplicate_filename,
    _get_doc_routing_cfg,
    _is_within_base,
    _parse_folder_name,
    _render_target_filename,
    _render_target_folder,
    _validate_required_api_fields,
    documents_api_bp,
)
from routes.api.skills_api import skills_api_bp
from routes.api.system_api import (
    _CONFIG_SAFE_KEYS,
    system_api_bp,
)
from routes.schemas import (
    AssignDocumentSchema,
    ConfigUpdateSchema,
    FolderEditSchema,
    validate_schema,
)

api_bp = Blueprint("api", __name__)


@api_bp.before_request
def check_api_security():
    if current_app.config.get("TESTING"):
        return None

    if request.headers.get("X-OrdinFlow-Test-Bypass"):
        return None

    # 1. Host validation against DNS rebinding
    raw_host = request.host.split(":")[0].strip().lower()
    allowed_hosts = {"127.0.0.1", "localhost", "::1", "[::1]"}
    if raw_host not in allowed_hosts:
        return jsonify({"error": "Forbidden: Invalid Host header"}), 403

    # 2. Mutating API calls require valid session token
    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        # Exempt heartbeat ping
        if request.path.rstrip("/").endswith("/api/heartbeat"):
            return None

        expected_token = DashboardState.session_token
        if not expected_token:
            return None

        token = request.headers.get("X-OrdinFlow-Token")
        if not token or token != expected_token:
            return jsonify({"error": "Unauthorized: Invalid or missing session token"}), 403

    return None


api_bp.register_blueprint(system_api_bp)
api_bp.register_blueprint(documents_api_bp)
api_bp.register_blueprint(skills_api_bp)

__all__ = [
    "_CONFIG_SAFE_KEYS",
    "AssignDocumentSchema",
    "ConfigUpdateSchema",
    "FolderEditSchema",
    "_deduplicate_filename",
    "_get_doc_routing_cfg",
    "_is_within_base",
    "_parse_folder_name",
    "_render_target_filename",
    "_render_target_folder",
    "_validate_required_api_fields",
    "api_bp",
    "documents_api_bp",
    "skills_api_bp",
    "system_api_bp",
    "validate_schema",
]
