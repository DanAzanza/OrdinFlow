import logging
import os

from core.config import AppConfig
from core.utils import is_missing_value

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

    def find_existing_folder_by_keywords(
        self, base_dir: str, keywords: list
    ) -> str | None:
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

    def cleanup_empty_directories(self, directory: str):
        """Recursively deletes empty folders upwards, stopping at watch_dir."""
        try:
            watch_dir_abs = os.path.abspath(self.config.watch_dir)
            dir_path_abs = os.path.abspath(directory)

            while (
                dir_path_abs
                and dir_path_abs != watch_dir_abs
                and dir_path_abs.startswith(watch_dir_abs)
            ):
                if not os.path.exists(dir_path_abs):
                    break
                if not os.listdir(dir_path_abs):
                    try:
                        os.rmdir(dir_path_abs)
                        logger.info(f"[+] Deleted empty folder: {dir_path_abs}")
                    except OSError:
                        # Under Windows, folders are often temporarily locked by Explorer or file watchers.
                        logger.info(
                            f"[*] Empty folder could not be cleaned up (locked): {dir_path_abs}"
                        )
                        break
                    dir_path_abs = os.path.dirname(dir_path_abs)
                else:
                    break
        except (OSError, ValueError) as e:
            logger.debug(f"Error in cleanup_empty_directories: {e}")
