"""
OrdinFlow — Web Dashboard Backend
"""

import logging
import subprocess
import sys
import threading
import time
import webbrowser

import secrets
from flask import Flask, jsonify, request
from werkzeug.serving import make_server

from core.config import AppConfig
from core.processor import DocumentProcessor
from routes.api import api_bp
from routes.state import DMSService, DashboardState, get_current_dms
from routes.ui import ui_bp


def create_app(dms: DMSService | None = None) -> Flask:
    """Application factory for OrdinFlow web dashboard."""
    flask_app = Flask(__name__, template_folder="templates", static_folder="static")
    flask_app.extensions["dms"] = dms or get_current_dms()
    flask_app.register_blueprint(api_bp)
    flask_app.register_blueprint(ui_bp)

    active_dms = flask_app.extensions["dms"]
    if not active_dms.session_token:
        active_dms.session_token = secrets.token_urlsafe(32)

    @flask_app.before_request
    def check_host_header():
        raw_host = request.host.split(":")[0].strip().lower()
        allowed_hosts = {"127.0.0.1", "localhost", "::1", "[::1]"}
        if raw_host not in allowed_hosts:
            return jsonify({"error": "Forbidden: Invalid Host header"}), 403
        return None

    @flask_app.after_request
    def set_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; "
            "frame-src 'self' blob:; object-src 'self' blob:; frame-ancestors 'self'; base-uri 'self'",
        )
        if not request.path.startswith("/static/"):
            response.headers["Cache-Control"] = "private, no-store"
        return response

    return flask_app


app = create_app()


logger = logging.getLogger(__name__)


def heartbeat_monitor() -> None:
    while not DashboardState.shutdown_event.is_set():
        time.sleep(5)
        # If skill queue is actively running in the background, keep heartbeat alive
        try:
            from core.skills.queue import get_skill_queue_manager

            qm = get_skill_queue_manager()
            if qm.is_running and not qm.is_paused:
                DashboardState.last_heartbeat = time.time()
                continue
        except Exception as e:
            logger.debug("[Dashboard] Queue manager check failed: %s", e)

        # If background document processing exists, keep heartbeat alive
        try:
            if DashboardState.processor:
                with DashboardState.processor.processing_lock:
                    if len(DashboardState.processor.processing_files) > 0:
                        DashboardState.last_heartbeat = time.time()
                        continue
        except Exception as e:
            logger.debug("[Dashboard] Processor check failed: %s", e)

        # 300 seconds (5 minutes) inactivity timeout when browser tab is closed and no tasks are running
        if time.time() - DashboardState.last_heartbeat > 300:
            logger.info(
                "[*] Dashboard closed (no heartbeat for 300s and all processing idle). Terminating application..."
            )
            DashboardState.shutdown_event.set()
            break


def open_browser(port: int, bootstrap_nonce: str | None = None) -> None:
    if bootstrap_nonce:
        url = f"http://127.0.0.1:{port}/auth/bootstrap?nonce={bootstrap_nonce}"
    else:
        url = f"http://127.0.0.1:{port}/"

    # Wait until Flask server responds with HTTP 200 on zero-PII readiness endpoint (max 20 seconds)
    import http.client

    server_ready = False
    for _ in range(40):
        time.sleep(0.5)
        try:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
            conn.request("GET", "/api/health")
            resp = conn.getresponse()
            if resp.status == 200:
                server_ready = True
                conn.close()
                break
            conn.close()
        except (OSError, TimeoutError):
            pass

    if not server_ready:
        logger.warning(f"[Dashboard] Server on port {port} did not respond within 20s; skipping browser launch.")
        return

    opened = False
    if sys.platform == "win32":
        try:
            subprocess.Popen(["cmd", "/c", "start", "", url], shell=False)
            logger.info(f"[Dashboard] Browser opened via cmd start (http://127.0.0.1:{port}/)")
            opened = True
        except (OSError, RuntimeError, subprocess.SubprocessError) as e:
            logger.error(f"[Dashboard] Error in cmd start: {e}")

    if not opened:
        try:
            if webbrowser.open(url, new=2, autoraise=True):
                logger.info(f"[Dashboard] Browser opened via webbrowser.open(http://127.0.0.1:{port}/)")
                opened = True
        except (OSError, RuntimeError, webbrowser.Error) as e:
            logger.error(f"[Dashboard] Error in webbrowser.open: {e}")


def start_dashboard(
    processor: DocumentProcessor | None,
    config: AppConfig,
) -> None:
    if processor:
        DashboardState.processor = processor
    DashboardState.config = config
    DashboardState.last_heartbeat = time.time()
    if not DashboardState.session_token:
        DashboardState.session_token = secrets.token_urlsafe(32)

    # Suppress Werkzeug logs in console
    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    try:
        # Bind socket FIRST before starting heartbeat or launching browser
        server = make_server("127.0.0.1", config.dashboard_port, app, threaded=True)
    except (OSError, RuntimeError, ValueError) as e:
        logger.error(f"[!] Error binding Dashboard on port {config.dashboard_port}: {e}", exc_info=True)
        DashboardState.shutdown_event.set()
        return

    # Start Heartbeat Monitor
    threading.Thread(target=heartbeat_monitor, daemon=True).start()

    # Mint single-use bootstrap nonce and open browser in separate thread
    bootstrap_nonce = DashboardState.issue_bootstrap_token()
    threading.Thread(target=open_browser, args=(config.dashboard_port, bootstrap_nonce), daemon=True).start()

    try:
        logger.info(f"[Dashboard] WSGI Server started at http://127.0.0.1:{config.dashboard_port}/")
        server.serve_forever()
    except (OSError, RuntimeError, ValueError) as e:
        logger.error(f"[!] Error running Dashboard server: {e}", exc_info=True)
