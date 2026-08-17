"""Skill Queue Manager for mutually exclusive, sequential skill execution."""

import json
import logging
import os
import threading
import time
from collections.abc import Callable
from typing import Any

from core.skills.executor import SkillExecutor
from core.skills.manager import SkillManager

logger = logging.getLogger(__name__)


class SkillQueueManager:
    """Manages a single-threaded queue for executing Import and Export skills sequentially with disk persistence."""

    def __init__(self, skill_manager: SkillManager):
        self.skill_manager = skill_manager
        self.queue_file = os.path.join(self.skill_manager.skills_dir, "queue_state.json")
        self.lock = threading.Lock()
        self.queue: list[dict[str, Any]] = []
        self.is_running = False
        self._stop_requested = False
        self._worker_thread: threading.Thread | None = None
        self._import_handler: Callable[[dict[str, Any]], bool] | None = None
        self._export_handler: Callable[[dict[str, Any]], bool] | None = None

        self._load_from_disk()

    def _load_from_disk(self) -> None:
        """Loads persisted queue items from disk if available."""
        if not os.path.isfile(self.queue_file):
            return
        try:
            with open(self.queue_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                has_running = False
                for item in data:
                    if isinstance(item, dict) and item.get("status") == "running":
                        item["status"] = "pending"
                        has_running = True
                self.queue = data
                if has_running:
                    self._save_to_disk()
                logger.info(
                    "[SkillQueueManager] Loaded %d persisted queue items from disk.",
                    len(self.queue),
                )
        except (OSError, json.JSONDecodeError, UnicodeError) as e:
            logger.warning("[SkillQueueManager] Could not load queue_state.json: %s", e)

    def _save_to_disk(self) -> None:
        """Safely persists queue items to disk atomically."""
        try:
            os.makedirs(os.path.dirname(self.queue_file), exist_ok=True)
            temp_path = self.queue_file + ".tmp"
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(self.queue, f, indent=2, ensure_ascii=False)
            if os.path.exists(self.queue_file):
                os.replace(temp_path, self.queue_file)
            else:
                os.rename(temp_path, self.queue_file)
        except OSError as e:
            logger.warning("[SkillQueueManager] Could not save queue_state.json: %s", e)

    def set_handlers(
        self,
        import_handler: Callable[[dict[str, Any]], bool] | None = None,
        export_handler: Callable[[dict[str, Any]], bool] | None = None,
    ) -> None:
        """Configures external runtime handlers for import and export actions (preserves layer separation)."""
        if import_handler is not None:
            self._import_handler = import_handler
        if export_handler is not None:
            self._export_handler = export_handler

    def get_queue_state(self) -> dict[str, Any]:
        """Returns current items and running state."""
        with self.lock:
            active_item = None
            for item in self.queue:
                if item.get("status") == "running":
                    active_item = dict(item)
                    break
            return {
                "is_running": self.is_running,
                "active_item": active_item,
                "items": [dict(item) for item in self.queue],
            }

    def add_to_queue(
        self, skill_id: str, context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Adds a skill to the queue and persists state."""
        skill = self.skill_manager.get_skill(skill_id)
        skill_name = skill.get("name", skill_id) if skill else skill_id
        skill_type = skill.get("type", "export") if skill else "export"

        item_id = f"q_{int(time.time() * 1000)}_{len(self.queue) + 1}"
        item = {
            "id": item_id,
            "skill_id": skill_id,
            "skill_name": skill_name,
            "skill_type": skill_type,
            "status": "pending",
            "context": context or {},
            "created_at": time.time(),
        }
        with self.lock:
            self.queue.append(item)
            self._save_to_disk()
            logger.info(
                "[SkillQueueManager] Added skill '%s' (%s) to queue as %s",
                skill_name,
                skill_type,
                item_id,
            )
        return item

    def remove_from_queue(self, queue_id: str) -> bool:
        """Removes an item from the queue and persists state."""
        with self.lock:
            for idx, item in enumerate(self.queue):
                if item["id"] == queue_id:
                    if self.is_running and item.get("status") == "running":
                        logger.warning(
                            "[SkillQueueManager] Cannot remove actively executing item %s while queue is running",
                            queue_id,
                        )
                        return False
                    self.queue.pop(idx)
                    self._save_to_disk()
                    logger.info(
                        "[SkillQueueManager] Removed item %s from queue", queue_id
                    )
                    return True
        return False

    def clear_queue(self) -> bool:
        """Clears all non-running items from the queue and persists state."""
        with self.lock:
            if self.is_running:
                self.queue = [item for item in self.queue if item.get("status") == "running"]
            else:
                self.queue = []
            self._save_to_disk()
            logger.info("[SkillQueueManager] Queue cleared.")
            return True

    def reorder_queue(self, item_ids: list[str]) -> bool:
        """Reorders pending items in the queue according to the provided ID list."""
        with self.lock:
            id_to_item = {item["id"]: item for item in self.queue}
            new_queue = []
            # Keep running item at the front if present
            for item in self.queue:
                if item["status"] == "running":
                    new_queue.append(item)

            for i_id in item_ids:
                if i_id in id_to_item and id_to_item[i_id]["status"] != "running":
                    new_queue.append(id_to_item[i_id])

            # Append any unmentioned pending items
            seen = {it["id"] for it in new_queue}
            for item in self.queue:
                if item["id"] not in seen:
                    new_queue.append(item)

            self.queue = new_queue
            self._save_to_disk()
            logger.info(
                "[SkillQueueManager] Queue reordered: %s",
                [it["id"] for it in self.queue],
            )
            return True

    def start_queue(self, force_reset_if_no_pending: bool = True) -> bool:
        """Starts processing the queue in a background worker thread."""
        with self.lock:
            if self.is_running:
                logger.info("[SkillQueueManager] Queue is already running.")
                return True

            # If all items are completed or failed, reset them to pending so start runs them
            has_pending = any(item.get("status") == "pending" for item in self.queue)
            if not has_pending and self.queue and force_reset_if_no_pending:
                for item in self.queue:
                    item["status"] = "pending"
                self._save_to_disk()
                logger.info(
                    "[SkillQueueManager] Reset %d items to pending for execution.",
                    len(self.queue),
                )

            self.is_running = True
            self._stop_requested = False
            self._worker_thread = threading.Thread(
                target=self._worker_loop, daemon=True
            )
            self._worker_thread.start()
            logger.info("[SkillQueueManager] Queue started.")
            return True

    def stop_queue(self) -> bool:
        """Stops processing the queue after the currently executing item finishes."""
        with self.lock:
            self._stop_requested = True
            self.is_running = False
            for item in self.queue:
                if item.get("status") == "running":
                    item["status"] = "pending"
            self._save_to_disk()
            logger.info("[SkillQueueManager] Queue stop requested.")
            return True

    def _worker_loop(self):
        """Sequential execution loop for queued skills."""
        while not self._stop_requested:
            target_item = None
            with self.lock:
                for item in self.queue:
                    if item["status"] == "pending":
                        target_item = item
                        target_item["status"] = "running"
                        self._save_to_disk()
                        break

            if not target_item:
                logger.info("[SkillQueueManager] No more pending items in queue.")
                with self.lock:
                    self.is_running = False
                break

            logger.info(
                "[SkillQueueManager] Executing queued item %s (Skill: %s)",
                target_item["id"],
                target_item["skill_id"],
            )
            success = False

            try:
                if target_item["skill_type"] == "import":
                    if self._import_handler:
                        success = bool(self._import_handler(target_item))
                    else:
                        logger.warning(
                            "[SkillQueueManager] No import handler configured for item %s.",
                            target_item["id"],
                        )
                        success = True
                else:
                    if self._export_handler:
                        success = bool(self._export_handler(target_item))
                    else:
                        executor = SkillExecutor(self.skill_manager)
                        context = target_item.get("context", {})
                        folder_path = context.get("folder_path")
                        if folder_path and isinstance(folder_path, str):
                            success = executor.execute_skill_for_folder(
                                target_item["skill_id"], folder_path, context
                            )
                        else:
                            success = executor.execute_skill(
                                target_item["skill_id"], context
                            )

            except Exception as e:
                logger.error(
                    "[SkillQueueManager] Error executing queued item %s: %s",
                    target_item["id"],
                    e,
                    exc_info=True,
                )
                success = False

            with self.lock:
                target_item["status"] = "completed" if success else "failed"
                self._save_to_disk()

            time.sleep(0.5)

        with self.lock:
            self.is_running = False
        logger.info("[SkillQueueManager] Worker loop ended.")


_SKILL_QUEUE_MANAGER = None


def get_skill_queue_manager(
    skill_manager: SkillManager | None = None,
) -> SkillQueueManager:
    global _SKILL_QUEUE_MANAGER
    if _SKILL_QUEUE_MANAGER is None:
        if skill_manager is None:
            skills_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                "settings",
                "skills",
            )
            skill_manager = SkillManager(skills_dir=skills_dir)
        _SKILL_QUEUE_MANAGER = SkillQueueManager(skill_manager)
    return _SKILL_QUEUE_MANAGER
