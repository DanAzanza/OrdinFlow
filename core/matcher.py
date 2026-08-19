import logging
import os

from core.config import AppConfig
from core.utils import cleanup_empty_folder, is_missing_value

logger = logging.getLogger(__name__)


def _clean_name(name: str) -> str:
    if not name:
        return ""
    name = name.replace(".", " ")
    # Removes hyphens for matching
    return name.lower().replace("-", " ").strip()


class FileSystemRouter:
    """Encapsulates filesystem logic."""

    def __init__(self, config: AppConfig):
        self.config = config

    def find_existing_folder_by_keywords(self, base_dir: str, keywords: list) -> str | None:
        """Searches base directory for a matching folder based on a list of keywords."""
        if not os.path.exists(base_dir) or not keywords:
            return None
        valid_kw = [_clean_name(k) for k in keywords if k and not is_missing_value(k)]
        valid_kw = [k for k in valid_kw if k]
        if not valid_kw:
            return None

        for item in os.listdir(base_dir):
            item_path = os.path.join(base_dir, item)
            if os.path.isdir(item_path):
                item_clean = _clean_name(item)
                if all(kw in item_clean for kw in valid_kw):
                    return item_path
        return None

    def cleanup_empty_directories(self, directory: str) -> None:
        """Recursively deletes empty folders upwards, stopping at watch_dir."""
        cleanup_empty_folder(directory, stop_at=self.config.watch_dir)
