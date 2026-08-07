import argparse
import logging
import os
import queue
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
    with open(_crash_log, "a", encoding="utf-8", buffering=1) as _log_f:
        if sys.stderr is None:
            sys.stderr = _log_f
        if sys.stdout is None:
            sys.stdout = _log_f
except OSError as exc:
    logger.warning("Could not initialize crash log: %s", exc)

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from core.config import AppConfig
from core.processor import DocumentProcessor

ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}


class PDFHandler(FileSystemEventHandler):
    def __init__(self, processor: DocumentProcessor, file_queue: queue.Queue):
        super().__init__()
        self.processor = processor
        self.file_queue = file_queue

    def on_created(self, event):
        if event.is_directory:
            return
        fname = str(os.path.basename(event.src_path))
        # Ignore sidecar files
        if fname.endswith(".meta"):
            return
        filepath = os.path.abspath(event.src_path)
        if os.path.splitext(filepath.lower())[1] not in ALLOWED_EXTENSIONS:
            return
        # Skip if sidecar file already marks document as PRUEFEN
        if os.path.exists(str(filepath) + ".meta"):
            return
        with self.processor.processing_lock:
            if filepath in self.processor.processing_files:
                return
            self.processor.processing_files.add(filepath)
        self.file_queue.put(filepath)


def worker_loop(file_queue: queue.Queue, processor: DocumentProcessor):
    while True:
        filepath = file_queue.get()
        if filepath is None:
            break
        try:
            # Wait if processing is paused
            processor.wait_if_paused()

            # Skip if file does not exist or has already been marked with .meta
            if not os.path.exists(filepath) or os.path.exists(filepath + ".meta"):
                logger.info(
                    "[*] Skipping already processed or marked file: %s",
                    os.path.basename(filepath),
                )
                continue

            processor.process_and_route_file(filepath)
        except (OSError, RuntimeError, ValueError, TypeError, KeyError) as e:
            logger.error(
                "[!] Error in background worker processing '%s': %s", filepath, e
            )
        finally:
            with processor.processing_lock:
                processor.processing_files.discard(filepath)
            file_queue.task_done()


def process_existing_files(
    processor: DocumentProcessor,
    file_queue: queue.Queue,
    allowed_extensions: set[str] | list[str] | None = None,
):
    """Scans the watch directory and queues all unprocessed files.
    Groups per directory and sorts alphabetically within each folder.
    """
    watch_dir = processor.config.watch_dir
    if not os.path.exists(watch_dir):
        return
    queued = 0

    valid_exts = set(allowed_extensions) if allowed_extensions else ALLOWED_EXTENSIONS

    # topdown=True allows in-place sorting of subdirectories
    for root, dirs, files in os.walk(watch_dir, topdown=True):
        dirs.sort()  # Sort subdirectories alphabetically
        for f in sorted(files):  # Sort files in current directory alphabetically
            fp = os.path.abspath(os.path.join(root, f))
            if not os.path.isfile(fp):
                continue
            if f.endswith(".meta"):
                continue  # Skip sidecar files
            if os.path.splitext(f.lower())[1] not in valid_exts:
                continue
            if os.path.exists(fp + ".meta"):
                continue  # Sidecar exists: already marked as PRUEFEN

            with processor.processing_lock:
                if fp in processor.processing_files:
                    continue
                processor.processing_files.add(fp)

            file_queue.put(fp)
            queued += 1

    if queued > 0:
        logger.info(
            "[*] Found %d file(s) in watch directory and queued for processing.",
            queued,
        )


class FlushingFileHandler(logging.FileHandler):
    def emit(self, record):
        try:
            super().emit(record)
            self.flush()
        except (OSError, ValueError, UnicodeError) as exc:
            logger.debug("Could not emit log record: %s", exc)


class SafeStreamHandler(logging.StreamHandler):
    def emit(self, record):
        try:
            super().emit(record)
        except (OSError, ValueError, UnicodeError) as exc:
            logger.debug("Could not emit log record: %s", exc)


