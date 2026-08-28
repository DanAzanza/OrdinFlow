"""Robotic Process Automation (RPA) Export Skill Engine."""

from __future__ import annotations

import ctypes
import logging
import os
import sys
import time
from collections.abc import Callable, Mapping
from typing import Any

from core.skills.base import BaseSkill
from core.skills.grounder import SoMGrounder
from core.skills.models import SkillTask, TaskProgress, TaskResult
from core.skills.shield import input_shield
from core.skills.case_router import (
    filter_matching_files as _filter_matching_files_fn,
    find_pending_cases as _find_pending_cases_fn,
    mark_file_skill_executed as _mark_file_skill_executed_fn,
)
from core.skills.text_helpers import (
    paste_text_via_clipboard as _paste_text_via_clipboard,
    send_hotkey as _send_hotkey,
    substitute_placeholders as _substitute_placeholders_fn,
    type_unicode_text as _type_unicode_text,
)
from core.skills.window_manager import (
    check_hung_app_and_recover,
    ensure_window_ready,
    handle_known_dialog_popups as _handle_known_dialog_popups_fn,
    maximize_target_window,
    save_failure_screenshot as _save_failure_screenshot_fn,
)
from core.skills.condition_evaluator import evaluate_condition
from core.skills.error_handler import handle_action_error
from core.skills.script_runner import execute_script_step
from core.skills.uia_locator import UIALocator
from core.utils import is_sensitive_credential_text, sanitize_safe_path

logger = logging.getLogger(__name__)

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore[assignment]


