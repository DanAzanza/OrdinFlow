"""Input Shielding (BlockInput) module for crash-safe automation execution."""

import atexit
import ctypes
import logging
import sys
from contextlib import contextmanager

logger = logging.getLogger(__name__)

_block_input_active = False


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
    if _block_input_active:
        set_block_input(False)


atexit.register(_emergency_unblock)


@contextmanager
def input_shield(enabled: bool = True):
    """Context Manager for temporary user input blocking. Guaranteed release via try...finally."""
    if not enabled:
        yield
        return

    set_block_input(True)
    try:
        yield
    finally:
        set_block_input(False)
