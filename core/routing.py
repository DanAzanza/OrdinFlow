import re
from typing import Any

from core.utils import clean_path_component, clean_template_result, is_missing_value


class SafeTemplateDict(dict):
    """Safe dict implementation for generic string templating (case-insensitive)."""

    def __init__(
        self,
        data: dict,
        fallbacks: dict[str, Any] | None = None,
        optional_fields: set | None = None,
        extraction_fields: set | None = None,
        preserve_placeholders: bool = False,
    ):
        super().__init__()
        self.optional_fields = {k.lower() for k in (optional_fields or set())}
        self.extraction_fields = {k.lower() for k in (extraction_fields or set())}
        self.fallbacks = {k.lower(): v for k, v in (fallbacks or {}).items()}
        self.preserve_placeholders = preserve_placeholders
        self._lower_map: dict[str, Any] = {}

        for k, v in data.items():
            k_low = k.lower()
            if is_missing_value(v):
                val = "" if (not self.preserve_placeholders and self._is_optional(k)) else "----"
            elif isinstance(v, str):
                val = clean_path_component(v).strip()
            else:
                val = v

            # If a valid value already exists in _lower_map, it must not be overwritten by "----" / empty
            existing = self._lower_map.get(k_low)
            if existing and not is_missing_value(existing) and is_missing_value(val):
                continue
            self._lower_map[k_low] = val

    def _is_optional(self, key: str) -> bool:
        k_low = key.lower()
        return k_low in self.optional_fields

    def __missing__(self, key: str) -> str:
        k_low = key.lower()
        if k_low in self._lower_map:
            return str(self._lower_map[k_low])
        if k_low in self.fallbacks:
            return str(self.fallbacks[k_low])
        if self.preserve_placeholders:
            return "----"
        if self._is_optional(key):
            return ""
        return "----"


def _resolve_comp(comp: Any, idx: int):
    """Returns (label, template_string) for a component from folder_structure."""
    if isinstance(comp, dict):
        tpl = comp.get("template", "")
        label = comp.get("label") or tpl.strip("{} ") or f"Column_{idx + 1}"
        return label, tpl
    elif isinstance(comp, str):
        tpl = comp
        label = comp.strip("{} ") or f"Column_{idx + 1}"
        return label, tpl
    return f"Column_{idx + 1}", ""


def render_folder_name(
    data: dict,
    routing_cfg: dict | None = None,
    optional_fields: set | None = None,
    extraction_fields: set | None = None,
    folder_structure: list | None = None,
    delimiter: str = "--",
) -> str:
    """Generically generates a folder name based on configuration and structure."""
    safe_ctx = SafeTemplateDict(
        data,
        optional_fields=optional_fields,
        extraction_fields=extraction_fields,
    )

    if folder_structure is not None:
        effective_structure = folder_structure
    elif routing_cfg and isinstance(routing_cfg, dict) and "folder_structure" in routing_cfg:
        effective_structure = routing_cfg["folder_structure"] or []
    else:
        effective_structure = []

    parts = []
    for i, comp in enumerate(effective_structure):
        _, tpl = _resolve_comp(comp, i)
        if tpl:
            match = re.fullmatch(r"\{(\w+)\}", tpl.strip())
            val = clean_template_result(tpl.format_map(safe_ctx), delimiter=delimiter)

            # If a standalone structure component is empty,
            # ensure the placeholder ---- is used (unless the field is optional)
            if match and (not val or is_missing_value(val)):
                field_name = match.group(1)
                if not safe_ctx._is_optional(field_name):
                    val = "----"
                else:
                    val = ""
            if val:
                parts.append(val)

    while len(parts) > 1 and is_missing_value(parts[-1]):
        parts.pop()

    return clean_template_result(delimiter.join(parts), delimiter=delimiter)


def render_filename(
    data: dict,
    routing_cfg: dict | None = None,
    ext: str = "",
    optional_fields: set | None = None,
    extraction_fields: set | None = None,
    fallbacks: dict[str, Any] | None = None,
) -> str:
    """Generically generates a filename based on configuration and template."""
    routing_cfg = routing_cfg or {}
    filename_template = routing_cfg.get("filename_template") or "{Document}"
    safe_ctx = SafeTemplateDict(
        data, fallbacks=fallbacks, optional_fields=optional_fields, extraction_fields=extraction_fields
    )
    delimiter = "__"
    if "--" in filename_template:
        delimiter = "--"
    elif "++" in filename_template:
        delimiter = "++"
    base = clean_template_result(filename_template.format_map(safe_ctx), delimiter=delimiter)
    return f"{base}{ext}"


def parse_folder_name(
    folder_name: str,
    folder_structure: list | None = None,
    delimiter: str = "--",
) -> dict:
    """Parses a folder name using the configured delimiter and folder structure."""
    parts = folder_name.split(delimiter)
    parsed: dict[str, Any] = {
        "display_title": folder_name,
        "parts": parts,
    }

    if folder_structure:
        for i, comp in enumerate(folder_structure):
            label, _ = _resolve_comp(comp, i)
            clean_label = label.strip("{}")
            val = parts[i] if i < len(parts) else ""
            if is_missing_value(val):
                val = ""
            parsed[clean_label] = val
            parsed[label] = val
    else:
        for i, part in enumerate(parts):
            clean_val = "" if is_missing_value(part) else part
            parsed[f"part_{i + 1}"] = clean_val

    return parsed
