import json
import logging
import re
import time
from typing import Any

from core.config import AppConfig
from core.llm_backends import LLMBackend, get_backend
from core.utils import (
    MISSING_PLACEHOLDER,
    clean_extracted_value,
    is_missing_value,
)

logger = logging.getLogger(__name__)


def _repair_and_parse_json(raw_text: str) -> dict[str, Any]:
    """Robustly parses or repairs malformed/truncated JSON from LLM outputs."""
    if not raw_text or not isinstance(raw_text, str):
        return {}

    text = raw_text.strip()

    if "```" in text:
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text, flags=re.MULTILINE)
        text = re.sub(r"\n?```$", "", text, flags=re.MULTILINE)
        text = text.strip()

    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1:
        if last_brace > first_brace:
            candidate = text[first_brace : last_brace + 1]
        else:
            candidate = text[first_brace:]
    else:
        candidate = text

    try:
        data = json.loads(candidate)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    repaired = candidate.strip()
    if repaired.count('"') % 2 != 0:
        repaired += '"'
    open_braces = repaired.count("{")
    close_braces = repaired.count("}")
    if open_braces > close_braces:
        repaired += "}" * (open_braces - close_braces)

    try:
        data = json.loads(repaired)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    harvested = {}
    pattern = re.compile(
        r'"([^"]+)":\s*(?:"([^"\\]*(?:\\.[^"\\]*)*)"|(true|false|null|\d+(?:\.\d+)?))',
        re.IGNORECASE,
    )
    for match in pattern.finditer(candidate):
        key = match.group(1)
        val_str = match.group(2)
        val_primitive = match.group(3)

        if val_primitive is not None:
            v_lower = val_primitive.lower()
            if v_lower == "true":
                harvested[key] = True
            elif v_lower == "false":
                harvested[key] = False
            elif v_lower == "null":
                harvested[key] = None
            else:
                try:
                    harvested[key] = float(val_primitive) if "." in val_primitive else int(val_primitive)
                except ValueError:
                    harvested[key] = val_primitive
        elif val_str is not None:
            harvested[key] = val_str

    return harvested


