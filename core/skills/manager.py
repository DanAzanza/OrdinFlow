"""Skill YAML storage, configuration, and engine factory manager."""

from __future__ import annotations

import glob
import logging
import os
import re
import threading
import time
from typing import Any

import yaml

from core.skills.base import BaseSkill
from core.skills.engines.export_engine import ExportEngine
from core.skills.engines.import_engine import ImportEngine

logger = logging.getLogger(__name__)


class SkillManager:
    """Manages loading, saving, deleting, and instantiating modular skill engines."""

    def __init__(self, skills_dir: str = "./settings/skills"):
        self.skills_dir = os.path.abspath(skills_dir)
        os.makedirs(self.skills_dir, exist_ok=True)
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._lock = threading.Lock()

    def list_skills(self) -> list[dict[str, Any]]:
        """Loads all skills from the skills/ directory using mtime cache."""
        skills: list[dict[str, Any]] = []
        yaml_files = glob.glob(os.path.join(self.skills_dir, "*.yaml")) + glob.glob(
            os.path.join(self.skills_dir, "*.yml")
        )
        seen_paths: set[str] = set()

        with self._lock:
            for filepath in sorted(yaml_files):
                # Ignore example templates and state files
                fname = os.path.basename(filepath)
                if fname.endswith(".example.yaml") or fname == "queue_state.json":
                    continue

                seen_paths.add(filepath)
                try:
                    mtime = os.path.getmtime(filepath)
                    cached = self._cache.get(filepath)
                    if cached is not None and cached[0] == mtime:
                        skills.append(cached[1])
                        continue

                    with open(filepath, encoding="utf-8") as f:
                        data = yaml.safe_load(f)
                        if isinstance(data, dict) and "id" in data:
                            self._cache[filepath] = (mtime, data)
                            skills.append(data)
                except OSError as e:
                    logger.error("[SkillManager] Error reading %s: %s", filepath, e)

            # Evict removed files from cache
            for cached_path in list(self._cache.keys()):
                if cached_path not in seen_paths:
                    self._cache.pop(cached_path, None)

        return skills

    def get_skill(self, skill_id: str) -> dict[str, Any] | None:
        """Finds a skill definition by ID."""
        for skill in self.list_skills():
            if skill.get("id") == skill_id:
                return skill

        # Fallback to direct file lookup
        for ext in (".yaml", ".yml"):
            target = os.path.join(self.skills_dir, f"{skill_id}{ext}")
            if os.path.isfile(target):
                try:
                    with open(target, encoding="utf-8") as f:
                        data = yaml.safe_load(f)
                        if isinstance(data, dict):
                            return data
                except (OSError, yaml.YAMLError):
                    pass
        return None

    def get_default_import_skill(self) -> dict[str, Any] | None:
        """Finds the default or first enabled import skill."""
        skills = self.list_skills()
        for s in skills:
            if s.get("type") == "import" and s.get("enabled", True):
                return s
        for s in skills:
            if s.get("type") == "import":
                return s
        return None

    def get_document_types_for_skill(self, skill_id: str) -> dict[str, Any]:
        """Returns the document_types map defined in the specified skill."""
        skill = self.get_skill(skill_id)
        if skill and isinstance(skill.get("document_types"), dict):
            return dict(skill["document_types"])
        return {}

    def save_document_types_for_skill(self, skill_id: str, doc_types: dict[str, Any]) -> bool:
        """Saves updated document_types to a skill definition."""
        skill = self.get_skill(skill_id)
        if not skill:
            logger.warning("[SkillManager] Cannot save doc_types: skill '%s' not found.", skill_id)
            return False
        skill["document_types"] = doc_types
        self.save_skill(skill)
        return True

    def get_skill_engine(
        self,
        skill_id: str,
        vision_extractor: Any = None,
        processor: Any = None,
    ) -> BaseSkill | None:
        """Instantiates the appropriate executable BaseSkill engine for the given skill ID."""
        definition = self.get_skill(skill_id)
        if not definition:
            logger.warning("[SkillManager] No definition found for skill '%s'", skill_id)
            return None

        skill_type = definition.get("type", "export")
        if skill_type == "import":
            return ImportEngine(definition, processor=processor)
        else:
            return ExportEngine(
                definition,
                skill_manager=self,
                vision_extractor=vision_extractor,
            )

    def save_skill(self, skill_data: dict[str, Any]) -> str:
        """Saves a skill to its individual YAML file."""
        skill_id = str(skill_data.get("id") or "").strip()
        if not skill_id:
            name = str(skill_data.get("name") or "unnamed")
            name_slug = re.sub(r"[^a-z0-9_]+", "_", name.lower()).strip("_")
            base_slug = name_slug or "skill"
            candidate = base_slug
            counter = 2
            while os.path.exists(os.path.join(self.skills_dir, f"{candidate}.yaml")):
                candidate = f"{base_slug}_{counter}"
                counter += 1
            skill_id = candidate
            skill_data["id"] = skill_id

        filepath = os.path.join(self.skills_dir, f"{skill_id}.yaml")
        with open(filepath, "w", encoding="utf-8") as f:
            yaml.safe_dump(skill_data, f, allow_unicode=True, sort_keys=False)

        with self._lock:
            try:
                mtime = os.path.getmtime(filepath)
                self._cache[filepath] = (mtime, skill_data)
            except OSError as e:
                logger.debug("[SkillManager] Could not get mtime for %s: %s", filepath, e)

        logger.info("[SkillManager] Skill '%s' saved to %s", skill_id, filepath)
        return skill_id

    def delete_skill(self, skill_id: str) -> bool:
        """Deletes a skill's YAML file."""
        filepath = os.path.join(self.skills_dir, f"{skill_id}.yaml")
        if os.path.exists(filepath):
            os.remove(filepath)
            with self._lock:
                self._cache.pop(filepath, None)
            logger.info("[SkillManager] Skill '%s' deleted.", skill_id)
            return True
        return False

    def duplicate_skill(self, skill_id: str) -> dict[str, Any] | None:
        """Duplicates an existing skill."""
        original = self.get_skill(skill_id)
        if not original:
            return None

        new_data = dict(original)
        new_id = f"{skill_id}_copy_{int(time.time()) % 10000}"
        new_data["id"] = new_id
        new_data["name"] = f"{original.get('name', 'Skill')} (Copy)"
        self.save_skill(new_data)
        return new_data
