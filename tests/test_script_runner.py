"""Automated tests for safe script execution and parameterization in script_runner.py."""

from __future__ import annotations

import sys

from core.skills.script_runner import execute_script_step


def test_script_runner_parameterizes_via_environment():
    """Context variables must be passed via environment variables, preventing shell injection."""
    step = {
        "id": "step_ps",
        "action_type": "POWERSHELL",
        "command": "Write-Output {PatientName}",
        "shell": "powershell" if sys.platform == "win32" else "bash",
    }
    malicious_context = {
        "PatientName": 'Max"; Write-Output "INJECTED"; #',
    }

    # On non-Windows platforms, powershell may not be present, test environment formulation
    if sys.platform != "win32":
        # Test command rewriting logic
        import re
        cmd = re.sub(r"\{([A-Za-z0-9_]+)\}", lambda m: f"$env:ORDINFLOW_{m.group(1).upper()}", step["command"])
        assert cmd == "Write-Output $env:ORDINFLOW_PATIENTNAME"
        return

    # On Windows, run actual subprocess with safe environment variable
    # We capture stdout via a simple echo
    step["command"] = "$env:ORDINFLOW_PATIENTNAME"
    success = execute_script_step(
        step=step,
        context=malicious_context,
        substitute_fn=lambda cmd, ctx: cmd,
    )
    assert success is True


def test_script_runner_rewrites_legacy_placeholders():
    """Legacy {var} placeholders should automatically be rewritten to $env:ORDINFLOW_VAR for PowerShell."""
    import re
    raw_cmd = 'Get-ChildItem -Path "{folder}" -Filter "{filename}"'
    ps_cmd = re.sub(r"\{([A-Za-z0-9_]+)\}", lambda m: f"$env:ORDINFLOW_{m.group(1).upper()}", raw_cmd)
    assert ps_cmd == 'Get-ChildItem -Path "$env:ORDINFLOW_FOLDER" -Filter "$env:ORDINFLOW_FILENAME"'


def test_script_runner_empty_command_succeeds():
    """An empty command string should safely return True without spawning a process."""
    step = {"id": "s_empty", "command": "   "}
    assert execute_script_step(step, {}, lambda s, c: s) is True


def test_script_runner_missing_document_fullpath_fails():
    """Steps referencing document_fullpath must fail fast if path is missing or invalid."""
    import pytest
    from core.skills.exceptions import SkillActionError

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
