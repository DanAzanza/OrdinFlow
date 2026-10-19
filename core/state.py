"""Central state and service container for OrdinFlow runtime components.

Encapsulates configuration, processing pipeline, and background queue management
in a decoupled service interface (`DMSService`) and `DashboardState`.
"""

from __future__ import annotations

import queue
import threading
import time
from typing import Any


class EventBroadcaster:
    """Thread-safe pub-sub event broadcaster for Server-Sent Events (SSE).

    Uses bounded queues with drop-oldest overflow to guarantee zero blocking
    on worker threads. Never calls Python logging directly.
    """

    def __init__(self, maxsize: int = 200) -> None:
        self._subscribers: set[queue.Queue[dict[str, Any]]] = set()
        self._lock = threading.Lock()
        self._maxsize = maxsize

    def subscribe(self) -> queue.Queue[dict[str, Any]]:
        q: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=self._maxsize)
        with self._lock:
            self._subscribers.add(q)
        return q

    def unsubscribe(self, q: queue.Queue[dict[str, Any]]) -> None:
        with self._lock:
            self._subscribers.discard(q)

    def broadcast(self, event: dict[str, Any]) -> None:
        with self._lock:
            subscribers = list(self._subscribers)
        for q in subscribers:
            try:
                q.put_nowait(event)
            except queue.Full:
                try:
                    q.get_nowait()
                except queue.Empty:
                    pass
                try:
                    q.put_nowait(event)
                except queue.Full:
                    pass


event_broadcaster = EventBroadcaster()


class DMSService:
    """Service wrapper for OrdinFlow runtime components."""

    def __init__(self) -> None:
        self.config: Any = None
        self.processor: Any = None
        self._last_heartbeat: float = time.time()
        self._shutdown_event = threading.Event()
        self.session_token: str | None = None


def create_dms_service(config: Any = None, processor: Any = None) -> DMSService:
    """Factory creating an isolated DMSService instance."""
    service = DMSService()
    if config is not None:
        service.config = config
    if processor is not None:
        service.processor = processor
    return service


# Global service context default
dms_service = DMSService()

_STATE_LOCK = threading.Lock()


def get_current_dms() -> DMSService:
    """Retrieve the active DMSService instance.

    Checks active Flask application context first if available and configured
    via current_app.extensions['dms']; falls back to the process-level default.
    """
    try:
        from flask import current_app, has_app_context

        if has_app_context():
            ext_dms = current_app.extensions.get("dms")
            if ext_dms is not None and isinstance(ext_dms, DMSService):
                return ext_dms
    except ImportError:
        pass
    return dms_service


def set_current_dms(service: DMSService) -> None:
    """Set the process-level default DMSService instance."""
    global dms_service
    with _STATE_LOCK:
        dms_service = service


# Static interception for direct attribute access on DashboardState
class _DashboardStateMeta(type):
    @property
    def config(cls) -> Any:
        dms = get_current_dms()
        if dms.config is None:
            with _STATE_LOCK:
                if dms.config is None:
                    from core.config import AppConfig

                    dms.config = AppConfig()
        return dms.config

    @config.setter
    def config(cls, value: Any) -> None:
        dms = get_current_dms()
        with _STATE_LOCK:
            dms.config = value

    @property
    def processor(cls) -> Any:
        dms = get_current_dms()
        with _STATE_LOCK:
            return dms.processor

    @processor.setter
    def processor(cls, value: Any) -> None:
        dms = get_current_dms()
        with _STATE_LOCK:
            dms.processor = value

    @property
    def last_heartbeat(cls) -> float:
        dms = get_current_dms()
        with _STATE_LOCK:
            return dms._last_heartbeat

    @last_heartbeat.setter
    def last_heartbeat(cls, value: float) -> None:
        dms = get_current_dms()
        with _STATE_LOCK:
            dms._last_heartbeat = value

    @property
    def shutdown_event(cls) -> threading.Event:
        return get_current_dms()._shutdown_event

    @property
    def session_token(cls) -> str | None:
        dms = get_current_dms()
        with _STATE_LOCK:
            return dms.session_token

    @session_token.setter
    def session_token(cls, value: str | None) -> None:
        dms = get_current_dms()
        with _STATE_LOCK:
            dms.session_token = value


class DashboardState(metaclass=_DashboardStateMeta):
    pass
