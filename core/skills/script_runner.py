"""Script and Subprocess Execution Engine for OrdinFlow RPA Skills.

Handles headless PowerShell, CLI commands, and script execution with timeouts,
fail-fast variable validation, and UTF-8 encoding support.
"""

from __future__ import annotations

import logging
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from core.skills.exceptions import SkillActionError
from core.skills.models import TaskProgress
from core.utils import is_within_allowed_roots, sanitize_safe_path

logger = logging.getLogger(__name__)


def execute_script_step(
    step: Mapping[str, Any],
    context: Mapping[str, Any],
    substitute_fn: Callable[[str, Mapping[str, Any]], str],
    wait_for_queue_fn: Callable[..., bool] | None = None,
    reporter: Callable[[TaskProgress], None] | None = None,
) -> bool:
    """Executes a PowerShell / Shell / CLI command step with bounded timeouts and safe parameterization."""
    step_id = str(step.get("id", "script_step"))
    action_type = str(step.get("action_type") or step.get("type", "SCRIPT")).upper()
    raw_cmd = str(step.get("command", "") or step.get("script", "") or step.get("code", "")).strip()
    timeout_s = float(step.get("timeout_s", 60.0))
    shell_type = str(step.get("shell", "powershell")).lower()

    if not raw_cmd:
        logger.warning("[ScriptRunner] Empty command string provided.")
        return True

    resolved_doc: Path | None = None
    if (
        "{document_fullpath}" in raw_cmd
        or "$env:ORDINFLOW_DOCUMENT_FULLPATH" in raw_cmd
        or "${env:ORDINFLOW_DOCUMENT_FULLPATH}" in raw_cmd
    ):
        raw_fp = str(context.get("document_fullpath", "") or "").strip()
        is_safe, clean_fp = sanitize_safe_path(raw_fp)
        if is_safe and clean_fp:
            candidate = Path(clean_fp).resolve()
            if is_within_allowed_roots(candidate) and candidate.is_file():
                resolved_doc = candidate

        if not resolved_doc:
            err_msg = (
                f"Required variable 'document_fullpath' is missing, invalid, or points to non-existent file: {raw_fp!r}"
            )
            logger.error("  [!] SCRIPT aborted: %s", err_msg)
            if step.get("on_failure", "stop") == "stop":
                raise SkillActionError(step_id, err_msg, action_type)
            return False

    # 1. Prepare safe process environment variables (cap at 8192 chars for Windows environment block safety)
    proc_env = dict(os.environ)
    for k, v in context.items():
        if isinstance(v, (str, int, float, bool)):
            clean_k = re.sub(r"[^A-Za-z0-9_]", "_", str(k)).upper()
            val_str = str(resolved_doc if k == "document_fullpath" and resolved_doc else v)
            proc_env[f"ORDINFLOW_{clean_k}"] = val_str.replace("\x00", "")[:8192]

    if shell_type in ("cmd", "bat"):
        err_msg = (
            "Execution with shell='cmd' or 'bat' is prohibited due to cmd.exe variable expansion vulnerabilities. "
            "Use 'powershell' (or direct binary execution) instead."
        )
        logger.error("  [!] SCRIPT aborted: %s", err_msg)
        if step.get("on_failure", "stop") == "stop":
            raise SkillActionError(step_id, err_msg, action_type)
        return False

    # 2. Safe command formulation: NEVER interpolate unescaped document text directly into command lines.
    # Instead, rewrite legacy {KEY} placeholders to native shell environment variable references.
    if shell_type in ("powershell", "ps1", "pwsh"):
        def _to_ps_env(m: re.Match[str]) -> str:
            clean_k = re.sub(r"[^A-Za-z0-9_]", "_", m.group(1)).upper()
            return f"${{env:ORDINFLOW_{clean_k}}}"

        cmd_to_run = re.sub(r"\{([A-Za-z0-9_]+)\}", _to_ps_env, raw_cmd)
    elif shell_type in ("bash", "sh"):
        def _to_sh_env(m: re.Match[str]) -> str:
            clean_k = re.sub(r"[^A-Za-z0-9_]", "_", m.group(1)).upper()
            return f"$ORDINFLOW_{clean_k}"

        cmd_to_run = re.sub(r"\{([A-Za-z0-9_]+)\}", _to_sh_env, raw_cmd)
    else:
        # CLI direct binary execution: only rewrite validated document_fullpath
        cmd_to_run = raw_cmd.replace("{document_fullpath}", str(resolved_doc or ""))

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
                env=proc_env,
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
                env=proc_env,
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
                err_msg = f"Script timed out after {timeout_s:.1f}s"
                logger.error("[ScriptRunner] %s", err_msg)
                if step.get("on_failure", "stop") == "stop":
                    raise SkillActionError(step_id, err_msg, action_type)
                return False

            try:
                chunk_timeout = min(0.25, remaining_t)
                stdout_out, stderr_out = proc.communicate(timeout=chunk_timeout)
                break
            except subprocess.TimeoutExpired:
                continue

        returncode = proc.returncode
        if returncode is not None and returncode != 0:
            clean_err = stderr_out.strip() or stdout_out.strip() or f"Process exited with code {returncode}"
            err_msg = f"Script failed with exit code {returncode}: {clean_err[:300]}"
            logger.error("[ScriptRunner] %s", err_msg)
            if step.get("on_failure", "stop") == "stop":
                raise SkillActionError(step_id, err_msg, action_type)
            return False
        elif returncode == 0:
            logger.info(
                "[ScriptRunner] Script executed successfully: %s",
                stdout_out[:200] if stdout_out else "",
            )
        return True
    except SkillActionError:
        raise
    except Exception as e:
        err_msg = f"Script execution error: {e}"
        logger.error("[ScriptRunner] %s", err_msg)
        if step.get("on_failure", "stop") == "stop":
            raise SkillActionError(step_id, err_msg, action_type) from e
        return False
