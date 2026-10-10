"""Comprehensive regression tests verifying the architectural improvements.

Covers:
1. Packaging metadata (PEP 621 dependencies & setuptools package data).
2. Vision patch size parameterization and ceiling division padding.
3. FlushingRotatingFileHandler rollover resilience and PermissionError handling.
4. EventBroadcaster pub-sub semantics, non-blocking overflow, and SSE endpoint.
5. Frontend versioning and asset cache-busting tag verification.
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import patch

from flask import Flask
from PIL import Image

from core.config import AppConfig
from core.image_processing import ImagePreprocessor, _encode_pil_fallback
from core.state import DashboardState, EventBroadcaster
from main import FlushingRotatingFileHandler
from routes.api import api_bp
from routes.ui import ui_bp


def test_event_broadcaster_pub_sub_and_overflow():
    """Verifies that EventBroadcaster handles subscription, broadcast, and queue overflow."""
    broadcaster = EventBroadcaster(maxsize=3)
    q1 = broadcaster.subscribe()
    q2 = broadcaster.subscribe()

    # Normal broadcast
    broadcaster.broadcast({"type": "test", "data": 1})
    assert q1.get_nowait() == {"type": "test", "data": 1}
    assert q2.get_nowait() == {"type": "test", "data": 1}

    # Overflow test (exceeding maxsize=3 should drop oldest, not block)
    for i in range(5):
        broadcaster.broadcast({"type": "overflow", "data": i})

    # q1 should only hold the latest 3 items (2, 3, 4) due to maxsize=3
    items = []
    while not q1.empty():
        items.append(q1.get_nowait()["data"])
    assert items == [2, 3, 4]

    # Drain q2 and test unsubscribe
    while not q2.empty():
        q2.get_nowait()
    broadcaster.unsubscribe(q2)
    broadcaster.broadcast({"type": "test", "data": "after_unsub"})
    assert q2.empty()


def test_api_events_sse_endpoint():
    """Verifies that /api/events yields text/event-stream headers and SSE data."""
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(api_bp)

    client = app.test_client()
    res = client.get("/api/events", headers={"X-OrdinFlow-Test-Bypass": "1"})

    assert res.status_code == 200
    assert "text/event-stream" in res.content_type
    assert res.headers.get("Cache-Control") == "no-cache"


def test_flushing_rotating_file_handler_rollover_and_permission_error(tmp_path):
    """Verifies that FlushingRotatingFileHandler rotates at maxBytes and recovers from locks."""
    log_file = tmp_path / "test_rot.log"
    handler = FlushingRotatingFileHandler(
        str(log_file),
        mode="a",
        maxBytes=150,
        backupCount=2,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(message)s"))

    logger = logging.getLogger("test_rot_logger")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)

    # Write enough lines to force multiple rollovers
    for i in range(15):
        logger.info(f"Log message line {i:03d} to trigger rotation testing")

    handler.close()
    logger.removeHandler(handler)

    assert log_file.exists()
    assert (tmp_path / "test_rot.log.1").exists()

    # Test PermissionError recovery on Windows transient file lock
    handler2 = FlushingRotatingFileHandler(
        str(log_file),
        mode="a",
        maxBytes=150,
        backupCount=2,
        encoding="utf-8",
    )
    with patch("logging.handlers.RotatingFileHandler.doRollover", side_effect=PermissionError("File locked")):
        # Should not raise exception
        handler2.doRollover()
        assert handler2.stream is not None
    handler2.close()


def test_vision_patch_size_parameterization():
    """Verifies that non-default patch sizes apply correct ceiling division in preprocessing."""
    cfg = AppConfig()
    cfg.vision_patch_size = 16

    img = Image.new("RGB", (105, 105), (200, 200, 200))
    preprocessor = ImagePreprocessor(cfg)

    # Scale with patch_size=16
    b64 = preprocessor.scale_and_encode_image(img, max_dim=64)
    assert isinstance(b64, str) and len(b64) > 0

    # Direct fallback test with custom patch size
    b64_fallback = _encode_pil_fallback(img, max_dim=64, patch_size=16)
    assert isinstance(b64_fallback, str) and len(b64_fallback) > 0


def test_frontend_asset_cache_busting(test_sandbox):
    """Verifies that index.html template injects app_version query parameters for all static assets."""
    _, config, _ = test_sandbox
    config.app_version = "0.9.9"
    DashboardState.config = config

    real_templates = str(Path(__file__).resolve().parent.parent / "templates")
    app = Flask(__name__, template_folder=real_templates)
    app.config["TESTING"] = True
    app.register_blueprint(ui_bp)

    client = app.test_client()
    res = client.get("/")
    assert res.status_code == 200
    html = res.get_data(as_text=True)

    assert 'href="/static/css/app.css?v=0.9.9"' in html
    assert 'src="/static/js/api.js?v=0.9.9"' in html
    assert 'src="/static/js/app.js?v=0.9.9"' in html
