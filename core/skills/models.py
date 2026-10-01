"""Domain models and schemas for the OrdinFlow Skills System."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TypedDict


class SkillActionDict(TypedDict, total=False):
    """Declarative action definition inside a skill task."""

    id: str
    action_type: str
    description: str
    locator: dict[str, Any]
    text: str
    file_path: str
    window_title: str
    press_enter: bool
    skill_id: str
    keys: list[str] | str
    duration_s: float
    delay_ms: int
    max_retries: int
    retry_delay_s: float
    on_success: str
    on_failure: str
    on_failure_action: str
    on_failure_skill: str
    is_secret: bool
    timeout_s: float
    poll_interval_s: float
    launch_skill_id: str
    maximize_window: bool
    recover_hung_process: bool
    condition: dict[str, Any] | str | bool
    then_actions: list[SkillActionDict | dict[str, Any]]
    else_actions: list[SkillActionDict | dict[str, Any]]
    on_error: dict[str, Any] | str
    extract_to_var: str
    provider: str
    variable: str
    expected: Any
    pattern: str


class SkillTaskBlockDict(TypedDict, total=False):
    """Declarative task block grouping multiple sequential actions within a Skill."""

    id: str
    title: str
    actions: list[SkillActionDict | dict[str, Any]]


class SkillType(str, Enum):
    IMPORT = "import"
    EXPORT = "export"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskProgress:
    current: int = 0
    total: int = 0
    message: str = ""
    percent: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "current": self.current,
            "total": self.total,
            "message": self.message,
            "percent": round(self.percent, 1),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> TaskProgress:
        if not data or not isinstance(data, dict):
            return cls()
        return cls(
            current=int(data.get("current", 0)),
            total=int(data.get("total", 0)),
            message=str(data.get("message", "")),
            percent=float(data.get("percent", 0.0)),
        )


@dataclass
class TaskResult:
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
        }


@dataclass
class SkillTask:
    id: str
    skill_id: str
    skill_name: str
    skill_type: SkillType | str
    status: TaskStatus | str = TaskStatus.PENDING
    context: dict[str, Any] = field(default_factory=dict)
    progress: TaskProgress = field(default_factory=TaskProgress)
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    result: dict[str, Any] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "skill_id": self.skill_id,
            "skill_name": self.skill_name,
            "skill_type": str(self.skill_type.value if isinstance(self.skill_type, SkillType) else self.skill_type),
            "status": str(self.status.value if isinstance(self.status, TaskStatus) else self.status),
            "context": dict(self.context) if isinstance(self.context, dict) else {},
            "progress": self.progress.to_dict() if isinstance(self.progress, TaskProgress) else self.progress,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "result": dict(self.result) if isinstance(self.result, dict) else self.result,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SkillTask:
        raw_status = data.get("status", TaskStatus.PENDING.value)
        status = TaskStatus(raw_status) if raw_status in [s.value for s in TaskStatus] else TaskStatus.PENDING

        raw_type = data.get("skill_type", SkillType.EXPORT.value)
        skill_type = SkillType(raw_type) if raw_type in [t.value for t in SkillType] else SkillType.EXPORT

        return cls(
            id=str(data.get("id", "")),
            skill_id=str(data.get("skill_id", "")),
            skill_name=str(data.get("skill_name", "")),
            skill_type=skill_type,
            status=status,
            context=dict(data.get("context") or {}),
            progress=TaskProgress.from_dict(data.get("progress")),
            created_at=float(data.get("created_at", time.time())),
            started_at=float(data["started_at"]) if data.get("started_at") else None,
            finished_at=float(data["finished_at"]) if data.get("finished_at") else None,
            result=dict(data["result"]) if isinstance(data.get("result"), dict) else None,
            error=str(data["error"]) if data.get("error") else None,
        )


@dataclass
class QueueSnapshot:
    """Explicit, typed view of the queue execution state."""

    is_running: bool = False
    is_paused: bool = False
    auto_repeat_enabled: bool = False
    auto_repeat_interval_seconds: int = 300
    active_item: SkillTask | None = None
    items: list[SkillTask] = field(default_factory=list)

    @property
    def active_task(self) -> SkillTask | None:
        """Alias for active_item for parity with SkillQueueManager.active_task."""
        return self.active_item

    @classmethod
    def from_manager(cls, manager: Any) -> QueueSnapshot:
        lock = getattr(manager, "lock", None)
        if lock is not None and hasattr(lock, "__enter__"):
            with lock:
                return cls._build_from_manager(manager)
        return cls._build_from_manager(manager)

    @classmethod
    def _build_from_manager(cls, manager: Any) -> QueueSnapshot:
        raw_active: SkillTask | None = getattr(manager, "active_task", None) or getattr(manager, "active_item", None)
        raw_items: list[SkillTask] = list(getattr(manager, "items", []))

        # Deep-isolate tasks to prevent mutation races across threads
        cloned_active = SkillTask.from_dict(raw_active.to_dict()) if raw_active else None
        cloned_items = [SkillTask.from_dict(t.to_dict()) for t in raw_items]

        return cls(
            is_running=bool(getattr(manager, "is_running", False)),
            is_paused=bool(getattr(manager, "is_paused", False)),
            auto_repeat_enabled=bool(getattr(manager, "auto_repeat_enabled", False)),
            auto_repeat_interval_seconds=int(getattr(manager, "auto_repeat_interval_seconds", 300)),
            active_item=cloned_active,
            items=cloned_items,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_running": self.is_running,
            "is_paused": self.is_paused,
            "auto_repeat_enabled": self.auto_repeat_enabled,
            "auto_repeat_interval_seconds": self.auto_repeat_interval_seconds,
            "active_item": self.active_item.to_dict() if self.active_item else None,
            "items": [item.to_dict() for item in self.items],
        }
