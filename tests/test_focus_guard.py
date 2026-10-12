"""Automated negative and invariance tests for Desktop RPA Focus Guard & Failsafe mechanism."""

from __future__ import annotations

from unittest.mock import patch
import pytest

from core.skills.action_executor import execute_type_text
from core.skills.exceptions import SkillActionError
from core.skills.window_manager import (
    is_desktop_locked_or_minimized,
    is_target_or_child_active,
    verify_and_ensure_focus,
)


def test_focus_guard_allows_matching_window():
    """Focus guard succeeds when active foreground window matches target window pattern."""
    with patch("core.skills.window_manager.sys.platform", "win32"), \
         patch("core.skills.window_manager.is_desktop_locked_or_minimized", return_value=(False, "")), \
         patch("core.skills.window_manager.get_active_window_title", return_value="Medistar Praxissoftware - Patient Mustermann"), \
         patch("core.skills.window_manager.get_foreground_hwnd", return_value=12345), \
         patch("core.skills.window_manager.find_window_hwnd", return_value=12345):

        ok, err = verify_and_ensure_focus("Medistar")
        assert ok is True
        assert err == ""


def test_focus_guard_allows_owned_child_dialog():
    """Focus guard permits child modal dialogs (e.g. 'Speichern unter') belonging to the target process."""
    with patch("core.skills.window_manager.sys.platform", "win32"), \
         patch("core.skills.window_manager.is_desktop_locked_or_minimized", return_value=(False, "")), \
         patch("core.skills.window_manager.get_active_window_title", return_value="Speichern unter"), \
         patch("core.skills.window_manager.get_foreground_hwnd", return_value=99999), \
         patch("core.skills.window_manager.find_window_hwnd", return_value=12345), \
         patch("core.skills.window_manager.get_window_pid", side_effect=lambda hwnd: 4040 if hwnd in (99999, 12345) else None):

        # Although title is "Speichern unter" and target is "TurboMed", identical PID allows interaction
        assert is_target_or_child_active("TurboMed") is True

        ok, err = verify_and_ensure_focus("TurboMed")
        assert ok is True
        assert err == ""


def test_focus_guard_aborts_on_unrelated_foreground():
    """Focus guard detects unrelated applications (e.g. Slack/Outlook) and aborts keystroke typing."""
    with patch("core.skills.window_manager.sys.platform", "win32"), \
         patch("core.skills.window_manager.is_desktop_locked_or_minimized", return_value=(False, "")), \
         patch("core.skills.window_manager.get_active_window_title", return_value="Slack - #general"), \
         patch("core.skills.window_manager.get_foreground_hwnd", return_value=88888), \
         patch("core.skills.window_manager.find_window_hwnd", return_value=None):

        ok, err = verify_and_ensure_focus("Medistar", auto_activate=False)
        assert ok is False
        assert "not active" in err
        assert "Slack" in err

        # Verify that execute_type_text raises SkillActionError and does NOT type
        step = {
            "id": "step_1",
            "action_type": "TYPE_TEXT",
            "text": "Geheimdaten Patient",
            "window_title": "Medistar",
            "on_failure": "stop",
        }
        with pytest.raises(SkillActionError, match="Focus Guard"):
            execute_type_text(
                step=step,
                step_id="step_1",
                action_type="TYPE_TEXT",
                context={},
                substitute_fn=lambda t, c: t,
                target_window="Medistar",
            )


def test_focus_guard_desktop_locked_fails_safe():
    """When desktop is locked (Win+L) or RDP is minimized (hwnd 0), focus guard fails immediately."""
    with patch("core.skills.window_manager.sys.platform", "win32"), \
         patch("ctypes.windll.user32.GetForegroundWindow", return_value=0):

        locked, reason = is_desktop_locked_or_minimized()
        assert locked is True
        assert "detached" in reason or "minimized" in reason

        ok, err = verify_and_ensure_focus("Medistar")
        assert ok is False
        assert "Desktop locked" in err


def test_clipboard_sanitizes_pii_on_restore():
    """paste_text_via_clipboard should clear clipboard after paste if prev_text was None."""
    from core.skills.text_helpers import paste_text_via_clipboard

    with patch("sys.platform", "win32"), \
         patch("core.skills.text_helpers._open_clipboard_with_retry", return_value=True), \
         patch("core.skills.text_helpers._get_clipboard_unicode", return_value=None), \
         patch("core.skills.text_helpers._set_clipboard_unicode", return_value=True), \
         patch("ctypes.windll.user32.keybd_event"), \
         patch("ctypes.windll.user32.EmptyClipboard") as mock_empty, \
         patch("ctypes.windll.user32.CloseClipboard"):

        result = paste_text_via_clipboard("Patient Diagnosedaten")
        assert result is True
        # Verify EmptyClipboard was called to wipe sensitive data
        assert mock_empty.called
