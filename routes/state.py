"""Central state and service container for the DMS backend.

Encapsulates configuration, processing pipeline, and background jobs in a
clean service interface (`DMSService`) to reduce direct global state.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from core.jobs import job_queue


class DMSService:
    """Service wrapper for DMS runtime components."""

    def __init__(self):
        self._lock = threading.Lock()
        self.config: Any = None
        self.processor: Any = None
        self.file_queue: Any = None
        self._last_heartbeat: float = time.time()
        self._shutdown_event = threading.Event()

    def is_ready(self) -> bool:
        with self._lock:
            return self.processor is not None and self.config is not None

    def heartbeat(self):
        with self._lock:
            self._last_heartbeat = time.time()

    def submit_background_job(self, name: str, func, *args, **kwargs) -> str:
        """Submits a job to the sequential FIFO queue."""
        return job_queue.submit(name, func, *args, **kwargs)


# Global service context
dms_service = DMSService()


def get_dms_service() -> DMSService:
    """Returns the central DMS service container instance."""
    return dms_service


# Static interception for direct attribute access on DashboardState
class _DashboardStateMeta(type):
    @property
    def config(cls):
        if dms_service.config is None:
            from core.config import AppConfig

            dms_service.config = AppConfig()
        return dms_service.config

    @config.setter
    def config(cls, value):
        dms_service.config = value

    @property
    def processor(cls):
        return dms_service.processor

    @processor.setter
    def processor(cls, value):
        dms_service.processor = value

    @property
    def file_queue(cls):
        return dms_service.file_queue

    @file_queue.setter
    def file_queue(cls, value):
        dms_service.file_queue = value

    @property
    def last_heartbeat(cls):
        return dms_service._last_heartbeat

    @last_heartbeat.setter
    def last_heartbeat(cls, value):
        dms_service._last_heartbeat = value

    @property
    def shutdown_event(cls):
        return dms_service._shutdown_event


class DashboardState(metaclass=_DashboardStateMeta):
    pass
