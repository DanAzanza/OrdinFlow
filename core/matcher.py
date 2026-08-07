import logging
import os
from difflib import SequenceMatcher

from core.config import AppConfig
from core.utils import is_missing_value

logger = logging.getLogger(__name__)


def _clean_name(name: str) -> str:
    if not name:
        return ""
    name = name.replace(".", " ")
    # Removes hyphens for matching
    return name.lower().replace("-", " ").strip()


def _split_person_name(person_raw: str) -> tuple[str, str]:
    # Cleans square brackets and extracts first/last name
    person_raw = person_raw.strip("[]").strip()
    if "," in person_raw:
        parts = person_raw.split(",", 1)
        return parts[0].strip(), parts[1].strip()
    return person_raw, ""


def _names_match(n1: str, v1: str, n2: str, v2: str, threshold: float) -> bool:
    n1_c, v1_c = _clean_name(n1), _clean_name(v1)
    n2_c, v2_c = _clean_name(n2), _clean_name(v2)

    # 1. When both first and last names are available separately
    if v1_c and v2_c:
        ratio_n = SequenceMatcher(None, n1_c, n2_c).ratio()
        ratio_v = SequenceMatcher(None, v1_c, v2_c).ratio()

        # Stricter thresholds for very short names (e.g. Hans vs. Jens, or May vs. Roy)
        th_n = 0.90 if len(n1_c) <= 4 or len(n2_c) <= 4 else threshold
        th_v = 0.90 if len(v1_c) <= 4 or len(v2_c) <= 4 else threshold

        return ratio_n >= th_n and ratio_v >= th_v

    # 2. Fallback for incomplete data (e.g. one name missing): word-by-word comparison
    w1 = sorted((n1_c + " " + v1_c).split())
    w2 = sorted((n2_c + " " + v2_c).split())

    if len(w1) != len(w2):
        # If word counts differ, compare full strings via SequenceMatcher
        full1 = " ".join(w1)
        full2 = " ".join(w2)
        return SequenceMatcher(None, full1, full2).ratio() >= threshold

    # Pairwise comparison of sorted words
    for word1, word2 in zip(w1, w2):
        w_th = 0.90 if len(word1) <= 4 or len(word2) <= 4 else threshold
        if SequenceMatcher(None, word1, word2).ratio() < w_th:
            return False

    return True


class FileSystemRouter:
    """Encapsulates filesystem logic."""

    def __init__(self, config: AppConfig):
        self.config = config

    def find_existing_person_folder(
        self, base_dir: str, last_name: str, first_name: str
    ) -> str | None:
        """Searches base directory for a matching folder using fuzzy/keyword matching."""
        if not os.path.exists(base_dir) or not last_name or not first_name:
            return None

        clean_last = _clean_name(last_name)
        clean_first = _clean_name(first_name)
        if not clean_last or not clean_first:
            return None

        for item in os.listdir(base_dir):
            item_path = os.path.join(base_dir, item)
            if os.path.isdir(item_path):
                item_clean = _clean_name(item)
                if clean_last in item_clean and clean_first in item_clean:
                    return item_path
        return None

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
