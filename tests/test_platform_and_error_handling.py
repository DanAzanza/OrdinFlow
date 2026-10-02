"""Unit tests for platform utilities (drive listing, native dialogs) and RPA error handling."""

from __future__ import annotations

import base64
import os
import subprocess
import sys
from unittest.mock import MagicMock

from core.platform_utils import get_system_drives, pick_path_dialog
from core.skills.error_handler import handle_action_error


# ============================================================================
# 1. Platform Utils Tests (Drive Listing & Native Dialogs)
# ============================================================================


def test_get_system_drives(monkeypatch):
    """Tests system drive enumeration on Windows and POSIX fallback."""
    # 1. POSIX fallback
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(os, "name", "posix")
    assert get_system_drives() == ["/"]

    # 2. Windows simulation
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(os, "name", "nt")

    def mock_exists(path):
        return path in ("C:\\", "D:\\")

    monkeypatch.setattr(os.path, "exists", mock_exists)
    drives = get_system_drives()
    assert "C:\\" in drives
    assert "D:\\" in drives
    assert "Z:\\" not in drives


def test_pick_path_dialog_tkinter_file_and_folder(monkeypatch):
    """Tests native GUI picker via Tkinter for file and directory without popping up real windows."""
    mock_tk_mod = MagicMock()
    mock_filedialog = MagicMock()

    mock_filedialog.askopenfilename.return_value = "C:/models/qwen.gguf"
    mock_filedialog.askdirectory.return_value = "C:/docs/inbox"
    mock_tk_mod.filedialog = mock_filedialog

    monkeypatch.setitem(sys.modules, "tkinter", mock_tk_mod)
    monkeypatch.setitem(sys.modules, "tkinter.filedialog", mock_filedialog)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""))

    # 1. File picker with model filter detection
    res_file = pick_path_dialog(picker_type="file", title="Select GGUF Model")
    assert res_file == os.path.normpath("C:/models/qwen.gguf")
    mock_filedialog.askopenfilename.assert_called_once()
    _, kwargs = mock_filedialog.askopenfilename.call_args
    assert any("*.gguf" in str(ft) for ft in kwargs.get("filetypes", []))

    # 2. Folder picker
    res_folder = pick_path_dialog(picker_type="folder", title="Select Scan Folder")
    assert res_folder == os.path.normpath("C:/docs/inbox")
    mock_filedialog.askdirectory.assert_called_once()


def test_pick_path_dialog_powershell_fallback(monkeypatch):
    """Tests PowerShell fallback when Tkinter is unavailable, asserting -EncodedCommand syntax."""
    # Force Tkinter failure
    mock_tk_mod = MagicMock()
    mock_tk_mod.Tk.side_effect = RuntimeError("No DISPLAY")
    monkeypatch.setitem(sys.modules, "tkinter", mock_tk_mod)

    captured_cmds: list[list[str]] = []

    def mock_run(cmd, *args, **kwargs):
        captured_cmds.append(cmd)
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout="C:\\ps_selected\\folder\n",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", mock_run)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(os, "name", "nt")

    res = pick_path_dialog(picker_type="folder", title="Select PS Folder")
    assert res == os.path.normpath("C:\\ps_selected\\folder")
    assert len(captured_cmds) == 1

    # Decode and inspect PowerShell encoded payload
    encoded_arg = captured_cmds[0][-1]
    decoded_script = base64.b64decode(encoded_arg).decode("utf-16le")
    assert "System.Windows.Forms.FolderBrowserDialog" in decoded_script
    assert "Select PS Folder" in decoded_script


