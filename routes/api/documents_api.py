"""Document API routes aggregator for DMS backend.

Combines modularized sub-blueprints:
- inbox_api_bp (inbox listing, review, assignment, previews)
- cases_api_bp (cases listing, detail, file/folder edits, deletions)
- split_api_bp (split inspector submitting and multi-page routing)
- document_helpers (path checks, thumbnail cache, folder/file renderers)
"""

from flask import Blueprint

from routes.api.cases_api import cases_api_bp
from routes.api.document_helpers import (
    _MIME_MAP,
    ThumbnailCache,
    _deduplicate_filename,
    _generate_pdf_thumbnail,
    _get_config_delimiter,
    _get_config_folder_structure,
    _get_doc_optional_fields,
    _get_doc_routing_cfg,
    _get_doc_types_from_files,
    _is_within_base,
    _parse_folder_name,
    _remove_meta_sidecar,
    _render_target_filename,
    _render_target_folder,
    _resolve_and_guard,
    _thumbnail_cache,
    _validate_required_api_fields,
    safe_move_with_meta,
)
from routes.api.inbox_api import inbox_api_bp
from routes.api.split_api import (
    _is_split_enabled_for_import_skill,
    _parse_pages_input,
    split_api_bp,
)

documents_api_bp = Blueprint("api_documents", __name__)
documents_api_bp.register_blueprint(inbox_api_bp)
documents_api_bp.register_blueprint(cases_api_bp)
documents_api_bp.register_blueprint(split_api_bp)

__all__ = [
    "documents_api_bp",
    "inbox_api_bp",
    "cases_api_bp",
    "split_api_bp",
    "_MIME_MAP",
    "ThumbnailCache",
    "_thumbnail_cache",
    "_is_within_base",
    "_remove_meta_sidecar",
    "safe_move_with_meta",
    "_get_config_folder_structure",
    "_get_config_delimiter",
    "_deduplicate_filename",
    "_get_doc_routing_cfg",
    "_resolve_and_guard",
    "_get_doc_optional_fields",
    "_render_target_folder",
    "_render_target_filename",
    "_validate_required_api_fields",
    "_parse_folder_name",
    "_get_doc_types_from_files",
    "_generate_pdf_thumbnail",
    "_parse_pages_input",
    "_is_split_enabled_for_import_skill",
]
