"""Script and Subprocess Execution Engine for OrdinFlow RPA Skills.

Handles headless PowerShell, CLI commands, and script execution with timeouts,
fail-fast variable validation, and UTF-8 encoding support.
"""

from __future__ import annotations

import logging
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from typing import Any

from core.skills.models import TaskProgress
from core.utils import sanitize_safe_path

logger = logging.getLogger(__name__)


def execute_script_step(
    step: Mapping[str, Any],
    context: Mapping[str, Any],
    substitute_fn: Callable[[str, Mapping[str, Any]], str],
    wait_for_queue_fn: Callable[..., bool] | None = None,
    reporter: Callable[[TaskProgress], None] | None = None,
) -> bool:
    """Executes a PowerShell / Shell / CLI command step with bounded timeouts."""
    raw_cmd = str(step.get("command", "") or step.get("script", "") or step.get("code", ""))
    if "{document_fullpath}" in raw_cmd:
        raw_fp = str(context.get("document_fullpath", "") or "").strip()
        is_safe, clean_fp = sanitize_safe_path(raw_fp)
        resolved_doc = None
        if is_safe and clean_fp:
            candidate = Path(clean_fp).resolve()
            if candidate.is_file():
                resolved_doc = candidate

        if not resolved_doc:
            logger.error(
                "  [!] SCRIPT aborted: Required variable 'document_fullpath' is missing or points to non-existent file: %r",
                raw_fp,
            )
            return False

    cmd_to_run = substitute_fn(raw_cmd, context)
    timeout_s = float(step.get("timeout_s", 60.0))
    shell_type = str(step.get("shell", "powershell")).lower()

    if not cmd_to_run:
        return True

    try:
        if shell_type in ("powershell", "ps1", "pwsh") and sys.platform == "win32":
            ps_bin = shutil.which("powershell.exe") or shutil.which("powershell") or "powershell"
            args = [
                ps_bin,
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                cmd_to_run,
            ]
            proc = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                shell=False,
            )
        else:
            args = shlex.split(cmd_to_run, posix=(sys.platform != "win32"))
            if not args:
                logger.warning("[ScriptRunner] Empty command string provided.")
                return False
            bin_path = shutil.which(args[0])
            if bin_path:
                args[0] = bin_path
            proc = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                shell=False,
            )

        start_proc_t = time.time()
        stdout_out = ""
        stderr_out = ""
        while True:
            if wait_for_queue_fn and not wait_for_queue_fn(reporter, "Skill paused..."):
                try:
                    proc.terminate()
                except OSError as e:
                    logger.debug("[ScriptRunner] Subprocess terminate error: %s", e)
                return False

            remaining_t = timeout_s - (time.time() - start_proc_t)
            if remaining_t <= 0:
                try:
                    proc.kill()
                    proc.communicate(timeout=1.0)
                except OSError as e:
                    logger.debug("[ScriptRunner] Subprocess kill error: %s", e)
                logger.error("[ScriptRunner] Script timed out after %.1fs", timeout_s)
                if step.get("on_failure", "stop") == "stop":
                    return False
                return True

            try:
                chunk_timeout = min(0.25, remaining_t)
                stdout_out, stderr_out = proc.communicate(timeout=chunk_timeout)
                break
            except subprocess.TimeoutExpired:
                continue

        returncode = proc.returncode
        if returncode is not None and returncode != 0:
            logger.error("[ScriptRunner] Script failed (code %d): %s", returncode, stderr_out)
            if step.get("on_failure", "stop") == "stop":
                return False
        elif returncode == 0:
            logger.info(
                "[ScriptRunner] Script executed successfully: %s",
                stdout_out[:200] if stdout_out else "",
            )
        return True
    except Exception as e:
        logger.error("[ScriptRunner] Script execution error: %s", e)
        if step.get("on_failure", "stop") == "stop":
            return False
        return True
