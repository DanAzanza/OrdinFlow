"""Case folder routing, document filtering, and .meta sidecar tracking for RPA export skills."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)


def filter_matching_files(
    folder_path: str,
    allowed_types: list[str] | None = None,
    delimiter: str = "__",
) -> list[dict[str, Any]]:
    """Filters PDF files in a case folder according to allowed document types and loads sidecar metadata."""
    matching_files: list[dict[str, Any]] = []
    if not os.path.exists(folder_path) or not os.path.isdir(folder_path):
        return matching_files

    if not allowed_types or "*" in allowed_types or "ALL" in [t.upper() for t in allowed_types]:
        allowed_types_clean = None
    else:
        allowed_types_clean = [t.strip().lower() for t in allowed_types if t.strip()]

    for fname in sorted(os.listdir(folder_path)):
        if fname.lower().endswith(".pdf"):
            full_path = os.path.join(folder_path, fname)
            meta_path = full_path + ".meta"
            doc_type = "UNKNOWN"
            meta_data: dict[str, Any] = {}

            if os.path.exists(meta_path):
                try:
                    with open(meta_path, encoding="utf-8") as f:
                        loaded = json.load(f)
                        if isinstance(loaded, dict):
                            meta_data = loaded
                            doc_type = (
                                loaded.get("Document")
                                or loaded.get("Dokument")
                                or loaded.get("document_type")
                                or "UNKNOWN"
                            )
                except (json.JSONDecodeError, OSError):
                    pass

            if doc_type == "UNKNOWN":
                if delimiter and delimiter in fname:
                    parts = fname.split(delimiter)
                    if len(parts) >= 1 and parts[0]:
                        doc_type = parts[0]
                elif "__" in fname:
                    parts = fname.split("__")
                    if len(parts) >= 1 and parts[0]:
                        doc_type = parts[0]

            is_match = False
            if allowed_types_clean is None:
                is_match = True
            else:
                doc_subtypes = [t.strip().lower() for t in doc_type.split("+") if t.strip()]
                is_match = any(st in allowed_types_clean for st in doc_subtypes)

            if is_match:
                executed_skills = meta_data.get("executed_skills", [])
                if not isinstance(executed_skills, list):
                    executed_skills = []
                matching_files.append(
                    {
                        "filename": fname,
                        "fullpath": full_path,
                        "document_type": doc_type,
                        "meta": meta_data,
                        "executed_skills": executed_skills,
                    }
                )

    return matching_files


def find_pending_cases(
    target_base_dir: str,
    skill_id: str,
    allowed_types: list[str] | None = None,
    folder_structure: list[str] | None = None,
    delimiter: str = "__",
) -> list[dict[str, Any]]:
    """Finds all approved case folders with unprocessed files matching the skill's document types."""
    if not os.path.exists(target_base_dir):
        return []

    types_to_match = allowed_types or ["*"]
    pending_cases: list[dict[str, Any]] = []

    for folder_name in sorted(os.listdir(target_base_dir)):
        folder_path = os.path.join(target_base_dir, folder_name)
        if not os.path.isdir(folder_path):
            continue
        if not os.path.exists(os.path.join(folder_path, ".approved")):
            continue

        matching = filter_matching_files(folder_path, types_to_match, delimiter=delimiter)
        unprocessed_files = [f for f in matching if skill_id not in f.get("executed_skills", [])]

        if unprocessed_files:
            parts = folder_name.split(delimiter) if delimiter in folder_name else folder_name.split("__")
            parsed_meta: dict[str, str] = {}

            if folder_structure and isinstance(folder_structure, list):
                for idx, key in enumerate(folder_structure):
                    clean_key = str(key).strip("{} ")
                    raw_val = parts[idx].strip() if idx < len(parts) else ""
                    val = "" if raw_val == "----" else raw_val
                    if clean_key:
                        parsed_meta[clean_key] = val
                        parsed_meta[f"{{{clean_key}}}"] = val
            else:
                for idx, part in enumerate(parts):
                    clean_part = "" if part.strip() == "----" else part.strip()
                    parsed_meta[f"part_{idx}"] = clean_part

            # Automatically derive Vorname / Nachname if Person or Patient is present in comma notation
            person_val = parsed_meta.get("Person") or parsed_meta.get("person") or parsed_meta.get("Patient") or parsed_meta.get("patient") or ""
            if person_val and "," in person_val:
                person_parts = person_val.split(",", 1)
                parsed_meta.setdefault("Nachname", person_parts[0].strip())
                parsed_meta.setdefault("Vorname", person_parts[1].strip())
                parsed_meta.setdefault("{Nachname}", person_parts[0].strip())
                parsed_meta.setdefault("{Vorname}", person_parts[1].strip())

            pending_cases.append(
                {
                    "folder_name": folder_name,
                    "folder_path": folder_path,
                    "matching_files": unprocessed_files,
                    "unprocessed_count": len(unprocessed_files),
                    "parsed_metadata": parsed_meta,
                }
            )

    return pending_cases


def mark_file_skill_executed(filepath: str, skill_id: str) -> bool:
    """Updates the .meta sidecar file with the executed skill ID and timestamp."""
    meta_path = filepath + ".meta"
    data: dict[str, Any] = {}
    if os.path.exists(meta_path):
        try:
            with open(meta_path, encoding="utf-8") as f:
                data = json.load(f) or {}
        except (json.JSONDecodeError, OSError):
            data = {}

    executed = data.get("executed_skills", [])
    if not isinstance(executed, list):
        executed = []
    if skill_id not in executed:
        executed.append(skill_id)
    data["executed_skills"] = executed

    history = data.get("skill_execution_history", {})
    if not isinstance(history, dict):
        history = {}
    history[skill_id] = time.time()
    data["skill_execution_history"] = history

    try:
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("[CaseRouter] Marked '%s' as executed by '%s'", filepath, skill_id)
        return True
    except OSError as e:
        logger.error("[CaseRouter] Failed writing metadata to %s: %s", meta_path, e)
        return False
