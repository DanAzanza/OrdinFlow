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


class SkillTaskBlockDict(TypedDict, total=False):
    """Declarative task block grouping multiple sequential actions within a Skill."""

    id: str
    title: str
    actions: list[SkillActionDict | dict[str, Any]]


class SkillType(str, Enum):
    IMPORT = "import"
    EXPORT = "export"
    CUSTOM = "custom"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
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
            "context": self.context,
            "progress": self.progress.to_dict() if isinstance(self.progress, TaskProgress) else self.progress,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "result": self.result,
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
