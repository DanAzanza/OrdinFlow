"""
OrdinFlow — Web Dashboard Backend
"""

import logging
import os
import queue
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser

from flask import Flask
from werkzeug.serving import make_server

from core.config import AppConfig
from core.processor import DocumentProcessor
from routes.api import api_bp
from routes.state import DashboardState
from routes.ui import ui_bp

app = Flask(__name__, template_folder="templates", static_folder="static")
app.register_blueprint(api_bp)
app.register_blueprint(ui_bp)

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
        except Exception:
            pass

        # If background jobs exist (e.g. split/OCR jobs in job_queue), keep heartbeat alive
        try:
            from core.jobs import get_job_queue

            jq = get_job_queue()
            if any(j.status in ("running", "pending") for j in jq.get_all_jobs()):
                DashboardState.last_heartbeat = time.time()
                continue
        except Exception:
            pass

        # If background document processing or queued files exist, keep heartbeat alive
        try:
            if DashboardState.processor:
                with DashboardState.processor.processing_lock:
                    if len(DashboardState.processor.processing_files) > 0:
                        DashboardState.last_heartbeat = time.time()
                        continue
            if DashboardState.file_queue is not None and not DashboardState.file_queue.empty():
                DashboardState.last_heartbeat = time.time()
                continue
        except Exception:
            pass

        # 300 seconds (5 minutes) inactivity timeout when browser tab is closed and no tasks are running
        if time.time() - DashboardState.last_heartbeat > 300:
            logger.info(
                "[*] Dashboard closed (no heartbeat for 300s and all processing idle). Terminating application..."
            )
            DashboardState.shutdown_event.set()
            time.sleep(2)
            os._exit(0)


def open_browser(port: int) -> None:
    url = f"http://127.0.0.1:{port}/"

    # Wait until Flask server responds with HTTP 200 (max 20 seconds)
    server_ready = False
    for _ in range(40):
        time.sleep(0.5)
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=1) as resp:
                if resp.status == 200:
                    server_ready = True
                    break
        except (urllib.error.URLError, TimeoutError, OSError):
            pass

    if not server_ready:
        logger.warning(f"[Dashboard] Server on port {port} did not respond within 20s.")

    opened = False
    if sys.platform == "win32":
        try:
            subprocess.Popen(f'cmd /c start "" "{url}"', shell=True)
            logger.info(f"[Dashboard] Browser opened via cmd start ({url})")
            opened = True
        except (OSError, RuntimeError, subprocess.SubprocessError) as e:
            logger.error(f"[Dashboard] Error in cmd start: {e}")

    if not opened:
        try:
            if webbrowser.open(url, new=2, autoraise=True):
                logger.info(f"[Dashboard] Browser opened via webbrowser.open({url})")
                opened = True
        except (OSError, RuntimeError, webbrowser.Error) as e:
            logger.error(f"[Dashboard] Error in webbrowser.open: {e}")

    if not opened and hasattr(os, "startfile"):
        try:
            os.startfile(url)
            logger.info(f"[Dashboard] Browser opened via os.startfile({url})")
            opened = True
        except (OSError, RuntimeError) as e:
            logger.error(f"[Dashboard] Error in os.startfile: {e}")


def start_dashboard(
    processor: DocumentProcessor | None,
    file_queue: queue.Queue | None,
    config: AppConfig,
) -> None:
    if processor:
        DashboardState.processor = processor
    DashboardState.file_queue = file_queue
    DashboardState.config = config
    DashboardState.last_heartbeat = time.time()

    # Start Heartbeat Monitor
    threading.Thread(target=heartbeat_monitor, daemon=True).start()

    # Open browser in separate thread
    threading.Thread(target=open_browser, args=(config.dashboard_port,), daemon=True).start()

    # Suppress Werkzeug logs in console
    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    try:
        logger.info(f"[Dashboard] WSGI Server started at http://127.0.0.1:{config.dashboard_port}/")
        server = make_server("127.0.0.1", config.dashboard_port, app, threaded=True)
        server.serve_forever()
    except (OSError, RuntimeError, ValueError) as e:
        logger.error(f"[!] Error starting Dashboard: {e}", exc_info=True)