class LLMExtractor:
    """Encapsulates communication with the LLM backend (direct llama.cpp or server + Instructor/Pydantic).

    Selects backend via config.llm_backend:
      - "llama_cpp" : direct Llama() API, no separate server required
      - "server"    : OpenAI-compatible API via llama-server with structured Pydantic models (Instructor)
    """

    def __init__(self, config: AppConfig):
        self.config = config
        self._backend: LLMBackend = get_backend(config)  # Backend is lazily initialized
        self._doc_types_cache: dict | None = None

    def preload(self) -> None:
        """Preloads LLM backend weights into memory ahead of time."""
        try:
            self._backend.preload()
        except Exception as e:
            logger.warning("[!] Backend preload error: %s", e)

    def unload_backend(self) -> None:
        """Unloads LLM backend weights from memory."""
        try:
            self._backend.unload()
        except Exception as e:
            logger.warning("[!] Backend unload error: %s", e)

    def invalidate_cache(self) -> None:
        """Clears the document types cache after a configuration change."""
        self._doc_types_cache = None

    def _get_effective_document_types(self) -> dict:
        if getattr(self, "_doc_types_cache", None) is not None:
            return self._doc_types_cache  # type: ignore[return-value]
        doc_types = getattr(self.config, "document_types", None) or {}
        doc_types = {k: dict(v) for k, v in doc_types.items()}
        for matched_type, matched_info in doc_types.items():
            matched_info.setdefault("extraction_fields", {})
            matched_info.setdefault("validation", {"signature_required": False})
            routing = matched_info.setdefault(
                "routing",
                {
                    "archive": True,
                    "folder_template": "",
                    "filename_template": matched_type,
                },
            )
            routing.setdefault("folder_template", "")
            routing.setdefault("filename_template", matched_type)
        self._doc_types_cache = doc_types
        return doc_types

    def call_vision_api(self, payload: dict[str, Any]) -> str:
        """Calls the configured LLM backend (direct or OpenAI-compatible)."""
        # Ensure model is loaded
        try:
            self._backend._ensure_loaded()  # type: ignore[attr-defined]
        except RuntimeError as _e:
            logger.error(str(_e))
            raise
        retries = getattr(self.config, "vision_api_retries", 3)
        last_error = ""
        for attempt in range(retries):
            try:
                result = self._backend.call_vision_api(payload)  # type: ignore[attr-defined]
                if isinstance(result, str) and len(result.strip()) > 0:
                    return result.strip()
                logger.debug(f"[-] Empty response from backend (attempt {attempt + 1}/{retries})")
            except (
                ConnectionError,
                OSError,
                RuntimeError,
                TimeoutError,
                ValueError,
            ) as e:
                last_error = str(e)
                wait_time = 2 ** (attempt + 1)
                logger.warning(f"[-] LLM call failed (attempt {attempt + 1}/{retries}): {e}. Waiting {wait_time}s...")
                time.sleep(wait_time)
        if last_error:
            logger.error(f"[!] Vision API error after {retries} attempts: {last_error}")
        return ""

    def call_vision_api_json(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        raw = self.call_vision_api(payload)
        if not raw:
            return None
        if isinstance(raw, dict):
            return raw
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning(f"[-] JSONDecodeError parsing Vision response: {e}. Attempting auto-repair...")
            repaired = _repair_and_parse_json(raw)
            if repaired:
                logger.info(f"[+] Auto-repaired JSON response successfully: {repaired}")
                return repaired
            logger.error(f"[!] Unable to salvage JSON response. Raw: {raw!r}")
            return None

    def classify_image(self, b64_image: str) -> dict[str, Any]:
        """Classifies an image using the configured LLM backend."""
        doc_types = self._get_effective_document_types()
        type_descriptions = []
        for dt, info in doc_types.items():
            desc = (info.get("classification_desc") or "").strip()
            if desc:
                type_descriptions.append(f"- '{dt}': {desc}")
            else:
                type_descriptions.append(f"- '{dt}'")
        type_str = "\n".join(type_descriptions)
        prompt = (
            "Analyze this document carefully. Which category fits best?\n"
            f"Options:\n{type_str}\n\n"
            "Reply ONLY with the exact category name - no JSON, no explanation."
        )
        payload = {"messages": [{"role": "user", "content": prompt, "images": [b64_image]}]}

        raw_resp = self.call_vision_api(payload)
        if raw_resp:
            cleaned = raw_resp.strip().strip("'\" ").lower()
            # 1. Exact match
            for dt in doc_types:
                if dt.lower() == cleaned:
                    return {"Document": dt}
            # 2. Substring match
            for dt in doc_types:
                if cleaned and (cleaned in dt.lower() or dt.lower() in cleaned):
                    return {"Document": dt}

        fallback = next(
            (k for k, v in doc_types.items() if (v.get("classification_desc") or "").strip()),
            None,
        )
        if not fallback and doc_types:
            fallback = next(iter(doc_types))
        return {"Document": fallback if fallback else "UNKNOWN"}

    def find_doc_type_config(self, doc_type: str) -> tuple[str, dict]:
        """Returns the document configuration for the given type. Case-insensitive."""
        if not isinstance(doc_type, str):
            fallback_key = next(iter(self._get_effective_document_types()), "UNKNOWN")
            logger.warning(
                f"[!] find_doc_type_config: Invalid doc_type {type(doc_type).__name__} "
                f'(value={doc_type!r}). Falling back to "{fallback_key}".'
            )
            doc_type = fallback_key
        doc_types = self._get_effective_document_types()
        # 1. Try exact match first (fast path)
        if doc_type in doc_types:
            return doc_type, doc_types[doc_type]
        # 2. Case-insensitive fallback
        lower_key = doc_type.strip().lower()
        for actual_key, info in doc_types.items():
            if actual_key.lower() == lower_key:
                return actual_key, info
        return doc_type, {}

    def _get_specific_rules_for_doctype(self, doc_type: str) -> tuple[str, str]:
        """Returns the name and specific extraction rules for a document type (excludes classification_desc)."""
        name, info = self.find_doc_type_config(doc_type)
        v = info.get("specific_rules")
        if v:
            return name, str(v)
        return name, ""

    def _build_json_fields(self, extraction_fields: dict[str, Any]) -> str:
        """Builds the JSON schema format prompt for data extraction."""
        field_entries = []
        for field, desc in extraction_fields.items():
            if field.lower() in ["document"]:
                continue
            if isinstance(desc, dict):
                desc_text = str(desc.get("description") or "")
            else:
                desc_text = str(desc or "")
            safe_desc = desc_text.replace('"', "'")
            field_entries.append(f'  "{field}": "{safe_desc}"')
        return "{\n" + ",\n".join(field_entries) + "\n}"

    def _build_extraction_prompt(
        self,
        doc_type_name: str,
        extraction_fields: dict[str, Any],
        base_rules_tmpl: str,
        specific_rules: str = "",
    ) -> str:
        """Constructs the extraction prompt."""
        if specific_rules:
            doc_section = f"\n<document_rules>\n{specific_rules}\n</document_rules>\n"
        else:
            doc_section = "\n"
        return f"<instruction>\nExtract data from this {doc_type_name}.\n</instruction>\n\n<base_rules>\n{base_rules_tmpl.strip()}\n</base_rules>{doc_section}<output_format>\n{self._build_json_fields(extraction_fields)}\n</output_format>"

    def extract_data_from_images_with_type(
        self,
        b64_image: str | list[str],
        doc_type: str,
        temperature: float = 0.0,
        target_fields: list[str] | None = None,
    ) -> dict[str, Any]:
        """Extracts data from one or more images based on document type rules."""
        _, matched_doc_info = self.find_doc_type_config(doc_type)
        raw_extraction_fields = dict(matched_doc_info.get("extraction_fields", {}))
        extraction_fields: dict[str, str] = {}
        for k, v in raw_extraction_fields.items():
            if isinstance(v, dict):
                extraction_fields[k] = str(v.get("description") or "")
            else:
                extraction_fields[k] = str(v) if v is not None else ""

        validation_cfg = matched_doc_info.get("validation", {})

        # Add signature check field if required
        if validation_cfg.get("signature_required", False) and not any(
            x in str(k).lower() for k in extraction_fields for x in ["signature", "signed"]
        ):
            sig_loc = validation_cfg.get("signature_location", "")
            desc = "true if handwritten signature/ink is present, otherwise false"
            if sig_loc:
                desc = f"{desc} (condition for this document: {sig_loc})"
            extraction_fields["Signed"] = desc

        if target_fields is not None:
            target_set = {f.lower() for f in target_fields}
            extraction_fields = {k: v for k, v in extraction_fields.items() if k.lower() in target_set}
            if not extraction_fields:
                return {}

        base_rules_tmpl = (
            f'1. MISSING DATA: If information is missing in the document, enter EXACTLY "{MISSING_PLACEHOLDER}".\n'
            "2. STRIKETHROUGH & CROSSED-OUT TEXT RULE (CRITICAL):\n"
            "   - Examine every word (printed OR handwritten) carefully for pen strokes, horizontal lines, or scribbles passing through it.\n"
            "   - Any text, name, or header entry (printed or handwritten) with a line, stroke, or line-through drawn THROUGH or ACROSS it is VOID / CROSSED OUT / DELETED.\n"
            "   - On scans, drawings, or forms, a line drawn through a name, value, or header text means the text is STRUCK OUT. DO NOT extract crossed-out values under ANY circumstances.\n"
            "   - If crossed-out text has a NEW LEGIBLE REPLACEMENT above/beside it -> extract ONLY the replacement.\n"
            f'   - If crossed-out text has NO replacement -> treat that field as missing and enter EXACTLY "{MISSING_PLACEHOLDER}".\n'
            "3. OUTPUT FORMAT: Respond exclusively in the specified JSON format."
        )
        doc_type_name, specific_rules = self._get_specific_rules_for_doctype(doc_type)
        prompt2 = self._build_extraction_prompt(
            doc_type_name=doc_type_name,
            extraction_fields=extraction_fields,
            base_rules_tmpl=base_rules_tmpl,
            specific_rules=specific_rules,
        )

        images_list = [b64_image] if isinstance(b64_image, str) else b64_image
        effective_images = [images_list[0]] if images_list else []

        # Build dynamic C++ JSON Schema to enforce exact key constraints on sampler level
        json_schema = (
            {
                "type": "object",
                "properties": {field: {"type": "string"} for field in extraction_fields},
                "required": list(extraction_fields),
                "additionalProperties": False,
            }
            if extraction_fields
            else None
        )

        payload2: dict[str, Any] = {
            "messages": [
                {
                    "role": "system",
                    "content": "You are a precise data extraction assistant. Extract ONLY the requested JSON keys. Never invent or add unrequested fields. Keep your thinking process extremely short and output JSON immediately.",
                },
                {"role": "user", "content": prompt2, "images": effective_images},
            ],
            "temperature": temperature,
            "json_schema": json_schema,
        }

        res2 = self.call_vision_api_json(payload2)
        if not res2 or not isinstance(res2, dict):
            return {}

        # Case normalization and strict filtering of requested fields
        raw_fields = matched_doc_info.get("extraction_fields", {})
        optional_list = matched_doc_info.get("validation", {}).get("optional_fields") or []
        sig_req = matched_doc_info.get("validation", {}).get("signature_required", False)

        if raw_fields or sig_req:
            allowed_keys = set(extraction_fields.keys()) | set(optional_list)
        else:
            allowed_keys = set(res2.keys()) | set(optional_list)

        normalized_res2: dict[str, Any] = {}
        lower_to_key = {ref_k.lower(): ref_k for ref_k in allowed_keys}
        for k, v in res2.items():
            ref_key = lower_to_key.get(k.lower())
            if ref_key or not (raw_fields or sig_req):
                normalized_res2[ref_key or k] = v
        res2 = normalized_res2

        optional_fields = {k.lower() for k in optional_list}
        all_keys = set(extraction_fields.keys()) | set(res2.keys())

        for key in list(all_keys):
            val = res2.get(key)
            if key == "Signed":
                if isinstance(val, str):
                    res2["Signed"] = val.strip().lower() in ("true", "1", "yes")
                else:
                    res2["Signed"] = bool(val)
            elif is_missing_value(val):
                if key.lower() in optional_fields:
                    res2[key] = ""
                else:
                    res2[key] = MISSING_PLACEHOLDER
            else:
                res2[key] = clean_extracted_value(val)

        return res2

    def extract_data_from_text_with_type(
        self,
        spatial_text: str,
        doc_type: str,
        temperature: float = 0.0,
        target_fields: list[str] | None = None,
    ) -> dict[str, Any]:
        """Extracts structured data from layout-aware spatial text without image inference."""
        if not spatial_text or not isinstance(spatial_text, str) or len(spatial_text.strip()) < 10:
            return {}

        _, matched_doc_info = self.find_doc_type_config(doc_type)
        raw_extraction_fields = dict(matched_doc_info.get("extraction_fields", {}))
        extraction_fields: dict[str, str] = {}
        for k, v in raw_extraction_fields.items():
            if isinstance(v, dict):
                extraction_fields[k] = str(v.get("description") or "")
            else:
                extraction_fields[k] = str(v) if v is not None else ""

        # Exclude signature verification from text-only extraction
        if "Signed" in extraction_fields:
            extraction_fields.pop("Signed", None)

        if target_fields is not None:
            target_set = {f.lower() for f in target_fields}
            extraction_fields = {
                k: v for k, v in extraction_fields.items() if k.lower() in target_set and k != "Signed"
            }

        if not extraction_fields:
            return {}

        base_rules_tmpl = (
            f'1. MISSING DATA: If information is missing in the text, enter EXACTLY "{MISSING_PLACEHOLDER}".\n'
            "2. SPATIAL LAYOUT CONTEXT:\n"
            "   - Text lines are prefixed with normalized spatial tags `[pos: y=..., x=...]` where y is top-to-bottom (0.0=top, 1.0=bottom) and x is left-to-right (0.0=left, 1.0=right).\n"
            "   - Use these spatial positions to understand document sections, sender/recipient headers, dates, and tables.\n"
            "3. OUTPUT FORMAT: Respond exclusively in the specified JSON format."
        )
        doc_type_name, specific_rules = self._get_specific_rules_for_doctype(doc_type)
        prompt_instruction = self._build_extraction_prompt(
            doc_type_name=doc_type_name,
            extraction_fields=extraction_fields,
            base_rules_tmpl=base_rules_tmpl,
            specific_rules=specific_rules,
        )

        user_content = (
            f"{prompt_instruction}\n\n<document_spatial_text>\n{spatial_text.strip()}\n</document_spatial_text>"
        )

        json_schema = (
            {
                "type": "object",
                "properties": {field: {"type": "string"} for field in extraction_fields},
                "required": list(extraction_fields),
                "additionalProperties": False,
            }
            if extraction_fields
            else None
        )

        payload: dict[str, Any] = {
            "messages": [
                {
                    "role": "system",
                    "content": "You are a precise data extraction assistant. Extract ONLY the requested JSON keys from the provided spatial text. Never invent or add unrequested fields. Output valid JSON immediately.",
                },
                {"role": "user", "content": user_content},
            ],
            "temperature": temperature,
            "json_schema": json_schema,
        }

        res = self.call_vision_api_json(payload)
        if not res or not isinstance(res, dict):
            return {}

        raw_fields = matched_doc_info.get("extraction_fields", {})
        optional_list = matched_doc_info.get("validation", {}).get("optional_fields") or []

        allowed_keys = (
            set(extraction_fields.keys()) | set(optional_list) if raw_fields else set(res.keys()) | set(optional_list)
        )

        normalized_res: dict[str, Any] = {}
        lower_to_key = {ref_k.lower(): ref_k for ref_k in allowed_keys}
        for k, v in res.items():
            ref_key = lower_to_key.get(k.lower())
            if ref_key or not raw_fields:
                normalized_res[ref_key or k] = v
        res = normalized_res

        optional_fields = {k.lower() for k in optional_list}
        all_keys = set(extraction_fields.keys()) | set(res.keys())

        for key in list(all_keys):
            val = res.get(key)
            if is_missing_value(val):
                if key.lower() in optional_fields:
                    res[key] = ""
                else:
                    res[key] = MISSING_PLACEHOLDER
            else:
                res[key] = clean_extracted_value(val)

        return res

    def describe_for_unknown(self, b64_image: str) -> dict[str, Any]:
        """Returns a short description of the image (for UNKNOWN cases)."""
        prompt = "<instruction>Describe the document briefly in 2-3 sentences.</instruction>"
        res_raw = self.call_vision_api({"messages": [{"role": "user", "content": prompt, "images": [b64_image]}]})
        return {
            "description": res_raw.strip() if isinstance(res_raw, str) else "",
            "pages": [],
        }


__all__ = ["LLMExtractor"]
