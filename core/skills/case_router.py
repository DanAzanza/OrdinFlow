"""Case folder routing, document filtering, and .meta sidecar tracking for RPA export skills."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import time
from typing import Any

from core.routing import parse_folder_name
from core.utils import sanitize_safe_path

logger = logging.getLogger(__name__)


def filter_matching_files(
    folder_path: str,
    allowed_types: list[str] | None = None,
    delimiter: str = "__",
) -> list[dict[str, Any]]:
    """Filters PDF files in a case folder according to allowed document types and loads sidecar metadata."""
    matching_files: list[dict[str, Any]] = []
    if not folder_path or not isinstance(folder_path, str):
        return matching_files

    is_safe, clean_folder = sanitize_safe_path(folder_path)
    if not is_safe or not clean_folder:
        return matching_files

    folder_p = Path(clean_folder).resolve()
    if not folder_p.is_dir():
        return matching_files

    if not allowed_types or "*" in allowed_types or "ALL" in [t.upper() for t in allowed_types]:
        allowed_types_clean = None
    else:
        allowed_types_clean = [t.strip().lower() for t in allowed_types if t.strip()]

    try:
        entries = sorted(folder_p.iterdir(), key=lambda p: p.name.lower())
    except OSError:
        return matching_files

    for entry in entries:
        if entry.is_file() and entry.name.lower().endswith(".pdf"):
            fname = entry.name
            full_path = str(entry)
            meta_path = Path(str(entry) + ".meta")
            doc_type = "UNKNOWN"
            meta_data: dict[str, Any] = {}

            if meta_path.is_file():
                try:
                    with meta_path.open("r", encoding="utf-8") as f:
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
            parsed_meta = parse_folder_name(
                folder_name,
                folder_structure=folder_structure,
                delimiter=delimiter if delimiter in folder_name else "__",
            )

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


def extract_all_skill_document_types(skill_def: dict[str, Any]) -> list[str]:
    """Recursively extracts all document types from top-level and nested FOR_EACH_DOCUMENT actions."""
    if not isinstance(skill_def, dict):
        return ["*"]

    collected: list[str] = []
    top_types = skill_def.get("document_types") or skill_def.get("suggested_document_types") or []
    if isinstance(top_types, list):
        collected.extend([str(t).strip() for t in top_types if str(t).strip()])
    elif isinstance(top_types, str) and top_types.strip():
        collected.append(top_types.strip())

    def _walk_actions(actions: list[dict[str, Any]]) -> None:
        for act in actions:
            if not isinstance(act, dict):
                continue
            act_type = str(act.get("action_type") or act.get("type", "")).upper()
            if act_type == "FOR_EACH_DOCUMENT":
                inner_types = act.get("document_types") or act.get("allowed_types") or []
                if isinstance(inner_types, list):
                    collected.extend([str(t).strip() for t in inner_types if str(t).strip()])
                elif isinstance(inner_types, str) and inner_types.strip():
                    collected.append(inner_types.strip())
                if isinstance(act.get("actions"), list):
                    _walk_actions(act["actions"])
            elif act_type in ("BRANCH", "IF_CONDITION"):
                if isinstance(act.get("then_actions"), list):
                    _walk_actions(act["then_actions"])
                if isinstance(act.get("else_actions"), list):
                    _walk_actions(act["else_actions"])
            elif act_type in ("FOR_EACH", "WHILE_LOOP"):
                if isinstance(act.get("actions"), list):
                    _walk_actions(act["actions"])

    for task in skill_def.get("tasks", []):
        if isinstance(task, dict) and isinstance(task.get("actions"), list):
            _walk_actions(task["actions"])

    for step in skill_def.get("steps", []) + skill_def.get("actions", []):
        if isinstance(step, dict):
            _walk_actions([step])

    unique_types: list[str] = []
    for t in collected:
        if t not in unique_types:
            unique_types.append(t)

    if not unique_types or "*" in unique_types or "ALL" in [t.upper() for t in unique_types]:
        return ["*"]
    return unique_types


def mark_file_skill_executed(filepath: str, skill_id: str) -> bool:
    """Updates the .meta sidecar file with the executed skill ID and timestamp using atomic file replacement."""
    if not filepath or not isinstance(filepath, str):
        return False
    is_safe, clean_fp = sanitize_safe_path(filepath)
    if not is_safe or not clean_fp:
        return False

    fp = Path(clean_fp).resolve()
    meta_p = Path(str(fp) + ".meta")
    data: dict[str, Any] = {}
    if meta_p.is_file():
        try:
            with meta_p.open("r", encoding="utf-8") as f:
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

    tmp_p = Path(f"{meta_p}.tmp_{os.getpid()}_{int(time.time() * 1000)}")
    last_err: Exception | None = None

    for attempt in range(5):
        try:
            with tmp_p.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            tmp_p.replace(meta_p)
            logger.info("[CaseRouter] Marked '%s' as executed by '%s'", filepath, skill_id)
            return True
        except OSError as e:
            last_err = e
            time.sleep(0.05 * (attempt + 1))

    # Clean up orphaned tmp file if present
    if tmp_p.is_file():
        try:
            tmp_p.unlink(missing_ok=True)
        except OSError:
            pass

    logger.error("[CaseRouter] Failed writing metadata to %s after 5 attempts: %s", meta_p, last_err)
    return False
