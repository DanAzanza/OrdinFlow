"""Central state and service container for OrdinFlow runtime components.

Encapsulates configuration, processing pipeline, and background queue management
in a decoupled service interface (`DMSService`) and `DashboardState`.
"""

from __future__ import annotations

import threading
import time
from typing import Any


class DMSService:
    """Service wrapper for OrdinFlow runtime components."""

    def __init__(self) -> None:
        self.config: Any = None
        self.processor: Any = None
        self._last_heartbeat: float = time.time()
        self._shutdown_event = threading.Event()
        self.session_token: str | None = None


# Global service context
dms_service = DMSService()

_STATE_LOCK = threading.Lock()


# Static interception for direct attribute access on DashboardState
class _DashboardStateMeta(type):
    @property
    def config(cls) -> Any:
        if dms_service.config is None:
            with _STATE_LOCK:
                if dms_service.config is None:
                    from core.config import AppConfig

                    dms_service.config = AppConfig()
        return dms_service.config

    @config.setter
    def config(cls, value: Any) -> None:
        with _STATE_LOCK:
            dms_service.config = value

    @property
    def processor(cls) -> Any:
        with _STATE_LOCK:
            return dms_service.processor

    @processor.setter
    def processor(cls, value: Any) -> None:
        with _STATE_LOCK:
            dms_service.processor = value

    @property
    def last_heartbeat(cls) -> float:
        with _STATE_LOCK:
            return dms_service._last_heartbeat

    @last_heartbeat.setter
    def last_heartbeat(cls, value: float) -> None:
        with _STATE_LOCK:
            dms_service._last_heartbeat = value

    @property
    def shutdown_event(cls) -> threading.Event:
        return dms_service._shutdown_event

    @property
    def session_token(cls) -> str | None:
        with _STATE_LOCK:
            return dms_service.session_token

    @session_token.setter
    def session_token(cls, value: str | None) -> None:
        with _STATE_LOCK:
            dms_service.session_token = value


class DashboardState(metaclass=_DashboardStateMeta):
    pass
