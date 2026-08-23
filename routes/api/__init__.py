"""REST API Blueprint registration and export encapsulation."""

from flask import Blueprint

from routes.api.documents_api import (
    _deduplicate_filename,
    _get_doc_routing_cfg,
    _get_doc_types_from_files,
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
    "_get_doc_types_from_files",
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
