import logging
import os
from dataclasses import asdict, dataclass, field
from typing import Any

import yaml

logger = logging.getLogger(__name__)


@dataclass
class AppConfig:
    """Central configuration class (app settings)."""

    # LLM backend settings
    llm_backend: str = (
        "llama_cpp"  # 'llama_cpp' (direct) | 'server' (standalone llama-server)
    )
    server_url: str = "http://127.0.0.1:8080/v1"
    server_api_key: str = "not-needed"
    llm_model_path: str = "models/Qwen3-VL-8B-Instruct-UD-Q4_K_XL.gguf"
    mmproj_path: str = "models/mmproj-BF16.gguf"

    # Preprocessing settings
    max_dimension: int = 1280
    crop_padding: int = 5
    white_border: int = 8
    contrast_limit: float = 1.0

    # Processing settings
    delay_seconds: float = 6.0

    folder_match_threshold: float = 0.90

    # Dashboard settings
    dashboard_port: int = 8080
    crop_edge_threshold: int = 45
    min_contour_area: int = 10

    classify_dimension: int = 1280
    vision_api_timeout: float = 120.0
    vision_api_retries: int = 3

    # Path settings (calculated via setup_paths)
    base_dir: str = "."
    watch_dir: str = ""
    target_base_dir: str = ""

    # Dynamic prompt & routing document types
    document_types: dict[str, dict[str, Any]] = field(default_factory=dict)
    vision_base_rules: str = ""
    signature_base_rules: str = ""
    folder_delimiter: str = "__"
    folder_structure: list[str] = field(default_factory=list)
    match_folder_by: list[str] = field(default_factory=list)

    # Feature toggles used in tests and processing flow
    split_multi_documents: bool = False
    save_empty_pages: bool = False

    def __post_init__(self):
        if not isinstance(self.document_types, dict):
            self.document_types = {}
        if not isinstance(self.folder_structure, list):
            self.folder_structure = []
        if not isinstance(self.match_folder_by, list):
            self.match_folder_by = []

    @staticmethod
    def _safe_doc_filename(doc_name: str) -> str:
        safe = (
            doc_name.lower()
            .replace(" ", "_")
            .replace("ä", "ae")
            .replace("ö", "oe")
            .replace("ü", "ue")
            .replace("ß", "ss")
        )
        safe = "".join(c for c in safe if c.isalnum() or c in ["_", "-"])
        return f"{safe}.yaml"

    def _resolve_path(self, filepath: str) -> str:
        """Resolves a relative path against base_dir, or returns absolute paths unchanged."""
        base = os.path.abspath(self.base_dir)
        return os.path.join(base, filepath) if not os.path.isabs(filepath) else filepath

    def load_from_yaml(
        self,
        filepath: str = "settings/config.yaml",
        import_skill_id: str = "import_eingang",
    ):
        full_path = self._resolve_path(filepath)

        # 1. Load main configuration (system settings)
        if os.path.exists(full_path):
            with open(full_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            for k, v in data.items():
                if k != "document_types":
                    setattr(self, k, v)
        else:
            # If settings/config.yaml does not exist -> create directory & default file
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            self.save_to_yaml(full_path, import_skill_id=import_skill_id)

        # 2. Load document types for specified import skill
        self.document_types = self.get_document_types_for_skill(
            import_skill_id, settings_dir=os.path.dirname(full_path)
        )

    def get_document_types_for_skill(
        self, import_skill_id: str = "import_eingang", settings_dir: str | None = None
    ) -> dict[str, dict[str, Any]]:
        """Loads document types directly from settings/skills/<import_skill_id>.yaml."""
        if settings_dir is None:
            settings_dir = self._resolve_path("settings")

        skills_dir = os.path.join(settings_dir, "skills")
        os.makedirs(skills_dir, exist_ok=True)
        skill_file = os.path.join(skills_dir, f"{import_skill_id}.yaml")
        if not os.path.exists(skill_file):
            skill_file = os.path.join(skills_dir, f"{import_skill_id}.yml")

        loaded_doc_types: dict[str, dict[str, Any]] = {}

        if os.path.exists(skill_file):
            try:
                with open(skill_file, encoding="utf-8") as f:
                    skill_data = yaml.safe_load(f) or {}
                loaded_doc_types = skill_data.get("document_types") or {}
            except (OSError, yaml.YAMLError) as e:
                logger.error("Error loading skill file %s: %s", skill_file, e)

        return dict(loaded_doc_types)

    def save_to_yaml(
        self,
        filepath: str = "settings/config.yaml",
        import_skill_id: str = "import_eingang",
    ):
        full_path = self._resolve_path(filepath)
        settings_dir = os.path.dirname(full_path)

        os.makedirs(settings_dir, exist_ok=True)

        # 1. Save system configuration to settings/config.yaml (without document_types)
        cfg_dict = {k: v for k, v in asdict(self).items() if k != "document_types"}
        with open(full_path, "w", encoding="utf-8") as f:
            yaml.dump(
                cfg_dict,
                f,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            )

        # 2. Save document types directly into the import skill file settings/skills/<import_skill_id>.yaml
        self.save_document_types_for_skill(
            import_skill_id=import_skill_id,
            document_types=self.document_types,
            settings_dir=settings_dir,
        )

    def save_document_types_for_skill(
        self,
        import_skill_id: str,
        document_types: dict[str, dict[str, Any]] | None,
        settings_dir: str | None = None,
    ):
        """Saves document types directly into the skill YAML file settings/skills/<import_skill_id>.yaml."""
        if settings_dir is None:
            settings_dir = self._resolve_path("settings")

        skills_dir = os.path.join(settings_dir, "skills")
        os.makedirs(skills_dir, exist_ok=True)
        skill_file = os.path.join(skills_dir, f"{import_skill_id}.yaml")

        skill_data = {}
        if os.path.exists(skill_file):
            try:
                with open(skill_file, encoding="utf-8") as f:
                    skill_data = yaml.safe_load(f) or {}
            except (OSError, yaml.YAMLError):
                skill_data = {}

        clean_doc_types: dict[str, dict[str, Any]] = {}
        if document_types:
            for d_name, d_val in document_types.items():
                if d_name not in ["UNBEKANNT", "LEER"]:
                    clean_doc_types[d_name] = d_val

        skill_data["id"] = import_skill_id
        if "type" not in skill_data:
            skill_data["type"] = "import"
        if "name" not in skill_data:
            skill_data["name"] = "Inbox Folder Import"

        skill_data["document_types"] = clean_doc_types

        with open(skill_file, "w", encoding="utf-8") as f:
            yaml.dump(
                skill_data,
                f,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            )

    def setup_paths(self):
        base_path = os.path.abspath(self.base_dir)
        if not self.watch_dir:
            self.watch_dir = os.path.join(base_path, "Inbox")
        if not self.target_base_dir:
            self.target_base_dir = os.path.join(base_path, "Cases")

        # Convert relative LLM path to absolute (base_dir + relative path)
        for attr_name in ("llm_model_path", "mmproj_path"):
            current = getattr(self, attr_name, None) or ""
            if current and not os.path.isabs(current):
                setattr(
                    self,
                    attr_name,
                    os.path.normpath(os.path.join(base_path, current)),
                )

        os.makedirs(self.watch_dir, exist_ok=True)
        os.makedirs(self.target_base_dir, exist_ok=True)
