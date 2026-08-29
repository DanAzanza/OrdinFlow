"""Central state and service container for the DMS backend.

Encapsulates configuration, processing pipeline, and background jobs in a
clean service interface (`DMSService`) to reduce direct global state.
"""

from __future__ import annotations

import threading
import time
from typing import Any


class DMSService:
    """Service wrapper for DMS runtime components."""

    def __init__(self):
        self.config: Any = None
        self.processor: Any = None
        self._last_heartbeat: float = time.time()
        self._shutdown_event = threading.Event()


# Global service context
dms_service = DMSService()


_STATE_LOCK = threading.Lock()


# Static interception for direct attribute access on DashboardState
class _DashboardStateMeta(type):
    @property
    def config(cls):
        if dms_service.config is None:
            with _STATE_LOCK:
                if dms_service.config is None:
                    from core.config import AppConfig

                    dms_service.config = AppConfig()
        return dms_service.config

    @config.setter
    def config(cls, value):
        with _STATE_LOCK:
            dms_service.config = value

    @property
    def processor(cls):
        with _STATE_LOCK:
            return dms_service.processor

    @processor.setter
    def processor(cls, value):
        with _STATE_LOCK:
            dms_service.processor = value

    @property
    def last_heartbeat(cls):
        with _STATE_LOCK:
            return dms_service._last_heartbeat

    @last_heartbeat.setter
    def last_heartbeat(cls, value):
        with _STATE_LOCK:
            dms_service._last_heartbeat = value

    @property
    def shutdown_event(cls):
        return dms_service._shutdown_event


class DashboardState(metaclass=_DashboardStateMeta):
    pass
