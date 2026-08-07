"""Re-export of Pydantic schemas for backward compatibility."""

from routes.api.system_api import (
    AssignDocumentSchema,
    ConfigUpdateSchema,
    FlexibleDocumentPayload,
    FolderEditSchema,
    validate_schema,
)

__all__ = [
    "AssignDocumentSchema",
    "ConfigUpdateSchema",
    "FlexibleDocumentPayload",
    "FolderEditSchema",
    "validate_schema",
]

