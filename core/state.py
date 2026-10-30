"""Central state and service container for OrdinFlow runtime components.

Encapsulates configuration, processing pipeline, and background queue management
in a decoupled service interface (`DMSService`) and `DashboardState`.
"""

from __future__ import annotations

from collections.abc import Callable
import queue
import secrets
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
        self.bootstrap_token: str | None = None

    def issue_bootstrap_token(self) -> str:
        """Generates and stores a single-use cryptographic bootstrap nonce."""
        with _STATE_LOCK:
            nonce = secrets.token_urlsafe(32)
            self.bootstrap_token = nonce
            return nonce

    def consume_bootstrap_token(self, candidate: str | None) -> bool:
        """Validates and atomically invalidates the single-use bootstrap nonce."""
        if not candidate or not isinstance(candidate, str):
            return False
        with _STATE_LOCK:
            expected = self.bootstrap_token
            if not expected or not isinstance(expected, str):
                return False
            if secrets.compare_digest(candidate, expected):
                self.bootstrap_token = None
                return True
            return False


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
_CONTEXT_RESOLVER: Callable[[], DMSService | None] | None = None


def register_dms_context_resolver(resolver: Callable[[], DMSService | None] | None) -> None:
    """Registers an external context resolver (e.g. Flask app context) without coupling core to web frameworks."""
    global _CONTEXT_RESOLVER
    with _STATE_LOCK:
        _CONTEXT_RESOLVER = resolver


def get_current_dms() -> DMSService:
    """Retrieve the active DMSService instance.

    Checks the registered context resolver first if available; falls back to the process-level default.
    """
    resolver = _CONTEXT_RESOLVER
    if resolver is not None:
        resolved = resolver()
        if resolved is not None and isinstance(resolved, DMSService):
            return resolved
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

    @property
    def bootstrap_token(cls) -> str | None:
        dms = get_current_dms()
        with _STATE_LOCK:
            return dms.bootstrap_token

    @bootstrap_token.setter
    def bootstrap_token(cls, value: str | None) -> None:
        dms = get_current_dms()
        with _STATE_LOCK:
            dms.bootstrap_token = value

    def issue_bootstrap_token(cls) -> str:
        return get_current_dms().issue_bootstrap_token()

    def consume_bootstrap_token(cls, candidate: str | None) -> bool:
        return get_current_dms().consume_bootstrap_token(candidate)


class DashboardState(metaclass=_DashboardStateMeta):
    pass
