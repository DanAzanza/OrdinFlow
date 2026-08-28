"""Action-Level Error Handling and Recovery Engine for OrdinFlow RPA Skills.

Evaluates and executes configured error policies (CONTINUE, ABORT, RETRY, FALLBACK)
for discrete action steps, preventing uncontrolled script crashes and enabling resilient workflows.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping
from typing import Any

logger = logging.getLogger(__name__)


class ActionExecutionError(Exception):
    """Raised when an action fails and the error policy dictates aborting."""


def handle_action_error(
    step: Mapping[str, Any],
    step_id: str,
    error_msg: str,
    context: Mapping[str, Any],
    retry_fn: Callable[[], bool] | None = None,
    fallback_fn: Callable[[dict[str, Any]], bool] | None = None,
    save_screenshot_fn: Callable[[str, str], Any] | None = None,
) -> bool:
    """Evaluates the error policy for a failed step.

    Supported `on_error` specifications:
    1. String shorthand: "ABORT" (default), "CONTINUE", "RETRY", "FALLBACK"
    2. Dict configuration:
       - action: "CONTINUE" | "ABORT" | "RETRY" | "FALLBACK"
       - max_retries: int (default: 3)
       - delay_ms: int (default: 500)
       - fallback_action: dict (e.g. `{"action_type": "HOTKEY", "keys": ["esc"]}`)
    """
    on_error = step.get("on_error")
    action_type = str(step.get("action_type") or step.get("type", "")).upper()

    policy = "ABORT"
    max_retries = 3
    delay_ms = 500
    fallback_action: dict[str, Any] | None = None

    if isinstance(on_error, str):
        policy = on_error.upper().strip()
    elif isinstance(on_error, Mapping):
        policy = str(on_error.get("action", "ABORT")).upper().strip()
        max_retries = max(int(on_error.get("max_retries", 3)), 1)
        delay_ms = max(int(on_error.get("delay_ms", 500)), 0)
        fallback_action = on_error.get("fallback_action")

    logger.warning(
        "[ErrorHandler] Step '%s' (%s) encountered error: %s. Applying error policy: %s",
        step_id,
        action_type,
        error_msg,
        policy,
    )

    # 1. CONTINUE (Ignore and proceed)
    if policy in ("CONTINUE", "IGNORE"):
        logger.info("[ErrorHandler] Continuing workflow after suppressed error in step '%s'.", step_id)
        return True

    # 2. RETRY (Execute retry loop)
    if policy == "RETRY" and retry_fn:
        logger.info("[ErrorHandler] Retrying step '%s' up to %d times...", step_id, max_retries)
        for attempt in range(1, max_retries + 1):
            if delay_ms > 0:
                time.sleep(delay_ms / 1000.0)
            logger.info("[ErrorHandler] Step '%s' retry attempt %d/%d", step_id, attempt, max_retries)
            try:
                if retry_fn():
                    logger.info("[ErrorHandler] Step '%s' succeeded on retry attempt %d.", step_id, attempt)
                    return True
            except Exception as e:
                logger.debug("[ErrorHandler] Step '%s' retry %d failed: %s", step_id, attempt, e)

        logger.error("[ErrorHandler] All %d retries for step '%s' exhausted.", max_retries, step_id)

    # 3. FALLBACK (Execute emergency/recovery step)
    if (policy == "FALLBACK" or fallback_action) and fallback_fn and fallback_action:
        logger.info("[ErrorHandler] Executing fallback action for step '%s': %s", step_id, fallback_action)
        try:
            fb_success = fallback_fn(dict(fallback_action))
            if fb_success:
                logger.info("[ErrorHandler] Fallback action for step '%s' executed successfully.", step_id)
                return True
        except Exception as e:
            logger.error("[ErrorHandler] Fallback action for step '%s' failed: %s", step_id, e)

    # 4. ABORT (Default: Fail fast and capture diagnostics)
    if save_screenshot_fn:
        save_screenshot_fn(step_id, f"Action Error: {error_msg}")

    logger.error("[ErrorHandler] Step '%s' aborted workflow due to unhandled error.", step_id)
    return False
