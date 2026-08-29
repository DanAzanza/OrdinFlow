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
from core.utils import sanitize_safe_path

logger = logging.getLogger(__name__)


class _SkillYamlDumper(yaml.SafeDumper):
    pass


def _multiline_str_representer(dumper: yaml.SafeDumper, data: str) -> yaml.ScalarNode:
    clean = data.replace("\r\n", "\n")
    if "\n" in clean:
        return dumper.represent_scalar("tag:yaml.org,2002:str", clean, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", clean)


yaml.add_representer(str, _multiline_str_representer, Dumper=_SkillYamlDumper)


INVALID_NAME_CHARS: set[str] = set(r':/\*?"<>|')


class SkillManager:
    """Manages loading, saving, deleting, renaming, and instantiating modular skill engines."""

    def __init__(self, skills_dir: str = "./settings/skills"):
        self.skills_dir = os.path.abspath(skills_dir)
        os.makedirs(self.skills_dir, exist_ok=True)
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._lock = threading.Lock()

    @classmethod
    def validate_name(cls, name: str) -> tuple[bool, str]:
        """Validates that a skill name is non-empty and contains no filesystem/path-breaking characters."""
        trimmed = (name or "").strip()
        if not trimmed:
            return False, "Skill name cannot be empty."

        found_invalid = [c for c in trimmed if c in INVALID_NAME_CHARS]
        if found_invalid:
            unique_chars = "".join(sorted(set(found_invalid)))
            return (
                False,
                f"Skill name contains forbidden character(s): '{unique_chars}'. Path characters like ':', '/', '\\' are not allowed.",
            )
        return True, ""

    @classmethod
    def sanitize_name(cls, name: str) -> str:
        """Sanitizes a skill name for filesystem storage by removing forbidden characters."""
        trimmed = (name or "").strip()
        cleaned = re.sub(r'[\\/:*?"<>|]+', "_", trimmed).strip(" ._")
        return cleaned or "unnamed_skill"

    @classmethod
    def slugify_name(cls, name: str) -> str:
        """Converts a skill name to a lowercased slug without special characters."""
        return re.sub(r"[^a-z0-9_]+", "_", (name or "").lower()).strip("_")

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
                        if isinstance(data, dict):
                            base_name = os.path.splitext(fname)[0]
                            skill_name = str(data.get("name") or data.get("id") or base_name).strip()
                            data["name"] = skill_name
                            data["id"] = skill_name
                            self._cache[filepath] = (mtime, data)
                            skills.append(data)
                except OSError as e:
                    logger.error("[SkillManager] Error reading %s: %s", filepath, e)

            # Evict removed files from cache
            for cached_path in list(self._cache.keys()):
                if cached_path not in seen_paths:
                    self._cache.pop(cached_path, None)

        return skills

    def get_skill(self, skill_id_or_name: str) -> dict[str, Any] | None:
        """Finds a skill definition by name, ID, slug, or filename."""
        query = str(skill_id_or_name or "").strip()
        if not query:
            return None

        query_slug = self.slugify_name(query)
        for skill in self.list_skills():
            s_name = str(skill.get("name") or "")
            s_id = str(skill.get("id") or "")
            if s_name == query or s_id == query:
                return skill
            if query_slug and (self.slugify_name(s_name) == query_slug or self.slugify_name(s_id) == query_slug):
                return skill

        # Fallback to direct file lookup
        for ext in (".yaml", ".yml"):
            sanitized = self.sanitize_name(query)
            for candidate_name in (query, sanitized, query_slug):
                if not candidate_name:
                    continue
                target = os.path.join(self.skills_dir, f"{candidate_name}{ext}")
                if os.path.isfile(target):
                    try:
                        with open(target, encoding="utf-8") as f:
                            data = yaml.safe_load(f)
                            if isinstance(data, dict):
                                base_name = os.path.splitext(os.path.basename(target))[0]
                                skill_name = str(data.get("name") or data.get("id") or base_name).strip()
                                data["name"] = skill_name
                                data["id"] = skill_name
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
        """Instantiates the appropriate executable BaseSkill engine for the given skill ID or name."""
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
        """Saves a skill to its individual YAML file named after the skill name."""
        name = str(skill_data.get("name") or skill_data.get("id") or "").strip()
        if not name:
            name = "Untitled Skill"

        is_valid, err_msg = self.validate_name(name)
        if not is_valid:
            raise ValueError(err_msg)

        # Path Traversal & Injection Security Gate
        raw_tasks = skill_data.get("tasks", [])
        if isinstance(raw_tasks, list):
            for t in raw_tasks:
                if isinstance(t, dict):
                    for act in t.get("actions", []):
                        if isinstance(act, dict) and act.get("action_type") == "TYPE_FILE_PATH":
                            fp = str(act.get("file_path", "") or "")
                            if fp:
                                is_safe, _ = sanitize_safe_path(fp)
                                if not is_safe:
                                    raise ValueError(f"Security error: Invalid path with directory traversal ('..') in action: '{fp}'")

        clean_filename = self.sanitize_name(name)
        skill_data["name"] = name
        skill_data["id"] = name

        os.makedirs(self.skills_dir, exist_ok=True)
        filepath = os.path.join(self.skills_dir, f"{clean_filename}.yaml")
        tmp_filepath = f"{filepath}.tmp_{os.getpid()}"
        try:
            with open(tmp_filepath, "w", encoding="utf-8") as f:
                yaml.dump(skill_data, f, Dumper=_SkillYamlDumper, allow_unicode=True, sort_keys=False)
            os.replace(tmp_filepath, filepath)
        except Exception:
            if os.path.exists(tmp_filepath):
                try:
                    os.remove(tmp_filepath)
                except OSError:
                    pass
            raise

        with self._lock:
            try:
                mtime = os.path.getmtime(filepath)
                self._cache[filepath] = (mtime, skill_data)
            except OSError as e:
                logger.debug("[SkillManager] Could not get mtime for %s: %s", filepath, e)

        logger.info("[SkillManager] Skill '%s' saved to %s", name, filepath)
        return name

    def delete_skill(self, skill_id_or_name: str) -> bool:
        """Deletes a skill's YAML file with retry on Windows file locks."""
        query = str(skill_id_or_name or "").strip()
        clean_name = self.sanitize_name(query)
        query_slug = self.slugify_name(query)
        candidates = [
            os.path.join(self.skills_dir, f"{query}.yaml"),
            os.path.join(self.skills_dir, f"{query}.yml"),
            os.path.join(self.skills_dir, f"{clean_name}.yaml"),
            os.path.join(self.skills_dir, f"{clean_name}.yml"),
            os.path.join(self.skills_dir, f"{query_slug}.yaml"),
            os.path.join(self.skills_dir, f"{query_slug}.yml"),
        ]
        existing = self.get_skill(query)
        if existing and existing.get("name"):
            cand_name = self.sanitize_name(existing["name"])
            candidates.insert(0, os.path.join(self.skills_dir, f"{cand_name}.yaml"))

        deleted = False
        for filepath in set(candidates):
            if os.path.exists(filepath):
                for attempt in range(5):
                    try:
                        os.remove(filepath)
                        deleted = True
                        break
                    except (PermissionError, OSError) as e:
                        if attempt == 4:
                            logger.error("[SkillManager] Failed to delete %s after retries: %s", filepath, e)
                            raise
                        time.sleep(0.05 * (attempt + 1))
                with self._lock:
                    self._cache.pop(filepath, None)
                logger.info("[SkillManager] Skill file '%s' deleted.", filepath)
        return deleted

    def rename_skill(
        self,
        old_name: str,
        new_name: str,
        skill_data: dict[str, Any] | None = None,
        cascade: bool = True,
    ) -> str:
        """Renames a skill and cascades updates to referencing sub-skills, config.yaml, and metadata."""
        old_clean = (old_name or "").strip()
        new_clean = (new_name or "").strip()

        is_valid, err_msg = self.validate_name(new_clean)
        if not is_valid:
            raise ValueError(err_msg)

        if old_clean == new_clean:
            if skill_data:
                return self.save_skill(skill_data)
            return new_clean

        # 1. Load existing skill definition if not provided
        if not skill_data:
            existing = self.get_skill(old_clean)
            if not existing:
                raise FileNotFoundError(f"Skill '{old_clean}' not found.")
            skill_data = dict(existing)

        # 2. Save under new name
        skill_data["name"] = new_clean
        skill_data["id"] = new_clean
        self.save_skill(skill_data)

        # 3. Delete old skill file
        self.delete_skill(old_clean)

        if not cascade:
            return new_clean

        # 4. Cascade updates across all other skills in skills_dir
        for other_skill in self.list_skills():
            if other_skill.get("name") == new_clean:
                continue

            modified = False
            # Check tasks/actions for sub-skill calls
            for task in other_skill.get("tasks", []):
                for act in task.get("actions", []):
                    if act.get("action_type") == "CALL_SKILL":
                        if act.get("skill_id") == old_clean or act.get("skill_name") == old_clean:
                            act["skill_id"] = new_clean
                            act["skill_name"] = new_clean
                            modified = True

            # Check document types export_skill reference
            if isinstance(other_skill.get("document_types"), dict):
                for dt_cfg in other_skill["document_types"].values():
                    if isinstance(dt_cfg, dict) and dt_cfg.get("export_skill") == old_clean:
                        dt_cfg["export_skill"] = new_clean
                        modified = True

            if modified:
                self.save_skill(other_skill)

        # 5. Cascade updates to system config.yaml / DashboardState.config
        try:
            from routes.state import DashboardState

            if DashboardState.config:
                cfg_modified = False
                if getattr(DashboardState.config, "default_export_skill", None) == old_clean:
                    DashboardState.config.default_export_skill = new_clean
                    cfg_modified = True

                if isinstance(DashboardState.config.document_types, dict):
                    for dt_cfg in DashboardState.config.document_types.values():
                        if isinstance(dt_cfg, dict) and dt_cfg.get("export_skill") == old_clean:
                            dt_cfg["export_skill"] = new_clean
                            cfg_modified = True

                if cfg_modified:
                    DashboardState.config.save_to_yaml()
        except Exception as e:
            logger.warning("[SkillManager] Could not cascade skill rename to system config: %s", e)

        # 6. Cascade updates to .meta case files
        try:
            from routes.state import DashboardState

            if DashboardState.config and DashboardState.config.target_base_dir:
                base_dir = DashboardState.config.target_base_dir
                if os.path.exists(base_dir):
                    import json

                    for root, _, files in os.walk(base_dir):
                        for f in files:
                            if f.endswith(".meta"):
                                meta_path = os.path.join(root, f)
                                try:
                                    with open(meta_path, encoding="utf-8") as mf:
                                        meta_data = json.load(mf)

                                    meta_modified = False
                                    executed = meta_data.get("executed_skills", [])
                                    if isinstance(executed, list) and old_clean in executed:
                                        meta_data["executed_skills"] = [
                                            new_clean if x == old_clean else x for x in executed
                                        ]
                                        meta_modified = True

                                    history = meta_data.get("skill_execution_history", {})
                                    if isinstance(history, dict) and old_clean in history:
                                        history[new_clean] = history.pop(old_clean)
                                        meta_modified = True

                                    if meta_modified:
                                        tmp_meta = meta_path + f".tmp_{os.getpid()}"
                                        with open(tmp_meta, "w", encoding="utf-8") as mf:
                                            json.dump(meta_data, mf, indent=2, ensure_ascii=False)
                                        os.replace(tmp_meta, meta_path)
                                except Exception as e:
                                    logger.debug("[SkillManager] Could not update meta file %s: %s", meta_path, e)
        except Exception as e:
            logger.warning("[SkillManager] Could not cascade skill rename to case metadata: %s", e)

        return new_clean

    def duplicate_skill(self, skill_id_or_name: str) -> dict[str, Any] | None:
        """Duplicates an existing skill with a clean unique copy name."""
        original = self.get_skill(skill_id_or_name)
        if not original:
            return None

        orig_name = original.get("name") or skill_id_or_name
        candidate = f"{orig_name} (Copy)"
        counter = 2
        while self.get_skill(candidate) is not None:
            candidate = f"{orig_name} (Copy {counter})"
            counter += 1

        new_data = dict(original)
        new_data["name"] = candidate
        new_data["id"] = candidate
        self.save_skill(new_data)
        return new_data


_GLOBAL_SKILL_MANAGER: SkillManager | None = None
_GLOBAL_SM_LOCK = threading.Lock()


def get_skill_manager(skills_dir: str | None = None) -> SkillManager:
    """Returns a thread-safe singleton SkillManager instance for the active directory."""
    global _GLOBAL_SKILL_MANAGER
    if skills_dir:
        return SkillManager(skills_dir=skills_dir)

    with _GLOBAL_SM_LOCK:
        from routes.state import DashboardState

        base_dir = (
            getattr(DashboardState.config, "base_dir", os.getcwd())
            if DashboardState.config
            else os.getcwd()
        )
        resolved_dir = getattr(
            DashboardState.config,
            "skills_dir",
            os.path.join(base_dir, "settings", "skills"),
        ) if DashboardState.config else os.path.join(base_dir, "settings", "skills")
        resolved_abs = os.path.abspath(resolved_dir)

        if _GLOBAL_SKILL_MANAGER is None or _GLOBAL_SKILL_MANAGER.skills_dir != resolved_abs:
            _GLOBAL_SKILL_MANAGER = SkillManager(skills_dir=resolved_abs)
        return _GLOBAL_SKILL_MANAGER