def setup_logging():
    log_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    # File handler with UTF-8 and direct flush
    file_handler = FlushingFileHandler(
        "main.log",
        mode="a",
        encoding="utf-8",
    )
    file_handler.setFormatter(log_formatter)
    root_logger.addHandler(file_handler)

    # Console handler with fallback safety for Windows OEM encodings
    if sys.stdout is not None and sys.stdout != sys.stderr:
        console_handler = SafeStreamHandler(sys.stdout)
        console_handler.setFormatter(log_formatter)
        root_logger.addHandler(console_handler)

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("werkzeug").setLevel(logging.ERROR)


def is_port_in_use(port: int = 8080) -> bool:
    import socket

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            return s.connect_ex(("127.0.0.1", port)) == 0
    except (OSError, ValueError, URLError):
        return False


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-dir", type=str, default=".")
    return parser.parse_known_args()[0]


def _cleanup_stale_instance(port: int) -> None:
    """Attempts graceful shutdown of any stale OrdinFlow instance, followed by force-kill if needed."""
    url = f"http://127.0.0.1:{port}/api/router/shutdown"
    logger.info("[*] Sending shutdown signal to existing process on port %s...", port)
    try:
        req = urllib.request.Request(
            url, data=b"", headers={"User-Agent": "OrdinFlow-Launcher"}
        )
        with urllib.request.urlopen(req, timeout=2):
            pass
    except (OSError, URLError, TimeoutError, ValueError):
        pass

    for _ in range(6):
        time.sleep(0.5)
        if not is_port_in_use(port):
            logger.info("[+] Stale process on port %s shut down cleanly.", port)
            return

    logger.warning("[!] Port %s still in use. Terminating stale process...", port)
    if sys.platform == "win32":
        try:
            out = subprocess.check_output(
                "netstat -ano -p tcp", shell=True, text=True, errors="ignore"
            )
            pids_to_kill = set()
            for line in out.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.strip().split()
                    if len(parts) >= 5:
                        pid_str = parts[-1]
                        if pid_str.isdigit() and int(pid_str) != os.getpid():
                            pids_to_kill.add(pid_str)
            for pid in pids_to_kill:
                logger.info(
                    "[*] Terminating stale process PID %s on port %s...", pid, port
                )
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

    # If OrdinFlow is already running on the port: clean up stale instance for a fresh start
    if is_port_in_use(config.dashboard_port):
        _cleanup_stale_instance(config.dashboard_port)

    logger.info("%s", "=" * 60)
    logger.info("[*] Watch Directory (Inbox)        : %s", config.watch_dir)
    logger.info("[*] Target Directory (Cases)       : %s", config.target_base_dir)
    logger.info("%s", "=" * 60)

    processor = DocumentProcessor(config)
    file_queue = queue.Queue()

    from routes.state import DashboardState

    DashboardState.processor = processor
    DashboardState.file_queue = file_queue
    DashboardState.config = config
    DashboardState.shutdown_event.clear()
    DashboardState.last_heartbeat = time.time()

    # 1. Start Web Dashboard
    try:
        import dashboard

        dash_thread = threading.Thread(
            target=dashboard.start_dashboard,
            args=(processor, file_queue, config),
            daemon=True,
        )
        dash_thread.start()
        logger.info(
            "[*] Web Dashboard started at http://127.0.0.1:%s",
            config.dashboard_port,
        )
    except (ImportError, RuntimeError, OSError, AttributeError) as e:
        logger.error("[!] Could not start Web Dashboard: %s", e)

    # 2. Start background worker and Watchdog observer
    worker_thread = threading.Thread(
        target=worker_loop, args=(file_queue, processor), daemon=True
    )
    worker_thread.start()

    process_existing_files(processor, file_queue)

    event_handler = PDFHandler(processor, file_queue)
    observer = Observer()
    observer.schedule(event_handler, path=config.watch_dir, recursive=True)
    observer.start()

    logger.info("[*] Watchdog active.")

    shutdown_event = DashboardState.shutdown_event
    while not shutdown_event.is_set():
        if shutdown_event.wait(timeout=1.0):
            logger.info("[*] Shutdown signal received. Exiting cleanly...")
            break

    observer.stop()
    logger.info("[*] Waiting for ongoing file processing to complete (max 30s)...")
    processor.resume()
    file_queue.put(None)
    worker_thread.join(timeout=30)
    observer.join()

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
