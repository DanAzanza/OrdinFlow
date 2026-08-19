"""Central application configuration module."""

from __future__ import annotations

import logging
import os
from dataclasses import asdict, dataclass, field
from typing import Any

import yaml

logger = logging.getLogger(__name__)


@dataclass
class AppConfig:
    """Central configuration class (system and processing settings)."""

    # LLM backend settings
    llm_backend: str = "llama_cpp"  # 'llama_cpp' (direct) | 'server' (standalone llama-server)
    server_url: str = "http://127.0.0.1:8080/v1"
    server_api_key: str = "not-needed"
    llm_model_path: str = "models/Qwen3-VL-8B-Instruct-UD-Q4_K_XL.gguf"
    mmproj_path: str = "models/mmproj-BF16.gguf"

    # Preprocessing settings
    max_dimension: int = 1008
    crop_padding: int = 5
    white_border: int = 8
    contrast_limit: float = 1.0

    # Dashboard settings
    dashboard_port: int = 8080
    crop_edge_threshold: int = 45
    min_contour_area: int = 10

    classify_dimension: int = 1008
    tier1_dimension: int = 1260
    tier2_dimension: int = 1512
    tier3_dimension: int = 1764
    vision_api_timeout: float = 120.0
    vision_api_retries: int = 3

    # Path settings (calculated via setup_paths)
    base_dir: str = "."
    watch_dir: str = ""
    target_base_dir: str = ""

    # Dynamic prompt & routing document types
    document_types: dict[str, dict[str, Any]] = field(default_factory=dict)
    folder_delimiter: str = "__"
    folder_structure: list[str] = field(default_factory=list)
    match_folder_by: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not isinstance(self.document_types, dict):
            self.document_types = {}
        if not isinstance(self.folder_structure, list):
            self.folder_structure = []
        if not isinstance(self.match_folder_by, list):
            self.match_folder_by = []

    def _resolve_path(self, filepath: str) -> str:
        """Resolves a relative path against base_dir, or returns absolute paths unchanged."""
        base = os.path.abspath(self.base_dir)
        return os.path.join(base, filepath) if not os.path.isabs(filepath) else filepath

    def load_from_yaml(self, filepath: str = "settings/config.yaml") -> None:
        """Loads system configuration from YAML and syncs document types from SkillManager."""
        full_path = self._resolve_path(filepath)

        # 1. Load main configuration (system settings)
        if os.path.exists(full_path):
            with open(full_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            for k, v in data.items():
                if k != "document_types" and hasattr(self, k):
                    setattr(self, k, v)
        else:
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            self.save_to_yaml(full_path)

        # 2. Sync document types from default import skill if available
        from core.skills.manager import SkillManager

        skills_dir = self._resolve_path(os.path.join("settings", "skills"))
        mgr = SkillManager(skills_dir=skills_dir)
        default_skill = mgr.get_default_import_skill()
        if default_skill and isinstance(default_skill.get("document_types"), dict):
            self.document_types = dict(default_skill["document_types"])

    def save_to_yaml(self, filepath: str = "settings/config.yaml") -> None:
        """Saves system configuration (excluding document_types) to YAML and syncs document_types to default import skill."""
        full_path = self._resolve_path(filepath)
        settings_dir = os.path.dirname(full_path)
        os.makedirs(settings_dir, exist_ok=True)

        cfg_dict = {k: v for k, v in asdict(self).items() if k != "document_types"}
        with open(full_path, "w", encoding="utf-8") as f:
            yaml.dump(
                cfg_dict,
                f,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            )

        if self.document_types:
            from core.skills.manager import SkillManager

            skills_dir = self._resolve_path(os.path.join("settings", "skills"))
            mgr = SkillManager(skills_dir=skills_dir)
            default_skill = mgr.get_default_import_skill()
            if default_skill:
                mgr.save_document_types_for_skill(default_skill["id"], self.document_types)
            else:
                skill_data = {
                    "id": "import_eingang",
                    "name": "Inbox Folder Import",
                    "type": "import",
                    "document_types": self.document_types,
                }
                mgr.save_skill(skill_data)

    def setup_paths(self) -> None:
        """Initializes and creates watch and target directories."""
        base_path = os.path.abspath(self.base_dir)
        if not self.watch_dir:
            self.watch_dir = os.path.join(base_path, "Inbox")
        if not self.target_base_dir:
            self.target_base_dir = os.path.join(base_path, "Cases")

        os.makedirs(self.watch_dir, exist_ok=True)
        os.makedirs(self.target_base_dir, exist_ok=True)
