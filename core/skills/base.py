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

    def validate(self) -> tuple[bool, str | None]:
        """Validates the skill definition for required fields and configuration integrity."""
        if not self.id:
            return False, "Skill missing 'id'"
        if not self.name:
            return False, "Skill missing 'name'"
        return True, None

    @abstractmethod
    def execute(
        self,
        task: SkillTask,
        reporter: Callable[[TaskProgress], None] | None = None,
    ) -> TaskResult:
        """Executes the skill action for the given task and reports progress."""
        raise NotImplementedError

    def cancel(self, task: SkillTask) -> None:
        """Optional hook to clean up resources if task is cancelled during execution."""
        pass
