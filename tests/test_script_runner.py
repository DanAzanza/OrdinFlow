"""Automated tests for safe script execution and parameterization in script_runner.py."""

from __future__ import annotations

import logging
import sys
import pytest

from core.skills.exceptions import SkillActionError
from core.skills.script_runner import execute_script_step


def test_script_runner_parameterizes_via_environment(caplog):
    """Context variables must be passed via environment variables, preventing shell injection."""
    caplog.set_level(logging.INFO)
    malicious_context = {
        "PatientName": 'Max"; Write-Output "INJECTED"; #',
    }

    if sys.platform == "win32":
        step = {
            "id": "step_ps",
            "action_type": "POWERSHELL",
            "command": 'Write-Output "Name={PatientName}"',
            "shell": "powershell",
        }
        # execute_script_step must rewrite {PatientName} to $env:ORDINFLOW_PATIENTNAME
        # and execute safely without running the injected command.
        success = execute_script_step(
            step=step,
            context=malicious_context,
            substitute_fn=lambda cmd, ctx: cmd,
        )
        assert success is True
        # Output must contain the payload as literal text
        assert 'Name=Max"; Write-Output "INJECTED"; #' in caplog.text
        # The injected payload must NOT have executed as an independent command (which would print just 'INJECTED')
        log_lines = [line.strip() for line in caplog.text.splitlines()]
        assert "INJECTED" not in log_lines
    else:
        # Non-Windows fallback test
        step = {
            "id": "step_sh",
            "action_type": "SCRIPT",
            "command": 'echo "Name={PatientName}"',
            "shell": "bash",
        }
        success = execute_script_step(
            step=step,
            context=malicious_context,
            substitute_fn=lambda cmd, ctx: cmd,
        )
        assert success is True


def test_script_runner_rewrites_legacy_placeholders_in_execution(caplog):
    """Legacy {var} placeholders must be rewritten into environment references and evaluated by the shell."""
    caplog.set_level(logging.INFO)
    context = {"folder": "Archiv2026", "filename": "Befund_Report.pdf"}

    if sys.platform == "win32":
        step = {
            "id": "step_rw",
            "command": 'Write-Output "{folder}__{filename}"',
            "shell": "powershell",
        }
        success = execute_script_step(
            step=step,
            context=context,
            substitute_fn=lambda cmd, ctx: cmd,
        )
        assert success is True
        assert "Archiv2026__Befund_Report.pdf" in caplog.text
    else:
        step = {
            "id": "step_rw_sh",
            "command": 'echo "{folder}__{filename}"',
            "shell": "bash",
        }
        success = execute_script_step(
            step=step,
            context=context,
            substitute_fn=lambda cmd, ctx: cmd,
        )
        assert success is True


def test_script_runner_cmd_and_bat_shell_prohibited():
    """Execution with shell='cmd' or 'bat' must fail fast with SkillActionError to eliminate cmd injection vectors."""
    step_cmd = {
        "id": "s_cmd",
        "command": "echo {name}",
        "shell": "cmd",
        "on_failure": "stop",
    }
    with pytest.raises(SkillActionError, match="prohibited due to cmd.exe variable expansion vulnerabilities"):
        execute_script_step(step_cmd, {"name": "Test"}, lambda s, c: s)

    step_bat = {
        "id": "s_bat",
        "command": "echo {name}",
        "shell": "bat",
        "on_failure": "stop",
    }
    with pytest.raises(SkillActionError, match="prohibited due to cmd.exe variable expansion vulnerabilities"):
        execute_script_step(step_bat, {"name": "Test"}, lambda s, c: s)

    # With on_failure='continue', it must return False without raising
    step_continue = dict(step_cmd, on_failure="continue")
    assert execute_script_step(step_continue, {"name": "Test"}, lambda s, c: s) is False


def test_script_runner_empty_command_succeeds():
    """An empty command string should safely return True without spawning a process."""
    step = {"id": "s_empty", "command": "   "}
    assert execute_script_step(step, {}, lambda s, c: s) is True


def test_script_runner_missing_document_fullpath_fails():
    """Steps referencing document_fullpath must fail fast if path is missing or invalid."""
    step = {"id": "s_doc", "command": "echo {document_fullpath}", "on_failure": "stop"}
    with pytest.raises(SkillActionError, match="document_fullpath"):
        execute_script_step(step, {}, lambda s, c: s)


def test_script_runner_nonzero_exit_code_fails():
    """Non-zero exit codes must return False when on_failure is 'continue'."""
    step = {
        "id": "s_exit",
        "command": "powershell -Command exit 42" if sys.platform == "win32" else "exit 42",
        "shell": "powershell" if sys.platform == "win32" else "sh",
        "on_failure": "continue",
    }
    assert execute_script_step(step, {}, lambda s, c: s) is False
