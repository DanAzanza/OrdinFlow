"""Lightweight background job queue stub for backward compatibility with /api/jobs.

Active background processing is performed directly by DocumentProcessor and SkillQueueManager.
This stub satisfies API endpoints and frontend pollers without spawning unused worker threads.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class JobStatus:
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    ERROR = "ERROR"


class BackgroundJobQueue:
    """Stub queue preserving API interface for frontend polling without allocating worker threads."""

    def list_jobs(self, limit: int = 50) -> list[dict[str, Any]]:
        return []

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        return None

    def submit(self, name: str, func: Any, *args: Any, **kwargs: Any) -> str:
        return ""

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass


# Global JobQueue service stub
job_queue = BackgroundJobQueue()
