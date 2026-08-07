"""Lightweight asynchronous background job queue for the DMS.

Executes resource-intensive tasks (such as OCR and vision-LLM processing)
sequentially (FIFO, max_workers=1) in a background thread.
This prevents:
1. The GPU / LLM process from being overloaded by parallel requests.
2. Dependent documents ('dependent: true' such as notes/photos) from inheriting the wrong context,
   since chronological order is strictly preserved.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
import uuid
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class JobStatus:
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    ERROR = "ERROR"


_TERMINAL_STATUSES: frozenset = frozenset({JobStatus.DONE, JobStatus.ERROR})


class JobTask:
    def __init__(
        self,
        job_id: str,
        name: str,
        func: Callable[..., Any],
        args: tuple = (),
        kwargs: dict | None = None,
    ):
        self.job_id = job_id
        self.name = name
        self.func = func
        self.args = args
        self.kwargs = kwargs or {}
        self.status = JobStatus.PENDING
        self.result: Any = None
        self.error: str | None = None
        self.created_at = time.time()
        self.started_at: float | None = None
        self.finished_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "name": self.name,
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


class BackgroundJobQueue:
    """Sequential FIFO queue for background jobs."""

    def __init__(self):
        self._queue: queue.Queue[JobTask] = queue.Queue()
        self._jobs: dict[str, JobTask] = {}
        self._lock = threading.Lock()
        self._worker_thread: threading.Thread | None = None
        self._shutdown = False

    def start(self):
        """Starts the background worker thread (if not already active)."""
        if self._worker_thread and self._worker_thread.is_alive():
            return
        self._shutdown = False
        self._worker_thread = threading.Thread(
            target=self._worker_loop, name="DMS-JobWorker", daemon=True
        )
        self._worker_thread.start()
        logger.info("[JobQueue] Background worker started (FIFO, sequential).")

    def stop(self):
        """Stops the worker thread after completing the current job."""
        self._shutdown = True
        # Wake up queue if empty
        self._queue.put(None)  # type: ignore

    def submit(self, name: str, func: Callable[..., Any], *args, **kwargs) -> str:
        """Submits a new job into the queue."""
        job_id = f"job-{uuid.uuid4().hex[:8]}"
        task = JobTask(job_id, name, func, args, kwargs)
        with self._lock:
            # Evict completed jobs when the list grows too large
            if len(self._jobs) > 200:
                completed = [
                    (jid, t) for jid, t in self._jobs.items()
                    if t.status in _TERMINAL_STATUSES
                ]
                if len(completed) > 100:
                    completed.sort(key=lambda x: x[1].created_at)
                    for jid, _ in completed[:50]:
                        del self._jobs[jid]
            self._jobs[job_id] = task
        self.start()
        self._queue.put(task)
        logger.info(f"[JobQueue] Job eingereiht: {job_id} ({name})")
        return job_id

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            task = self._jobs.get(job_id)
            return task.to_dict() if task else None

    def list_jobs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            sorted_jobs = sorted(
                self._jobs.values(), key=lambda j: j.created_at, reverse=True
            )
            return [j.to_dict() for j in sorted_jobs[:limit]]

    def _worker_loop(self):
        while not self._shutdown:
            try:
                task = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue
            if task is None:
                break

            task.status = JobStatus.RUNNING
            task.started_at = time.time()
            logger.info(f"[JobQueue] Starting job: {task.job_id} ({task.name})")

            try:
                task.result = task.func(*task.args, **task.kwargs)
                task.status = JobStatus.DONE
            except Exception as e:
                logger.exception(f"[JobQueue] Error in job {task.job_id}: {e}")
                task.error = str(e)
                task.status = JobStatus.ERROR
            finally:
                task.finished_at = time.time()
                self._queue.task_done()


# Global JobQueue service
job_queue = BackgroundJobQueue()