class ExportEngine(BaseSkill):
    """Executes step-by-step RPA desktop UI and RDP automations."""

    def __init__(
        self,
        definition_or_manager: dict[str, Any] | Any = None,
        skill_manager: Any = None,
        vision_extractor: Any = None,
    ):
        if isinstance(definition_or_manager, dict):
            definition = definition_or_manager
            mgr = skill_manager
            vext = vision_extractor
        else:
            mgr = definition_or_manager
            definition = {"id": "export_engine", "name": "Export Engine", "type": "export"}
            vext = skill_manager

        super().__init__(definition)
        self.skill_manager = mgr
        self.vision_extractor = vext
        raw_tasks = definition.get("tasks")
        raw_steps = definition.get("steps")
        raw_actions = definition.get("actions")

        actions: list[dict[str, Any]] = []
        if isinstance(raw_tasks, list) and raw_tasks:
            for t in raw_tasks:
                if isinstance(t, dict):
                    t_actions = t.get("actions", [])
                    if isinstance(t_actions, list):
                        for a in t_actions:
                            if isinstance(a, dict):
                                actions.append(a)
        elif isinstance(raw_steps, list):
            actions = [s for s in raw_steps if isinstance(s, dict)]
        elif isinstance(raw_actions, list):
            actions = [a for a in raw_actions if isinstance(a, dict)]

        self.steps: list[dict[str, Any]] = actions
        self.actions: list[dict[str, Any]] = actions
        self.tasks: list[dict[str, Any]] = [t for t in raw_tasks if isinstance(t, dict)] if isinstance(raw_tasks, list) else []
        self.target_window = definition.get("target_window")
        if not self.target_window:
            for s in self.steps:
                if s.get("action_type") == "FOCUS_WINDOW" and s.get("window_title"):
                    self.target_window = s.get("window_title")
                    break
        self.rdp_prefix = definition.get("rdp_path_prefix", "")
        self.launch_skill_id = definition.get("launch_skill_id", "")
        self.executable_path = definition.get("executable_path", "")
        self.maximize_window = bool(definition.get("maximize_window", False))
        self.recover_hung_process = bool(definition.get("recover_hung_process", False))

    def _save_failure_screenshot(self, step_id: str, desc: str = "", window_title: str | None = None) -> str | None:
        """Captures and saves a diagnostic screenshot when a skill step fails."""
        return _save_failure_screenshot_fn(step_id, desc, window_title)

    def _substitute_placeholders(self, text: str, context: Mapping[str, Any]) -> str:
        """Dynamically substitutes placeholders with optional modifiers (e.g. {Nachname|upper})."""
        return _substitute_placeholders_fn(text, context)

    def _locate_target(self, locator: dict[str, Any], window_title: str | None = None) -> tuple[int, int] | None:
        """Determines the (x, y) pixel coordinates for a locator with auto-adaptive OCR & VLM fallback."""
        return SoMGrounder.locate_target(locator, window_title=window_title, vision_extractor=self.vision_extractor)

    def _handle_known_dialog_popups(self, window_title: str | None = None) -> bool:
        """Inspects whether an unexpected overwrite/confirmation modal popup is blocking the flow and resolves it."""
        return _handle_known_dialog_popups_fn(window_title)

    def _maximize_window(self, win_pattern: str) -> None:
        """Maximizes the target window via Win32 ShowWindow(SW_MAXIMIZE = 3)."""
        maximize_target_window(win_pattern)

    def _ensure_window_ready(
        self,
        win_pattern: str,
        context: Mapping[str, Any],
        launch_skill_id: str = "",
        exe_path: str = "",
        maximize: bool = False,
    ) -> bool:
        """Checks if target window is available; if not, triggers launch skill or executable and maximizes."""
        return ensure_window_ready(
            win_pattern=win_pattern,
            context=context,
            launch_skill_id=launch_skill_id or self.launch_skill_id,
            exe_path=exe_path or self.executable_path,
            maximize=maximize,
            execute_skill_fn=self.execute_skill,
            is_cancelled_fn=lambda: not self.wait_for_queue(),
        )

    def _check_hung_app_and_recover(self, win_pattern: str, context: Mapping[str, Any]) -> bool:
        """Checks if target window is hung/unresponsive and restarts it if configured."""
        return check_hung_app_and_recover(
            win_pattern=win_pattern,
            context=context,
            recover_enabled=self.recover_hung_process,
            ensure_ready_fn=self._ensure_window_ready,
        )

    def _wait_for_queue(
        self,
        reporter: Callable[[TaskProgress], None] | None = None,
        paused_msg: str = "Execution paused...",
    ) -> bool:
        return self.wait_for_queue(reporter, paused_msg)

    def execute_actions(
        self,
        context: dict[str, Any],
        reporter: Callable[[TaskProgress], None] | None = None,
        depth: int = 0,
        dry_run: bool = False,
    ) -> bool:
        """Executes the recorded or synthesized action sequence step-by-step."""
        if not self.actions:
            logger.info("[!] Skill '%s' has no actions configured. Completed as no-op.", self.id)
            return True

        total_actions = len(self.actions)
        step_map = {str(s.get("id")): idx for idx, s in enumerate(self.actions) if s.get("id")}
        act_idx = 0
        while act_idx < total_actions:
            if not self.wait_for_queue(reporter, "Skill paused..."):
                logger.info("[*] Skill execution stopped by queue.")
                return False

            step = self.actions[act_idx]
            action_type = str(step.get("action_type") or step.get("type", "")).upper()
            step_id = step.get("id", f"act_{act_idx + 1}")
            desc = step.get("description") or action_type
            prefix = f"[Sub-Skill L{depth}] " if depth > 0 else ""

            if reporter:
                pct = int(((act_idx + 1) / total_actions) * 100)
                reporter(
                    TaskProgress(
                        current=act_idx + 1,
                        total=total_actions,
                        message=f"{prefix}Action {act_idx + 1}/{total_actions}: {desc}",
                        percent=pct,
                    )
                )

            logger.info("  [Action %d/%d] %s%s: %s", act_idx + 1, total_actions, prefix, step_id, desc)

            if dry_run and action_type in (
                "CLICK",
                "DOUBLE_CLICK",
                "RIGHT_CLICK",
                "TYPE_TEXT",
                "TYPE_FILE_PATH",
                "PASTE_CLIPBOARD",
                "HOTKEY",
                "PRESS_ENTER",
                "PRESS_TAB",
                "PRESS_KEY",
                "RUN_SCRIPT",
                "POWERSHELL",
                "EXECUTE_COMMAND",
                "SCRIPT",
                "MOUSE_CLICK",
            ):
                logger.info("  [DRY RUN] Simulated input action: %s", action_type)
                act_idx += 1
                continue

            # 1. FOCUS_WINDOW
            if action_type == "FOCUS_WINDOW":
                win_pattern = self._substitute_placeholders(step.get("window_title", self.target_window or ""), context)
                launch_skill = str(step.get("launch_skill_id") or self.launch_skill_id or "")
                exe_path = str(step.get("executable_path") or self.executable_path or "")
                maximize = bool(step.get("maximize_window", self.maximize_window))

                ready = self._ensure_window_ready(
                    win_pattern=win_pattern,
                    context=context,
                    launch_skill_id=launch_skill,
                    exe_path=exe_path,
                    maximize=maximize,
                )
                if not ready and win_pattern:
                    logger.warning(
                        "[ExportEngine] Window '%s' could not be found or launched in step '%s'.",
                        win_pattern,
                        step_id,
                    )

            # 2. CLICK / DOUBLE_CLICK / RIGHT_CLICK
            elif action_type in ("CLICK", "DOUBLE_CLICK", "RIGHT_CLICK"):
                locator = step.get("locator", {})
                win = self._substitute_placeholders(step.get("window_title", self.target_window or ""), context)
                max_retries = max(int(step.get("max_retries", 3)), 1)
                retry_delay_s = float(step.get("retry_delay_s", 0.35))
                coords = None
                for attempt in range(1, max_retries + 1):
                    if not self.wait_for_queue(reporter, "Skill paused..."):
                        return False
                    coords = self._locate_target(locator, win)
                    if coords is not None:
                        break
                    # Attempt auto-dialog resolution if modal is blocking
                    self._handle_known_dialog_popups(win)
                    if attempt < max_retries:
                        if not self.interruptible_sleep(retry_delay_s, reporter=reporter, paused_msg="Skill paused..."):
                            return False

                if coords is None:
                    if not self.wait_for_queue():
                        return False
                    logger.error("  [!] Target not found for action %s: %s", action_type, locator)
                    self._save_failure_screenshot(step_id, desc, win)
                    return False

                with input_shield():
                    if sys.platform == "win32":
                        ctypes.windll.user32.SetCursorPos(coords[0], coords[1])
                        if action_type == "CLICK":
                            ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
                            ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)
                        elif action_type == "DOUBLE_CLICK":
                            ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
                            ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)
                            time.sleep(0.05)
                            ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
                            ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)
                        elif action_type == "RIGHT_CLICK":
                            ctypes.windll.user32.mouse_event(0x0008, 0, 0, 0, 0)
                            ctypes.windll.user32.mouse_event(0x0010, 0, 0, 0, 0)

            # 3. TYPE_TEXT / PASTE_CLIPBOARD
            elif action_type in ("TYPE_TEXT", "PASTE_CLIPBOARD"):
                raw_text = str(step.get("text", "") or step.get("content", ""))
                text_to_type = self._substitute_placeholders(raw_text, context)
                # Fail-fast check: If raw text contains dynamic variable placeholders but resolves to empty string
                if "{" in raw_text and not text_to_type.strip():
                    logger.error("  [!] %s aborted: Placeholder in %r resolved to empty string.", action_type, raw_text)
                    return False

                press_enter = bool(step.get("press_enter", False))
                use_clipboard = bool(
                    step.get("use_clipboard", False)
                    or action_type == "PASTE_CLIPBOARD"
                    or ("\\" in text_to_type or "/" in text_to_type or len(text_to_type) > 15)
                )
                is_secret = bool(step.get("is_secret", False)) or is_sensitive_credential_text(raw_text, step.get("description", ""))
                if is_secret:
                    logger.info("  [Action %s] %s: [PROTECTED SENSITIVE CREDENTIAL MASKED]", step_id, action_type)
                with input_shield():
                    if use_clipboard and sys.platform == "win32":
                        _paste_text_via_clipboard(text_to_type, press_enter=press_enter)
                    else:
                        _type_unicode_text(text_to_type, press_enter=press_enter)

            # 4. TYPE_FILE_PATH (Instant Clipboard Paste + Security Gate + Fail-Fast Validation)
            elif action_type == "TYPE_FILE_PATH":
                raw_path = str(step.get("file_path", context.get("document_fullpath", "") or ""))
                sub_path = self._substitute_placeholders(raw_path, context).strip()
                if not sub_path:
                    logger.error("  [!] TYPE_FILE_PATH aborted: Target file path is empty or unresolved.")
                    return False

                is_safe, clean_path = sanitize_safe_path(sub_path)
                if not is_safe or not clean_path.strip():
                    logger.error("[Security] Aborted TYPE_FILE_PATH due to invalid/unsafe path: %r", sub_path)
                    self._save_failure_screenshot(step_id, f"Security Block: {sub_path}", self.target_window)
                    return False

                final_path = os.path.abspath(clean_path)
                if not os.path.exists(final_path):
                    logger.error("  [!] TYPE_FILE_PATH aborted: Target file does not exist on disk: %s", final_path)
                    self._save_failure_screenshot(step_id, f"Missing File: {final_path}", self.target_window)
                    return False

                if self.rdp_prefix and final_path.startswith("C:"):
                    final_path = self.rdp_prefix + final_path[2:]

                press_enter = bool(step.get("press_enter", True))
                with input_shield():
                    _paste_text_via_clipboard(final_path, press_enter=press_enter)

            # 5. WAIT_FOR_ELEMENT (Dynamic Waiting / Smart Polling)
            elif action_type == "WAIT_FOR_ELEMENT":
                locator = step.get("locator", {})
                win = self._substitute_placeholders(step.get("window_title", self.target_window or ""), context)
                timeout_s = float(step.get("timeout_s", step.get("duration_s", 5.0)))
                poll_interval_s = float(step.get("poll_interval_s", 0.25))
                start_t = time.time()
                found = False
                while (time.time() - start_t) <= timeout_s:
                    if not self.wait_for_queue(reporter, "Skill paused..."):
                        return False
                    coords = self._locate_target(locator, win)
                    if coords is not None:
                        found = True
                        break
                    self._handle_known_dialog_popups(win)
                    if not self.interruptible_sleep(poll_interval_s, reporter=reporter, paused_msg="Skill paused..."):
                        return False

                if not found:
                    if not self.wait_for_queue():
                        return False
                    logger.warning("[ExportEngine] WAIT_FOR_ELEMENT timed out after %.1fs for %s", timeout_s, locator)
                    on_fail = step.get("on_failure", "stop")
                    if on_fail == "stop":
                        self._save_failure_screenshot(step_id, f"Wait Timeout: {locator}", win)
                        return False

            # 6. VERIFY_SCREEN (Conditional Branching)
            elif action_type == "VERIFY_SCREEN":
                locator = step.get("locator", {})
                win = self._substitute_placeholders(step.get("window_title", self.target_window or ""), context)
                max_retries = int(step.get("max_retries", 1))
                retry_delay_s = float(step.get("retry_delay_s", 1.0))
                coords = None
                for attempt in range(1, max_retries + 1):
                    if not self.wait_for_queue(reporter, "Skill paused..."):
                        return False
                    coords = self._locate_target(locator, win)
                    if coords is not None:
                        break
                    if attempt < max_retries:
                        if not self.interruptible_sleep(retry_delay_s, reporter=reporter, paused_msg="Skill paused..."):
                            return False

                if not self.wait_for_queue():
                    return False

                success = coords is not None
                if success:
                    on_succ = step.get("on_success", "continue")
                    if on_succ == "stop_success":
                        return True
                    elif on_succ in step_map:
                        act_idx = step_map[on_succ]
                        continue
                else:
                    on_fail = step.get("on_failure", "stop")
                    on_fail_action = step.get("on_failure_action")
                    if on_fail_action == "run_skill" or on_fail == "run_skill":
                        sub_skill = str(step.get("on_failure_skill", ""))
                        if sub_skill:
                            if not self.execute_skill(sub_skill, context, depth=depth + 1):
                                return False
                    elif on_fail == "stop" and not on_fail_action:
                        return False
                    elif on_fail == "continue" or on_fail_action == "continue":
                        pass
                    elif on_fail in step_map:
                        act_idx = step_map[on_fail]
                        continue

            # 6. CALL_SKILL
            elif action_type == "CALL_SKILL":
                sub_id = str(step.get("skill_id", ""))
                if sub_id:
                    if not self.execute_skill(sub_id, context, depth=depth + 1, dry_run=dry_run):
                        return False

            # 7. HOTKEY
            elif action_type == "HOTKEY":
                keys = step.get("keys", [])
                if keys and sys.platform == "win32":
                    with input_shield():
                        _send_hotkey(keys)

            # 8. SLEEP / DELAY / WAIT
            elif action_type in ("SLEEP", "DELAY", "WAIT"):
                duration_s = float(step.get("duration_s", step.get("delay_ms", 1000) / 1000.0))
                if not self.interruptible_sleep(duration_s, reporter=reporter, paused_msg="Skill paused..."):
                    return False

            # 9. RUN_SCRIPT / POWERSHELL / EXECUTE_COMMAND (Headless COM / CLI Automation)
            elif action_type in ("RUN_SCRIPT", "POWERSHELL", "EXECUTE_COMMAND", "SCRIPT"):
                ok = execute_script_step(
                    step=step,
                    context=context,
                    substitute_fn=self._substitute_placeholders,
                    wait_for_queue_fn=self.wait_for_queue,
                    reporter=reporter,
                )
                if not ok and step.get("on_failure", "stop") == "stop":
                    return False

            # 8. BRANCH / IF_CONDITION (Declarative Conditional Branching)
            elif action_type in ("BRANCH", "IF_CONDITION"):
                cond = step.get("condition")
                win = self._substitute_placeholders(step.get("window_title", self.target_window or ""), context)

                is_true = evaluate_condition(
                    condition=cond,
                    context=context,
                    window_checker=lambda w: SoMGrounder.capture_screen(w) is not None,
                    element_checker=lambda loc, w: UIALocator.is_element_visible(loc, w) or (self._locate_target(loc, w) is not None),
                )
                logger.info("  [Condition %s] Result: %s", step_id, is_true)

                branch_actions = step.get("then_actions", []) if is_true else step.get("else_actions", [])
                if branch_actions:
                    sub_engine = ExportEngine({
                        "id": f"{self.id}__branch",
                        "name": f"{self.name} (Branch)",
                        "tasks": [{"id": "sub_branch", "actions": branch_actions}],
                        "target_window": self.target_window,
                        "executable_path": self.executable_path,
                    })
                    sub_success = sub_engine.execute_actions(
                        context=context,
                        reporter=reporter,
                        depth=depth + 1,
                        dry_run=dry_run,
                    )
                    if not sub_success:
                        logger.error("  [!] Branch execution in %s failed.", step_id)
                        return False

            # 9. EXTRACT_UI_TEXT (Extract Text from UI Element / Label into Context Variable)
            elif action_type == "EXTRACT_UI_TEXT":
                locator = step.get("locator", {})
                win = self._substitute_placeholders(step.get("window_title", self.target_window or ""), context)
                var_name = str(step.get("extract_to_var") or step.get("variable") or step.get("var") or "extracted_ui_text").strip().strip("{}")
                provider = str(step.get("provider", "auto")).lower()
                extracted_text = ""

                # Try native UIA first if available and not explicitly forced to vision
                if provider in ("uia", "auto") and UIALocator.is_available() and locator:
                    extracted_text = UIALocator.get_element_text(locator, win)

                # Fallback to OCR text if UIA returned empty or provider is vision
                if not extracted_text and provider in ("vision", "auto", "ocr"):
                    if locator.get("text"):
                        extracted_text = str(locator.get("text", ""))

                context[var_name] = extracted_text.strip()
                logger.info("  [Action %s] EXTRACT_UI_TEXT: Stored %r -> {%s}", step_id, extracted_text[:100], var_name)

            # 10. VALIDATE_UI_STATE (Validate UI / Context Assertions)
            elif action_type == "VALIDATE_UI_STATE":
                cond = step.get("condition") or step
                win = self._substitute_placeholders(step.get("window_title", self.target_window or ""), context)
                is_valid = evaluate_condition(
                    condition=cond,
                    context=context,
                    window_checker=lambda w: SoMGrounder.capture_screen(w) is not None,
                    element_checker=lambda loc, w: UIALocator.is_element_visible(loc, w) or (self._locate_target(loc, w) is not None),
                )
                if not is_valid:
                    err_msg = f"UI State Validation failed in step {step_id}: {cond}"
                    logger.error("  [!] %s", err_msg)
                    if not handle_action_error(
                        step=step,
                        step_id=step_id,
                        error_msg=err_msg,
                        context=context,
                        save_screenshot_fn=lambda sid, msg: self._save_failure_screenshot(sid, msg, win),
                    ):
                        return False

            # 11. SET_VARIABLE (Dynamically Mutate / Assign Context Variables)
            elif action_type == "SET_VARIABLE":
                var_name = str(step.get("variable") or step.get("var") or step.get("name") or "").strip().strip("{}")
                raw_val = str(step.get("value") or step.get("val") or "")
                if var_name:
                    context[var_name] = self._substitute_placeholders(raw_val, context)
                    logger.info("  [Action %s] SET_VARIABLE: {%s} = %r", step_id, var_name, context[var_name])

            # Optional post-step delay
            delay_ms = int(step.get("delay_ms", 300))
            if delay_ms > 0:
                if not self.interruptible_sleep(delay_ms / 1000.0, reporter=reporter, paused_msg="Skill paused..."):
                    return False

            act_idx += 1

        if reporter:
            reporter(
                TaskProgress(
                    current=total_actions,
                    total=total_actions,
                    message=f"Completed {self.name}",
                    percent=100.0,
                )
            )

        return True

    execute_steps = execute_actions

    def execute(
        self,
        task: SkillTask,
        reporter: Callable[[TaskProgress], None] | None = None,
    ) -> TaskResult:
        context = dict(task.context or {})
        folder_name = context.get("folder_name")
        folder_path = context.get("folder_path")

        from routes.state import DashboardState

        target_base = DashboardState.config.target_base_dir if DashboardState.config else "./Cases"

        try:
            if folder_path or folder_name:
                resolved_folder = (
                    str(folder_path) if folder_path else os.path.abspath(os.path.join(target_base, str(folder_name)))
                )
                success = self.execute_skill_for_folder(resolved_folder, context, reporter)
                return TaskResult(
                    success=success,
                    data={"folder_path": resolved_folder, "status": "completed" if success else "failed"},
                )
            else:
                # Batch execution: find all approved cases
                pending = self.find_pending_cases(target_base)
                if not pending:
                    if reporter:
                        reporter(
                            TaskProgress(
                                current=0,
                                total=0,
                                message="No pending approved cases found for export.",
                                percent=100.0,
                            )
                        )
                    return TaskResult(
                        success=True,
                        data={"pending_count": 0, "message": "No pending cases"},
                    )

                all_ok = True
                for idx, c in enumerate(pending, 1):
                    if not self.wait_for_queue(reporter, "Skill paused..."):
                        logger.info("[*] Batch case execution stopped by queue.")
                        all_ok = False
                        break

                    c_ctx = dict(c.get("parsed_metadata") or {})
                    c_ctx["folder_name"] = c["folder_name"]
                    c_ctx["folder_path"] = c["folder_path"]

                    if not self.execute_skill_for_folder(c["folder_path"], c_ctx, reporter):
                        all_ok = False
                        break

                return TaskResult(
                    success=all_ok,
                    data={"total_cases": len(pending), "status": "completed" if all_ok else "stopped_or_failed"},
                )
        except Exception as e:
            logger.error("[ExportEngine] Execution error: %s", e, exc_info=True)
            return TaskResult(success=False, error=str(e))

    def filter_matching_files(self, folder_path: str, allowed_types: list[str] | None = None) -> list[dict[str, Any]]:
        """Filters PDF files in a case folder according to the skill's allowed document types and loads metadata."""
        from routes.state import DashboardState

        delimiter = DashboardState.config.folder_delimiter if DashboardState.config else "__"
        return _filter_matching_files_fn(folder_path, allowed_types, delimiter=delimiter)

    def find_pending_cases(self, target_base_dir: str) -> list[dict[str, Any]]:
        """Finds all approved case folders with unprocessed files."""
        if not self.enabled:
            return []
        folder_struct = None
        delimiter = "__"
        from routes.state import DashboardState

        if DashboardState.config:
            folder_struct = DashboardState.config.folder_structure
            delimiter = DashboardState.config.folder_delimiter or "__"
        elif self.skill_manager and hasattr(self.skill_manager, "config") and self.skill_manager.config:
            folder_struct = getattr(self.skill_manager.config, "folder_structure", None)

        allowed_types = self.definition.get("document_types", ["*"])
        return _find_pending_cases_fn(
            target_base_dir, self.id, allowed_types, folder_structure=folder_struct, delimiter=delimiter
        )

    def execute_skill_for_folder(
        self,
        folder_path: str,
        context: dict[str, Any] | None = None,
        reporter: Callable[[TaskProgress], None] | None = None,
    ) -> bool:
        """Executes the export steps for all unprocessed matching files in an approved folder and marks each as executed."""
        allowed_types = self.definition.get("document_types", ["*"])
        all_matching = self.filter_matching_files(folder_path, allowed_types)
        matching_files = [f for f in all_matching if self.id not in f.get("executed_skills", [])]

        if not matching_files:
            return True

        all_ok = True
        for f in matching_files:
            if not self.wait_for_queue(reporter, "Skill paused..."):
                logger.info("[*] Skill execution stopped by queue.")
                return False

            file_ctx = dict(context or {})
            file_ctx["folder_path"] = folder_path
            file_ctx["matching_files"] = [mf["fullpath"] for mf in matching_files]

            for k, v in f.get("meta", {}).items():
                if k not in file_ctx:
                    file_ctx[k] = v

            file_ctx["document_fullpath"] = f["fullpath"]
            file_ctx["document_type"] = f["document_type"]
            file_ctx["filename"] = f["filename"]

            if self.execute_steps(file_ctx, reporter=reporter):
                self.mark_file_executed(f["fullpath"])
            else:
                all_ok = False
                break

        return all_ok

    def mark_file_executed(self, filepath: str) -> bool:
        """Updates the .meta sidecar file with this skill ID."""
        return _mark_file_skill_executed_fn(filepath, self.id)

    def mark_file_skill_executed(self, filepath: str, skill_id: str) -> bool:
        """Marks a file with any specified skill ID."""
        return _mark_file_skill_executed_fn(filepath, skill_id)

    def execute_skill(
        self,
        skill_id: str,
        context: dict[str, Any] | None = None,
        depth: int = 0,
        dry_run: bool = False,
    ) -> bool:
        """Executes a skill by ID within the current engine instance context."""
        if depth > 5 or not self.skill_manager:
            return False
        skill_def = self.skill_manager.get_skill(skill_id)
        if not skill_def or not skill_def.get("enabled", True):
            return False

        orig_steps = self.steps
        orig_actions = self.actions
        orig_window = self.target_window
        orig_rdp = self.rdp_prefix
        orig_id = self.id
        orig_name = self.name
        try:
            self.id = str(skill_def.get("id", skill_id))
            self.name = str(skill_def.get("name", self.id))
            raw_tasks = skill_def.get("tasks")
            raw_steps = skill_def.get("steps")
            actions: list[dict[str, Any]] = []
            if isinstance(raw_tasks, list) and raw_tasks:
                for t in raw_tasks:
                    if isinstance(t, dict):
                        for a in t.get("actions", []):
                            if isinstance(a, dict):
                                actions.append(a)
            elif isinstance(raw_steps, list):
                actions = [s for s in raw_steps if isinstance(s, dict)]
            self.steps = actions
            self.actions = actions
            self.target_window = skill_def.get("target_window")
            self.rdp_prefix = skill_def.get("rdp_path_prefix", "")
            return self.execute_actions(context or {}, depth=depth, dry_run=dry_run)
        finally:
            self.steps = orig_steps
            self.actions = orig_actions
            self.target_window = orig_window
            self.rdp_prefix = orig_rdp
            self.id = orig_id
            self.name = orig_name

    def find_pending_cases_for_skill(self, skill_id: str, target_base_dir: str) -> list[dict[str, Any]]:
        """Finds pending cases for any skill ID."""
        if self.id == skill_id:
            return self.find_pending_cases(target_base_dir)
        if self.skill_manager:
            engine = self.skill_manager.get_skill_engine(skill_id, self.vision_extractor)
            if isinstance(engine, ExportEngine):
                return engine.find_pending_cases(target_base_dir)
        return []
