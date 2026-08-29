"""Input Shielding (BlockInput) module for crash-safe automation execution."""

import atexit
import ctypes
import logging
import sys
import threading
from contextlib import contextmanager

logger = logging.getLogger(__name__)

_block_input_active = False
_shield_lock = threading.Lock()
_shield_depth = 0


def set_block_input(enable: bool) -> bool:
    """Toggles the Windows BlockInput lock in a crash-safe manner."""
    global _block_input_active
    if sys.platform != "win32":
        return False
    try:
        result = ctypes.windll.user32.BlockInput(ctypes.c_bool(enable))  # type: ignore[union-attr]
        if result or not enable:
            _block_input_active = enable
        return bool(result)
    except OSError as e:
        logger.warning("[InputShield] Error in BlockInput(%s): %s", enable, e)
        _block_input_active = False
        return False


def _emergency_unblock() -> None:
    """Safety Net: Ensures keyboard/mouse is unblocked upon process termination."""
    global _shield_depth
    with _shield_lock:
        _shield_depth = 0
    if _block_input_active:
        set_block_input(False)


atexit.register(_emergency_unblock)


@contextmanager
def input_shield(enabled: bool = True):
    """Context Manager for temporary user input blocking. Guaranteed release via try...finally."""
    global _shield_depth
    if not enabled or sys.platform != "win32":
        yield
        return

    with _shield_lock:
        if _shield_depth == 0:
            set_block_input(True)
        _shield_depth += 1
    try:
        yield
    finally:
        with _shield_lock:
            _shield_depth = max(0, _shield_depth - 1)
            if _shield_depth == 0:
                set_block_input(False)
