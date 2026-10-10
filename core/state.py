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