def test_pick_path_dialog_blocked_directories(monkeypatch):
    """Verifies that protected/blocked system directories fall back to os.getcwd()."""
    mock_tk_mod = MagicMock()
    mock_filedialog = MagicMock()
    mock_filedialog.askdirectory.return_value = "C:/safe/folder"
    mock_tk_mod.filedialog = mock_filedialog

    monkeypatch.setitem(sys.modules, "tkinter", mock_tk_mod)
    monkeypatch.setitem(sys.modules, "tkinter.filedialog", mock_filedialog)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""))

    # Initial dir pointing into Windows directory
    pick_path_dialog(picker_type="folder", initial_dir="C:\\Windows\\System32")
    _, kwargs = mock_filedialog.askdirectory.call_args
    assert kwargs.get("initialdir") == os.getcwd()

    # Initial dir pointing into $Recycle.Bin
    pick_path_dialog(picker_type="folder", initial_dir="C:\\$Recycle.Bin\\S-1-5")
    _, kwargs2 = mock_filedialog.askdirectory.call_args
    assert kwargs2.get("initialdir") == os.getcwd()


# ============================================================================
# 2. Error Handler Tests (Policies: CONTINUE, RETRY, FALLBACK, ABORT)
# ============================================================================


def test_error_handler_continue_and_ignore():
    """CONTINUE and IGNORE policies return True, suppressing error."""
    # 1. String policy CONTINUE
    step_continue = {"id": "step_1", "on_error": "CONTINUE"}
    assert handle_action_error(step_continue, "step_1", "Simulated error", context={}) is True

    # 2. String policy IGNORE
    step_ignore = {"id": "step_2", "on_error": "IGNORE"}
    assert handle_action_error(step_ignore, "step_2", "Simulated error", context={}) is True

    # 3. Dict policy action CONTINUE
    step_dict_continue = {"id": "step_3", "on_error": {"action": "CONTINUE"}}
    assert handle_action_error(step_dict_continue, "step_3", "Simulated error", context={}) is True


def test_error_handler_retry_success_and_exhaustion(monkeypatch):
    """RETRY policy executes retry_fn up to max_retries with zero sleep overhead."""
    # Crucial: Monkeypatch time.sleep to instant no-op to preserve CI test budget
    monkeypatch.setattr("time.sleep", lambda _: None)

    # 1. Retry succeeds on 2nd attempt
    attempts = 0

    def mock_retry_success():
        nonlocal attempts
        attempts += 1
        return attempts >= 2

    step_retry = {"id": "step_retry", "on_error": {"action": "RETRY", "max_retries": 3, "delay_ms": 100}}
    res_ok = handle_action_error(
        step_retry,
        "step_retry",
        "Temporary timeout",
        context={},
        retry_fn=mock_retry_success,
    )
    assert res_ok is True
    assert attempts == 2

    # 2. Retry exhausts all attempts and returns False
    exhaust_attempts = 0

    def mock_retry_fail():
        nonlocal exhaust_attempts
        exhaust_attempts += 1
        return False

    res_fail = handle_action_error(
        step_retry,
        "step_retry",
        "Persistent timeout",
        context={},
        retry_fn=mock_retry_fail,
    )
    assert res_fail is False
    assert exhaust_attempts == 3


def test_error_handler_fallback_action():
    """FALLBACK policy executes fallback_fn with fallback_action payload."""
    executed_fallbacks: list[dict] = []

    def mock_fallback(action):
        executed_fallbacks.append(action)
        return True

    fb_action = {"action_type": "HOTKEY", "keys": ["esc"]}
    step_fb = {
        "id": "step_fb",
        "on_error": {
            "action": "FALLBACK",
            "fallback_action": fb_action,
        },
    }

    res = handle_action_error(
        step_fb,
        "step_fb",
        "Dialog stuck",
        context={},
        fallback_fn=mock_fallback,
    )
    assert res is True
    assert len(executed_fallbacks) == 1
    assert executed_fallbacks[0] == fb_action


def test_error_handler_abort_and_screenshot():
    """Default ABORT policy invokes diagnostic screenshot callback and returns False."""
    screenshots: list[tuple[str, str]] = []

    def mock_screenshot(step_id, diag):
        screenshots.append((step_id, diag))

    step_abort = {"id": "critical_step", "on_error": "ABORT"}
    res = handle_action_error(
        step_abort,
        "critical_step",
        "Window not found",
        context={},
        save_screenshot_fn=mock_screenshot,
    )
    assert res is False
    assert len(screenshots) == 1
    assert screenshots[0][0] == "critical_step"
    assert "Window not found" in screenshots[0][1]
