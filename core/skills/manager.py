"""Skill YAML storage and configuration manager."""

import glob
import logging
import os
import re
import time
from typing import Any

import yaml

logger = logging.getLogger(__name__)


class SkillManager:
    """Manages loading, saving, deleting, and duplicating skill YAML files."""

    def __init__(self, skills_dir: str = "./settings/skills"):
        self.skills_dir = os.path.abspath(skills_dir)
        os.makedirs(self.skills_dir, exist_ok=True)

    def list_skills(self) -> list[dict[str, Any]]:
        """Loads all skills from the skills/ directory."""
        skills: list[dict[str, Any]] = []
        yaml_files = glob.glob(os.path.join(self.skills_dir, "*.yaml")) + glob.glob(
            os.path.join(self.skills_dir, "*.yml")
        )
        for filepath in sorted(yaml_files):
            try:
                with open(filepath, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    if isinstance(data, dict) and "id" in data:
                        skills.append(data)
            except OSError as e:
                logger.error("[SkillManager] Error reading %s: %s", filepath, e)
        return skills

    def get_skill(self, skill_id: str) -> dict[str, Any] | None:
        """Finds a skill by ID."""
        for skill in self.list_skills():
            if skill.get("id") == skill_id:
                return skill
        return None

    def save_skill(self, skill_data: dict[str, Any]) -> str:
        """Saves a skill to its individual YAML file."""
        skill_id = skill_data.get("id", "").strip()  # type: ignore[union-attr]
        if not skill_id:
            name_slug = re.sub(
                r"[^a-z0-9_]", "_", skill_data.get("name", "unnamed").lower()
            )  # type: ignore[arg-type]
            skill_id = f"skill_{name_slug}_{int(time.time())}"
            skill_data["id"] = skill_id

        filepath = os.path.join(self.skills_dir, f"{skill_id}.yaml")
        with open(filepath, "w", encoding="utf-8") as f:
            yaml.safe_dump(skill_data, f, allow_unicode=True, sort_keys=False)
        logger.info("[SkillManager] Skill '%s' saved to %s", skill_id, filepath)
        return skill_id

    def delete_skill(self, skill_id: str) -> bool:
        """Deletes a skill's YAML file."""
        filepath = os.path.join(self.skills_dir, f"{skill_id}.yaml")
        if os.path.exists(filepath):
            os.remove(filepath)
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
