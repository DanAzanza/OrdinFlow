import argparse
import logging
import os
import subprocess
import sys
import threading
import time
import urllib.request
from urllib.error import URLError

logger = logging.getLogger(__name__)

try:
    _base_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, _base_dir)
    _crash_log = os.path.join(_base_dir, "crash.log")
    _log_f = open(_crash_log, "a", encoding="utf-8", buffering=1)
    if sys.stderr is None:
        sys.stderr = _log_f
    if sys.stdout is None:
        sys.stdout = _log_f
except OSError:
    pass

from core.config import AppConfig
from core.processor import DocumentProcessor
from core.skills.queue import get_skill_queue_manager
from core.utils import memory_log_handler

ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}


class FlushingFileHandler(logging.FileHandler):
    """FileHandler that flushes after every emit to prevent stale disk logs."""

    def emit(self, record):
        super().emit(record)
        self.flush()


class SafeStreamHandler(logging.StreamHandler):
    """StreamHandler that catches BrokenPipeError and handles errors when stdout is detached or closed."""

    def emit(self, record):
        try:
            if self.stream and not getattr(self.stream, "closed", False):
                super().emit(record)
                self.flush()
        except (BrokenPipeError, OSError, ValueError):
            pass


def setup_logging():
    log_format = "%(asctime)s [%(levelname)s] %(message)s"
    formatter = logging.Formatter(log_format)

    file_handler = FlushingFileHandler("main.log", mode="a", encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    stream_handler = SafeStreamHandler(sys.stdout)
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    root.addHandler(file_handler)
    root.addHandler(stream_handler)
    root.addHandler(memory_log_handler)

    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def parse_args():
    parser = argparse.ArgumentParser(description="OrdinFlow - Autonomous Document Routing and Skill Execution Engine")
    parser.add_argument("--base-dir", default=".", help="Base directory for paths")
    return parser.parse_args()


def is_port_in_use(port: int) -> bool:
    """Checks if a TCP port is in use on localhost."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def is_ordinflow_running(port: int) -> bool:
    """Checks if an active OrdinFlow backend is already responding to status healthchecks on this port."""
    url = f"http://127.0.0.1:{port}/api/status"
    req = urllib.request.Request(url, headers={"User-Agent": "OrdinFlow-Launcher"})
    try:
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            return bool(resp.status == 200)
    except (URLError, TimeoutError, OSError):
        return False


def _cleanup_stale_instance(port: int) -> None:
    """Attempts to kill stale processes occupying the port (Windows only)."""
    if sys.platform != "win32":
        return
    logger.warning("[!] Port %s is occupied by a stale process. Attempting cleanup...", port)
    res = subprocess.run(
        f"netstat -ano | findstr :{port}",
        shell=True,
        capture_output=True,
        text=True,
        check=False,
    )
    pids = set()
    for line in res.stdout.strip().splitlines():
        parts = line.split()
        if len(parts) >= 5 and "LISTENING" in parts:
            pids.add(parts[-1])
    for pid in pids:
        try:
            int_pid = int(pid)
            if int_pid != os.getpid():
                logger.info("[*] Killing stale process with PID %s...", pid)
                subprocess.run(
                    f"taskkill /F /PID {pid}",
                    shell=True,
                    capture_output=True,
                    check=False,
                )
            time.sleep(1)
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as e:
            logger.error("[!] Error killing process on port %s: %s", port, e)


def main() -> None:
    args = parse_args()
    setup_logging()

    config = AppConfig(base_dir=args.base_dir)
    config.load_from_yaml()
    config.setup_paths()

    # If OrdinFlow is already running and healthy: open browser and exit launcher cleanly
    if is_ordinflow_running(config.dashboard_port):
        logger.info(
            "[*] OrdinFlow is already running on port %s. Opening Web Dashboard in browser...",
            config.dashboard_port,
        )
        from dashboard import open_browser

        open_browser(config.dashboard_port)
        return

    # If port is occupied by an unresponsive process: clean up stale instance
    if is_port_in_use(config.dashboard_port):
        _cleanup_stale_instance(config.dashboard_port)

    logger.info("%s", "=" * 60)
    logger.info("[*] Watch Directory (Inbox)        : %s", config.watch_dir)
    logger.info("[*] Target Directory (Cases)       : %s", config.target_base_dir)
    logger.info("%s", "=" * 60)

    processor = DocumentProcessor(config)
    queue_manager = get_skill_queue_manager()

    from routes.state import DashboardState

    DashboardState.processor = processor
    DashboardState.config = config
    DashboardState.shutdown_event.clear()
    DashboardState.last_heartbeat = time.time()

    # 1. Start Web Dashboard
    try:
        import dashboard

        dash_thread = threading.Thread(
            target=dashboard.start_dashboard,
            args=(processor, None, config),
            daemon=True,
        )
        dash_thread.start()
        logger.info(
            "[*] Web Dashboard started at http://127.0.0.1:%s",
            config.dashboard_port,
        )
    except (ImportError, RuntimeError, OSError, AttributeError) as e:
        logger.error("[!] Could not start Web Dashboard: %s", e)

    logger.info("[*] Skill Queue Manager active (Single Source of Execution).")

    # 2. Warm up Vision-LLM in background so first file processes instantly
    try:
        threading.Thread(
            target=processor.extraction_pipeline.llm_extractor.preload,
            daemon=True,
            name="ModelWarmupWorker",
        ).start()
    except Exception as e:
        logger.warning("[!] Could not initiate model preload: %s", e)

    shutdown_event = DashboardState.shutdown_event
    while not shutdown_event.is_set():
        if shutdown_event.wait(timeout=1.0):
            logger.info("[*] Shutdown signal received. Exiting cleanly...")
            break

    logger.info("[*] Stopping Skill Queue Manager...")
    queue_manager.stop_queue()
    logger.info("[*] Unloading AI models from memory...")
    try:
        processor.extraction_pipeline.llm_extractor.unload_backend()
    except Exception as e:
        logger.warning("[!] Error unloading models during shutdown: %s", e)
    processor.log_stats()
    logger.info("[*] Service terminated successfully.")
    time.sleep(0.5)
    os._exit(0)


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError, TypeError, KeyError) as e:
        logger.critical("[CRITICAL STARTUP ERROR] %s", e, exc_info=True)
        os._exit(1)
