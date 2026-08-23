"""Central Pydantic validation schemas for API endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class FlexibleDocumentPayload(BaseModel):
    """Base schema for document metadata with dynamic extra fields."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    document: str | None = Field(
        default="Document",
        alias="Document",
        description="Type or category of the document",
    )

    def to_clean_dict(self) -> dict[str, Any]:
        """Returns all parsed fields (incl. dynamic fields) as a dictionary."""
        data = self.model_dump(by_alias=False)
        cleaned: dict[str, Any] = {}
        for k, v in data.items():
            if isinstance(v, str):
                cleaned[k] = v.strip()
            else:
                cleaned[k] = v
        if "document" in cleaned:
            cleaned["Document"] = cleaned["document"]
        return cleaned


class AssignDocumentSchema(FlexibleDocumentPayload):
    """Schema for POST /api/inbox/<filename>/assign."""


class FolderEditSchema(BaseModel):
    """Schema for PUT /api/cases/<folder_name>."""

    model_config = ConfigDict(extra="allow")

    def to_clean_dict(self) -> dict[str, Any]:
        return {k: v.strip() if isinstance(v, str) else v for k, v in self.model_dump().items()}


class ConfigUpdateSchema(BaseModel):
    """Schema for PUT /api/config."""

    model_config = ConfigDict(extra="allow")

    folder_delimiter: str | None = None
    folder_structure: list[Any] | None = None
    document_types: dict[str, Any] | None = None


def validate_schema(schema_cls: Any, data: dict[str, Any] | None) -> tuple[Any | None, str | None]:
    """Helper function to safely validate JSON payloads against a Pydantic schema."""
    if data is None:
        return None, "No input data received (JSON expected)."
    if not isinstance(data, dict):
        return None, "Invalid data format (dictionary expected)."
    try:
        instance = schema_cls.model_validate(data)
        return instance, None
    except ValidationError as e:
        errors = []
        for err in e.errors():
            loc = " -> ".join(str(item) for item in err.get("loc", []))
            msg = err.get("msg", "")
            errors.append(f"{loc}: {msg}")
        return None, "; ".join(errors)


__all__ = [
    "AssignDocumentSchema",
    "ConfigUpdateSchema",
    "FlexibleDocumentPayload",
    "FolderEditSchema",
    "validate_schema",
]
