"""Base abstract interface for all OrdinFlow skills."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from core.skills.models import SkillTask, SkillType, TaskProgress, TaskResult


class BaseSkill(ABC):
    """Abstract base class defining the contract for all modular skills."""

    def __init__(self, definition: dict[str, Any]):
        self.definition = definition
        self.id = str(definition.get("id", ""))
        self.name = str(definition.get("name", self.id))
        raw_type = definition.get("type", "export")
        self.skill_type = SkillType(raw_type) if raw_type in [t.value for t in SkillType] else SkillType.EXPORT
        self.enabled = bool(definition.get("enabled", True))
        self.description = str(definition.get("description", ""))

    def wait_for_queue(
        self,
        reporter: Callable[[TaskProgress], None] | None = None,
        paused_msg: str = "Execution paused...",
    ) -> bool:
        """Blocks while SkillQueueManager is paused. Returns False if execution was stopped."""
        try:
            from core.skills.queue import get_skill_queue_manager

            qm = get_skill_queue_manager()
            if not qm.is_running and not qm.is_paused:
                return True
            if qm.is_stopped:
                return False
            was_paused = False
            while qm.is_paused and not qm.is_stopped:
                if not was_paused and reporter:
                    reporter(TaskProgress(message=f"⏸️ {paused_msg}"))
                    was_paused = True
                qm.wait_if_paused()
            return not qm.is_stopped
        except Exception:
            return True

    @abstractmethod
    def execute(
        self,
        task: SkillTask,
        reporter: Callable[[TaskProgress], None] | None = None,
    ) -> TaskResult:
        """Executes the skill action for the given task and reports progress."""
        raise NotImplementedError
