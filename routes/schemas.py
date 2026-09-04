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

    Datum: str | None = None
    Produkt: str | None = None
    Person: str | None = None
    folder_name: str | None = None

    def to_clean_dict(self) -> dict[str, Any]:
        return {k: (v.strip() if isinstance(v, str) else v) for k, v in self.model_dump().items() if v is not None}


class ConfigUpdateSchema(BaseModel):
    """Schema for PUT /api/config."""

    model_config = ConfigDict(extra="ignore")

    watch_dir: str | None = None
    target_base_dir: str | None = None
    dashboard_port: int | None = None
    folder_delimiter: str | None = None
    folder_structure: list[Any] | None = None
    match_folder_by: str | None = None
    document_types: dict[str, Any] | None = None
    llm_backend: str | None = None
    server_url: str | None = None
    server_api_key: str | None = None
    llm_model_path: str | None = None
    mmproj_path: str | None = None
    n_gpu_layers: int | None = None
    n_batch: int | None = None
    n_ubatch: int | None = None
    type_k: int | None = None
    type_v: int | None = None
    max_tokens: int | None = None
    n_threads: int | None = None
    render_dpi: int | None = None
    vision_api_timeout: int | float | None = None
    vision_api_retries: int | None = None
    crop_edge_threshold: int | None = None
    min_contour_area: int | None = None
    crop_padding: int | None = None
    white_border: int | None = None
    contrast_limit: int | float | None = None
    classify_dimension: int | None = None
    tier1_dimension: int | None = None
    tier2_dimension: int | None = None
    tier3_dimension: int | None = None

    def to_clean_dict(self) -> dict[str, Any]:
        return self.model_dump(exclude_unset=True)


class CaseApprovalSchema(BaseModel):
    """Schema for POST /api/cases/approve."""

    folder: str
    approved: bool = True


class SplitInspectorSubmitSchema(BaseModel):
    """Schema for POST /api/split_inspector/submit."""

    context: str = "inbox"
    filename: str
    folder: str | None = None
    documents: list[dict[str, Any]] = Field(default_factory=list)


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
    "CaseApprovalSchema",
    "ConfigUpdateSchema",
    "FlexibleDocumentPayload",
    "FolderEditSchema",
    "SplitInspectorSubmitSchema",
    "validate_schema",
]
