"""Central Skill Execution Queue Orchestrator and Dispatcher."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any

from core.skills.manager import SkillManager
from core.skills.models import SkillTask, SkillType, TaskProgress, TaskStatus

logger = logging.getLogger(__name__)


class SkillQueueManager:
    """Central single-source-of-execution FIFO task queue for all modular skills."""

    def __init__(self, skill_manager: SkillManager | None = None):
        self.skill_manager = skill_manager or SkillManager()
        self.lock = threading.Lock()
        self.items: list[SkillTask] = []
        self.active_task: SkillTask | None = None
        self.is_running = False
        self.is_paused = False
        self._stop_requested = False
        self._pause_event = threading.Event()
        self._pause_event.set()
        self._stop_event = threading.Event()
        self._worker_thread: threading.Thread | None = None
        self._worker_lock = threading.Lock()

        # Auto-repeat configuration (5 minutes default)
        self.auto_repeat_enabled = False
        self.auto_repeat_interval_seconds = 300
        self._last_auto_run_time = 0.0
        self._auto_repeat_thread: threading.Thread | None = None
        self._auto_repeat_stop_event = threading.Event()

        self._state_file = os.path.join(self.skill_manager.skills_dir, "queue_state.json")
        self._load_state()
        self._start_auto_repeat_worker()

    def _load_state(self) -> None:
        """Restores queue tasks and auto-repeat configuration from disk."""
        if not os.path.exists(self._state_file):
            return

        try:
            with open(self._state_file, encoding="utf-8") as f:
                data = json.load(f)

            if isinstance(data, dict):
                raw_items = data.get("items", [])
                self.auto_repeat_enabled = bool(data.get("auto_repeat_enabled", False))
                self.auto_repeat_interval_seconds = int(data.get("auto_repeat_interval_seconds", 300))
            elif isinstance(data, list):
                raw_items = data
            else:
                raw_items = []

            for raw in raw_items:
                task = SkillTask.from_dict(raw)
                # Reset any interrupted running tasks to pending
                if task.status == TaskStatus.RUNNING:
                    task.status = TaskStatus.PENDING
                self.items.append(task)

            logger.info("[SkillQueueManager] Loaded %d task(s) from state file.", len(self.items))
        except Exception as e:
            logger.warning("[SkillQueueManager] Could not load queue state: %s", e)

    def _save_state(self) -> None:
        """Persists queue tasks and settings atomically."""
        try:
            payload = {
                "auto_repeat_enabled": self.auto_repeat_enabled,
                "auto_repeat_interval_seconds": self.auto_repeat_interval_seconds,
                "items": [item.to_dict() for item in self.items],
            }
            tmp_file = self._state_file + ".tmp"
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            os.replace(tmp_file, self._state_file)
        except Exception as e:
            logger.warning("[SkillQueueManager] Could not save queue state: %s", e)

    def _start_auto_repeat_worker(self) -> None:
        """Starts background thread checking for recurring auto-repeat triggers."""
        if self._auto_repeat_thread and self._auto_repeat_thread.is_alive():
            return

        self._auto_repeat_stop_event.clear()
        self._auto_repeat_thread = threading.Thread(
            target=self._auto_repeat_loop,
            daemon=True,
            name="SkillQueueAutoRepeatWorker",
        )
        self._auto_repeat_thread.start()

    def _auto_repeat_loop(self) -> None:
        """Checks periodically if auto-repeat should trigger the queue."""
        while not self._auto_repeat_stop_event.is_set():
            time.sleep(3.0)
            with self.lock:
                if not self.auto_repeat_enabled:
                    continue
                if self.is_running or self.is_paused:
                    continue

                now = time.time()
                if now - self._last_auto_run_time < self.auto_repeat_interval_seconds:
                    continue

                self._last_auto_run_time = now

            # Trigger queue execution
            logger.info("[SkillQueueManager] Auto-repeat trigger firing...")
            self.start_queue(auto_triggered=True)

    def set_auto_repeat(self, enabled: bool, interval_seconds: int = 300) -> dict[str, Any]:
        """Configures or toggles auto-repeat scheduling."""
        with self.lock:
            self.auto_repeat_enabled = enabled
            self.auto_repeat_interval_seconds = max(10, interval_seconds)
            self._save_state()
            logger.info(
                "[SkillQueueManager] Auto-repeat set to enabled=%s, interval=%ds",
                self.auto_repeat_enabled,
                self.auto_repeat_interval_seconds,
            )
            return {
                "auto_repeat_enabled": self.auto_repeat_enabled,
                "auto_repeat_interval_seconds": self.auto_repeat_interval_seconds,
            }

    def add_to_queue(self, skill_id: str, context: dict[str, Any] | None = None) -> SkillTask:
        """Enqueues a skill task and returns the created SkillTask."""
        skill_data = self.skill_manager.get_skill(skill_id)
        skill_name = skill_data.get("name", skill_id) if skill_data else skill_id
        raw_type = skill_data.get("type", "export") if skill_data else "export"
        stype = SkillType(raw_type) if raw_type in [t.value for t in SkillType] else SkillType.EXPORT

        task_id = f"task_{int(time.time() * 1000)}_{len(self.items) + 1}"
        task = SkillTask(
            id=task_id,
            skill_id=skill_id,
            skill_name=skill_name,
            skill_type=stype,
            status=TaskStatus.PENDING,
            context=dict(context or {}),
            progress=TaskProgress(message="Waiting in queue..."),
        )

        with self.lock:
            self.items.append(task)
            self._save_state()

        logger.info("[SkillQueueManager] Added task '%s' (Skill '%s') to queue.", task_id, skill_name)
        return task

    def remove_from_queue(self, task_id: str) -> bool:
        """Removes a task by ID from the queue."""
        with self.lock:
            original_len = len(self.items)
            self.items = [i for i in self.items if i.id != task_id]
            if len(self.items) != original_len:
                self._save_state()
                return True
        return False

    def clear_queue(self) -> None:
        """Clears all pending items from the queue."""
        with self.lock:
            if self.is_running and self.active_task:
                self.items = [self.active_task]
            else:
                self.items.clear()
            self._save_state()
        logger.info("[SkillQueueManager] Queue cleared.")

    def reorder_queue(self, item_ids: list[str]) -> bool:
        """Reorders the queue according to the provided list of task IDs."""
        with self.lock:
            id_map = {item.id: item for item in self.items}
            new_items = []
            for tid in item_ids:
                if tid in id_map:
                    new_items.append(id_map[tid])
            # Append remaining items
            for item in self.items:
                if item not in new_items:
                    new_items.append(item)

            self.items = new_items
            self._save_state()
            return True

    def get_queue_state(self) -> dict[str, Any]:
        """Returns the live snapshot of queue execution status."""
        with self.lock:
            return {
                "is_running": self.is_running,
                "is_paused": self.is_paused,
                "auto_repeat_enabled": self.auto_repeat_enabled,
                "auto_repeat_interval_seconds": self.auto_repeat_interval_seconds,
                "active_item": self.active_task.to_dict() if self.active_task else None,
                "items": [item.to_dict() for item in self.items],
            }

    def start_queue(self, auto_triggered: bool = False) -> bool:
        """Starts worker loop processing queued items sequentially."""
        if self._worker_thread is not None and self._worker_thread.is_alive() and not self.is_running:
            self._worker_thread.join(timeout=1.5)

        with self.lock:
            if self.is_running or (self._worker_thread is not None and self._worker_thread.is_alive()):
                logger.info("[SkillQueueManager] Queue is already running.")
                return True

            if not self.items:
                logger.debug("[SkillQueueManager] Queue is empty. Nothing to execute.")
                return False

            # If no pending tasks remain, reset completed tasks to pending for a fresh run
            has_pending = any(i.status == TaskStatus.PENDING for i in self.items)
            if not has_pending:
                for i in self.items:
                    if i.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                        i.status = TaskStatus.PENDING
                        i.progress = TaskProgress(message="Waiting in queue...")

            # Check again
            if not any(i.status == TaskStatus.PENDING for i in self.items):
                logger.info("[SkillQueueManager] No executable tasks found in queue.")
                return False

            self.is_running = True
            self.is_paused = False
            self._stop_requested = False
            self._stop_event.clear()
            self._pause_event.set()

        from routes.state import DashboardState

        if DashboardState.processor and hasattr(DashboardState.processor, "resume"):
            DashboardState.processor.resume()

        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            daemon=True,
            name="SkillQueueWorkerThread",
        )
        self._worker_thread.start()
        logger.info("[SkillQueueManager] Queue execution started.")
        return True

    def pause_queue(self) -> bool:
        """Pauses queue execution immediately (blocking active engine at next file/step)."""
        with self.lock:
            if not self.is_running:
                return False
            self.is_paused = True
            self._pause_event.clear()
            self._save_state()

        from routes.state import DashboardState

        if DashboardState.processor and hasattr(DashboardState.processor, "pause"):
            DashboardState.processor.pause()

        logger.info("[SkillQueueManager] Queue paused.")
        return True

    def resume_queue(self) -> bool:
        """Resumes paused queue execution."""
        with self.lock:
            if not self.is_running and not self.is_paused:
                return False
            self.is_paused = False
            self._pause_event.set()
            self._save_state()

        from routes.state import DashboardState

        if DashboardState.processor and hasattr(DashboardState.processor, "resume"):
            DashboardState.processor.resume()

        with self.lock:
            if not self.is_running and not (self._worker_thread is not None and self._worker_thread.is_alive()):
                self.is_running = True
                self._stop_requested = False
                self._stop_event.clear()
                self._pause_event.set()
                self._worker_thread = threading.Thread(
                    target=self._worker_loop,
                    daemon=True,
                    name="SkillQueueWorkerThread",
                )
                self._worker_thread.start()
        logger.info("[SkillQueueManager] Queue resumed.")
        return True

    def stop_queue(self) -> None:
        """Stops queue execution immediately."""
        with self.lock:
            self._stop_requested = True
            self._stop_event.set()
            self._pause_event.set()
            self.is_running = False
            self.is_paused = False
            if self.active_task:
                self.active_task.status = TaskStatus.CANCELLED
                self.active_task.finished_at = time.time()
                self.active_task = None
            if not (self._worker_thread is not None and self._worker_thread.is_alive()):
                self._stop_requested = False
                self._stop_event.clear()
            self._save_state()

        from routes.state import DashboardState

        if DashboardState.processor and hasattr(DashboardState.processor, "resume"):
            DashboardState.processor.resume()

        logger.info("[SkillQueueManager] Queue stopped.")

    def wait_if_paused(self) -> bool:
        """Blocks while queue is paused. Returns False if queue was stopped."""
        while self.is_paused and not self._stop_event.is_set():
            self._pause_event.wait(timeout=0.2)
        return not self._stop_event.is_set()

    @property
    def is_stopped(self) -> bool:
        """Returns True if stop was requested during an active execution."""
        if not self.is_running and not (self._worker_thread is not None and self._worker_thread.is_alive()):
            return False
        return self._stop_event.is_set() or self._stop_requested

    def _worker_loop(self) -> None:
        """Internal sequential execution loop."""
        if not self._worker_lock.acquire(blocking=False):
            logger.warning("[SkillQueueManager] Worker loop already running in another thread. Exiting duplicate.")
            return

        try:
            while True:
                # Handle Pause: wait until resumed or stopped
                while True:
                    with self.lock:
                        if self._stop_requested:
                            break
                        if not self.is_paused:
                            break
                    time.sleep(0.3)

                current_task: SkillTask | None = None
                with self.lock:
                    if self._stop_requested:
                        break

                    # Find next pending task
                    for item in self.items:
                        if item.status == TaskStatus.PENDING:
                            current_task = item
                            break

                    if not current_task:
                        logger.info("[SkillQueueManager] All queued tasks completed.")
                        break

                    current_task.status = TaskStatus.RUNNING
                    current_task.started_at = time.time()
                    current_task.progress = TaskProgress(message="Starting execution...")
                    self.active_task = current_task
                    self._save_state()

                # Execute Task outside the lock
                success = False
                error_msg: str | None = None
                result_data: dict[str, Any] = {}

                try:
                    from routes.state import DashboardState

                    extractor = DashboardState.processor.llm_extractor if DashboardState.processor else None
                    processor = DashboardState.processor
                    engine = self.skill_manager.get_skill_engine(
                        current_task.skill_id,
                        vision_extractor=extractor,
                        processor=processor,
                    )
                    if not engine:
                        raise RuntimeError(f"Skill engine for '{current_task.skill_id}' not found.")

                    def progress_reporter(prog: TaskProgress) -> None:
                        with self.lock:
                            if current_task is not None:
                                current_task.progress = prog

                    res = engine.execute(current_task, reporter=progress_reporter)
                    success = res.success
                    result_data = res.data
                    error_msg = res.error
                except Exception as e:
                    logger.error("[SkillQueueManager] Error executing task %s: %s", current_task.id, e, exc_info=True)
                    error_msg = str(e)
                    success = False

                with self.lock:
                    current_task.finished_at = time.time()
                    if self._stop_requested:
                        current_task.status = TaskStatus.CANCELLED
                        current_task.progress = TaskProgress(percent=100.0, message="Stopped by user.")
                    else:
                        current_task.status = TaskStatus.COMPLETED if success else TaskStatus.FAILED
                        current_task.result = result_data
                        current_task.error = error_msg
                        if success:
                            current_task.progress = TaskProgress(percent=100.0, message="Completed successfully.")
                        else:
                            current_task.progress = TaskProgress(percent=100.0, message=f"Failed: {error_msg}")

                    self.active_task = None
                    self._save_state()
                    if self._stop_requested:
                        break

        finally:
            with self.lock:
                self.is_running = False
                self._stop_requested = False
                self._stop_event.clear()
                self.active_task = None
                self._save_state()
            self._worker_lock.release()
            logger.info("[SkillQueueManager] Queue worker thread finished.")


_SKILL_QUEUE_MANAGER: SkillQueueManager | None = None


def get_skill_queue_manager(skill_manager: SkillManager | None = None) -> SkillQueueManager:
    """Returns the singleton instance of SkillQueueManager."""
    global _SKILL_QUEUE_MANAGER
    if _SKILL_QUEUE_MANAGER is None:
        _SKILL_QUEUE_MANAGER = SkillQueueManager(skill_manager=skill_manager)
    elif skill_manager is not None:
        _SKILL_QUEUE_MANAGER.skill_manager = skill_manager
    return _SKILL_QUEUE_MANAGER
