"""CRUD and YAML export/import API endpoints for skills management."""

from __future__ import annotations

import logging
import os

import yaml
from flask import Blueprint, jsonify, request

from core.skills import SkillManager, get_skill_manager
from core.utils import safe_join_path
from routes.state import DashboardState

skills_crud_api_bp = Blueprint("api_skills_crud", __name__)
logger = logging.getLogger(__name__)


def _get_skill_manager() -> SkillManager:
    return get_skill_manager()


@skills_crud_api_bp.route("/api/skills", methods=["GET"])
def get_skills():
    """Lists all registered automation and export skills."""
    skills = _get_skill_manager().list_skills()
    return jsonify({"skills": skills})


@skills_crud_api_bp.route("/api/skills", methods=["POST"])
def save_skill():
    """Creates or updates a skill configuration."""
    data = request.json
    if not isinstance(data, dict):
        return jsonify({"error": "Invalid JSON payload"}), 400

    mgr = _get_skill_manager()
    original_name = str(
        data.pop("original_name", None) or data.pop("old_name", None) or data.pop("original_id", None) or ""
    ).strip()
    name = str(data.get("name") or data.get("id") or "").strip()
    if not name:
        name = "Untitled Skill"
        data["name"] = name

    is_valid, err_msg = mgr.validate_name(name)
    if not is_valid:
        return jsonify({"error": err_msg}), 400

    try:
        if original_name and original_name != name:
            saved_name = mgr.rename_skill(original_name, name, data)
        else:
            saved_name = mgr.save_skill(data)
        return jsonify({"status": "ok", "skill_id": saved_name, "name": saved_name})
    except ValueError as e:
        logger.warning("[SkillsCrudAPI] Validation error saving skill: %s", e)
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error("[SkillsCrudAPI] Error saving skill: %s", e, exc_info=True)
        return jsonify({"error": "Failed to save skill"}), 400


@skills_crud_api_bp.route("/api/skills/<skill_id>", methods=["DELETE"])
def delete_skill(skill_id: str):
    """Deletes a skill by ID."""
    success = _get_skill_manager().delete_skill(skill_id)
    if success:
        return jsonify({"status": "ok"})
    return jsonify({"error": "Skill not found"}), 404


@skills_crud_api_bp.route("/api/skills/<skill_id>/duplicate", methods=["POST"])
def duplicate_skill(skill_id: str):
    """Duplicates an existing skill."""
    new_skill = _get_skill_manager().duplicate_skill(skill_id)
    if new_skill:
        return jsonify({"status": "ok", "skill": new_skill})
    return jsonify({"error": "Could not duplicate skill"}), 400


@skills_crud_api_bp.route("/api/skills/to_yaml", methods=["POST"])
def skill_to_yaml():
    """Serializes a JSON skill structure to YAML string format."""
    data = request.json or {}
    skill_data = data.get("skill") or data
    try:
        from core.skills.manager import _SkillYamlDumper

        yaml_str = yaml.dump(skill_data, Dumper=_SkillYamlDumper, allow_unicode=True, sort_keys=False)
        return jsonify({"status": "ok", "yaml": yaml_str})
    except Exception as e:
        logger.error("[SkillsCrudAPI] Error serializing YAML: %s", e, exc_info=True)
        return jsonify({"error": "Failed to serialize skill to YAML"}), 400


@skills_crud_api_bp.route("/api/skills/from_yaml", methods=["POST"])
def skill_from_yaml():
    """Deserializes a YAML string into a Python/JSON dictionary representation."""
    data = request.json or {}
    yaml_str = str(data.get("yaml") or "")
    try:
        parsed = yaml.safe_load(yaml_str)
        if not isinstance(parsed, dict):
            return jsonify({"error": "YAML must represent a mapping/dictionary"}), 400
        return jsonify({"status": "ok", "skill": parsed})
    except yaml.YAMLError:
        return jsonify({"error": "Invalid YAML syntax"}), 400
    except Exception as e:
        logger.error("[SkillsCrudAPI] Error parsing YAML: %s", e, exc_info=True)
        return jsonify({"error": "Failed to parse YAML"}), 400


@skills_crud_api_bp.route("/api/skills/<skill_id>/yaml", methods=["GET", "POST"])
def skill_yaml_file(skill_id: str):
    """Fetches or saves a skill definition directly in raw YAML text format."""
    mgr = _get_skill_manager()
    clean_name = mgr.sanitize_name(skill_id)
    filepath = safe_join_path(mgr.skills_dir, f"{clean_name}.yaml")

    if request.method == "GET":
        if filepath and os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                return jsonify({"status": "ok", "yaml": content})
            except Exception as e:
                logger.error("[SkillsCrudAPI] Error reading skill file %s: %s", filepath, e, exc_info=True)
                return jsonify({"error": "Failed to read skill file"}), 500
        else:
            skill = mgr.get_skill(skill_id)
            if skill:
                return jsonify({"status": "ok", "yaml": yaml.safe_dump(skill, allow_unicode=True, sort_keys=False)})
            return jsonify({"error": "Skill not found"}), 404

    # POST: Save raw YAML directly
    data = request.json or {}
    yaml_str = str(data.get("yaml") or "")
    if not yaml_str.strip():
        return jsonify({"error": "Empty YAML content"}), 400

    try:
        parsed = yaml.safe_load(yaml_str)
        if not isinstance(parsed, dict):
            return jsonify({"error": "YAML must represent a dictionary"}), 400
        name = str(parsed.get("name") or skill_id).strip()
        parsed["name"] = name
        parsed["id"] = name
        saved_name = mgr.save_skill(parsed)
        return jsonify({"status": "ok", "skill_id": saved_name, "name": saved_name, "skill": parsed})
    except ValueError as e:
        logger.warning("[SkillsCrudAPI] Validation error saving raw YAML: %s", e)
        return jsonify({"error": str(e)}), 400
    except yaml.YAMLError:
        return jsonify({"error": "Invalid YAML syntax"}), 400
    except Exception as e:
        logger.error("[SkillsCrudAPI] Error saving raw YAML for skill %s: %s", skill_id, e, exc_info=True)
        return jsonify({"error": "Failed to save skill definition"}), 400


@skills_crud_api_bp.route("/api/skills/<import_skill_id>/documents", methods=["GET"])
def get_skill_document_types(import_skill_id: str):
    """Retrieves configured document types for a specific import skill."""
    mgr = _get_skill_manager()
    doc_types = mgr.get_document_types_for_skill(import_skill_id)
    return jsonify({"document_types": doc_types})


@skills_crud_api_bp.route("/api/skills/<import_skill_id>/documents", methods=["PUT"])
def save_skill_document_types(import_skill_id: str):
    """Saves configured document types for a specific import skill."""
    mgr = _get_skill_manager()
    data = request.json or {}
    doc_types = data.get("document_types", {})
    if not isinstance(doc_types, dict):
        return jsonify({"error": "document_types dict required"}), 400

    mgr.save_document_types_for_skill(import_skill_id, doc_types)
    if DashboardState.config:
        DashboardState.config.document_types = doc_types
    return jsonify({"status": "ok", "document_types": doc_types})
