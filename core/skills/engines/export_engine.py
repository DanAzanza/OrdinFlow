"""Robotic Process Automation (RPA) Export Skill Engine."""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Callable, Mapping
from typing import Any

from core.skills.base import BaseSkill
from core.skills.grounder import SoMGrounder
from core.skills.models import SkillTask, TaskProgress, TaskResult
from core.skills.shield import input_shield
from core.skills.case_router import (
    extract_all_skill_document_types as _extract_all_skill_document_types_fn,
    filter_matching_files as _filter_matching_files_fn,
    find_pending_cases as _find_pending_cases_fn,
    mark_file_skill_executed as _mark_file_skill_executed_fn,
)
from core.skills.loop_runner import (
    execute_for_each_collection,
    execute_for_each_document,
    execute_while_loop,
    has_for_each_document,
)
from core.skills.action_executor import (
    execute_focus_window,
    execute_mouse_click,
    execute_type_file_path,
    execute_type_text,
    execute_wait_for_element,
)
from core.skills.text_helpers import (
    send_hotkey as _send_hotkey,
    substitute_placeholders as _substitute_placeholders_fn,
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

logger = logging.getLogger(__name__)


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

    def _locate_target(self, locator: Mapping[str, Any], window_title: str | None = None) -> tuple[int, int] | None:
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
                ready = execute_focus_window(
                    step=step,
                    context=context,
                    default_target_window=self.target_window,
                    launch_skill_id=self.launch_skill_id,
                    executable_path=self.executable_path,
                    default_maximize=self.maximize_window,
                    substitute_fn=self._substitute_placeholders,
                    execute_skill_fn=self.execute_skill,
                    is_cancelled_fn=lambda: not self.wait_for_queue(),
                )
                if not ready and step.get("window_title"):
                    logger.warning("[ExportEngine] Window '%s' could not be readied in step '%s'.", step.get("window_title"), step_id)

            # 2. CLICK / DOUBLE_CLICK / RIGHT_CLICK
            elif action_type in ("CLICK", "DOUBLE_CLICK", "RIGHT_CLICK"):
                if not execute_mouse_click(
                    step=step,
                    step_id=step_id,
                    action_type=action_type,
                    context=context,
                    target_window=self.target_window,
                    substitute_fn=self._substitute_placeholders,
                    locate_fn=self._locate_target,
                    wait_for_queue_fn=lambda: self.wait_for_queue(reporter, "Skill paused..."),
                    sleep_fn=lambda s: self.interruptible_sleep(s, reporter=reporter, paused_msg="Skill paused..."),
                ):
                    return False

            # 3. TYPE_TEXT / PASTE_CLIPBOARD
            elif action_type in ("TYPE_TEXT", "PASTE_CLIPBOARD"):
                if not execute_type_text(
                    step=step,
                    step_id=step_id,
                    action_type=action_type,
                    context=context,
                    substitute_fn=self._substitute_placeholders,
                ):
                    return False

            # 4. TYPE_FILE_PATH (Instant Clipboard Paste + Security Gate + Fail-Fast Validation)
            elif action_type == "TYPE_FILE_PATH":
                if not execute_type_file_path(
                    step=step,
                    step_id=step_id,
                    context=context,
                    target_window=self.target_window,
                    rdp_prefix=self.rdp_prefix,
                    substitute_fn=self._substitute_placeholders,
                ):
                    return False

            # 5. WAIT_FOR_ELEMENT (Dynamic Waiting / Smart Polling)
            elif action_type == "WAIT_FOR_ELEMENT":
                found = execute_wait_for_element(
                    step=step,
                    context=context,
                    target_window=self.target_window,
                    substitute_fn=self._substitute_placeholders,
                    locate_fn=self._locate_target,
                    wait_for_queue_fn=lambda: self.wait_for_queue(reporter, "Skill paused..."),
                    sleep_fn=lambda s: self.interruptible_sleep(s, reporter=reporter, paused_msg="Skill paused..."),
                )
                if not found:
                    if not self.wait_for_queue():
                        return False
                    logger.warning("[ExportEngine] WAIT_FOR_ELEMENT timed out for %s", step.get("locator"))
                    on_fail = step.get("on_failure", "stop")
                    if on_fail == "stop":
                        win = self._substitute_placeholders(step.get("window_title", self.target_window or ""), context)
                        self._save_failure_screenshot(step_id, f"Wait Timeout: {step.get('locator')}", win)
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
                    if not self._execute_nested_actions(branch_actions, context, depth + 1, dry_run, reporter):
                        logger.error("  [!] Branch execution in %s failed.", step_id)
                        return False

            # 9. FOR_EACH_DOCUMENT (Case-Centric Document Loop)
            elif action_type == "FOR_EACH_DOCUMENT":
                if not execute_for_each_document(
                    step=step,
                    skill_id=self.id,
                    context=context,
                    sub_executor_fn=lambda acts, ctx, d: self._execute_nested_actions(acts, ctx, d, dry_run, reporter),
                    depth=depth,
                    dry_run=dry_run,
                    reporter=reporter,
                    wait_for_queue_fn=self.wait_for_queue,
                ):
                    logger.error("  [!] FOR_EACH_DOCUMENT loop in %s failed or aborted.", step_id)
                    return False

            # 10. FOR_EACH (Generic Collection Iteration)
            elif action_type == "FOR_EACH":
                if not execute_for_each_collection(
                    step=step,
                    context=context,
                    sub_executor_fn=lambda acts, ctx, d: self._execute_nested_actions(acts, ctx, d, dry_run, reporter),
                    depth=depth,
                    reporter=reporter,
                    wait_for_queue_fn=self.wait_for_queue,
                ):
                    return False

            # 11. WHILE_LOOP (Guarded Polling Loop)
            elif action_type == "WHILE_LOOP":
                win = self._substitute_placeholders(step.get("window_title", self.target_window or ""), context)
                if not execute_while_loop(
                    step=step,
                    context=context,
                    sub_executor_fn=lambda acts, ctx, d: self._execute_nested_actions(acts, ctx, d, dry_run, reporter),
                    window_checker=lambda w: SoMGrounder.capture_screen(w) is not None,
                    element_checker=lambda loc, w: UIALocator.is_element_visible(loc, w) or (self._locate_target(loc, w) is not None),
                    depth=depth,
                    reporter=reporter,
                    wait_for_queue_fn=self.wait_for_queue,
                ):
                    return False

            # 12. EXTRACT_UI_TEXT (Extract Text from UI Element / Label into Context Variable)
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

            # 13. VALIDATE_UI_STATE (Validate UI / Context Assertions)
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
                        save_screenshot_fn=lambda sid, msg, target_win=win: self._save_failure_screenshot(sid, msg, target_win),
                    ):
                        return False

            # 14. SET_VARIABLE (Dynamically Mutate / Assign Context Variables)
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
                for _idx, c in enumerate(pending, 1):
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

    def _execute_nested_actions(
        self,
        actions: list[dict[str, Any]],
        context: dict[str, Any],
        depth: int,
        dry_run: bool,
        reporter: Callable[[TaskProgress], None] | None,
    ) -> bool:
        """Executes a nested sub-list of actions within the same target window context."""
        sub_engine = ExportEngine({
            "id": f"{self.id}__nested",
            "name": f"{self.name} (Nested)",
            "tasks": [{"id": "sub_nested", "actions": actions}],
            "target_window": self.target_window,
            "executable_path": self.executable_path,
        })
        return sub_engine.execute_actions(
            context=context,
            reporter=reporter,
            depth=depth,
            dry_run=dry_run,
        )

    def get_target_document_types(self) -> list[str]:
        """Returns all aggregated document types targeted by this skill, including nested loops."""
        return _extract_all_skill_document_types_fn(self.definition)

    def filter_matching_files(self, folder_path: str, allowed_types: list[str] | None = None) -> list[dict[str, Any]]:
        """Filters PDF files in a case folder according to the skill's allowed document types and loads metadata."""
        from routes.state import DashboardState

        delimiter = DashboardState.config.folder_delimiter if DashboardState.config else "__"
        types_to_use = allowed_types or self.get_target_document_types()
        return _filter_matching_files_fn(folder_path, types_to_use, delimiter=delimiter)

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

        allowed_types = self.get_target_document_types()
        return _find_pending_cases_fn(
            target_base_dir, self.id, allowed_types, folder_structure=folder_struct, delimiter=delimiter
        )

    def execute_skill_for_folder(
        self,
        folder_path: str,
        context: dict[str, Any] | None = None,
        reporter: Callable[[TaskProgress], None] | None = None,
    ) -> bool:
        """Executes the export steps for an approved folder in case-centric or legacy file-centric mode."""
        allowed_types = self.get_target_document_types()
        all_matching = self.filter_matching_files(folder_path, allowed_types)
        matching_files = [f for f in all_matching if self.id not in f.get("executed_skills", [])]

        if not matching_files:
            return True

        # CASE-CENTRIC MODE: If skill contains FOR_EACH_DOCUMENT, execute skill ONCE for folder
        if has_for_each_document(self.definition):
            case_ctx = dict(context or {})
            case_ctx["folder_path"] = folder_path
            case_ctx["matching_files"] = [mf["fullpath"] for mf in matching_files]
            if matching_files:
                first_meta = matching_files[0].get("meta", {})
                for k, v in first_meta.items():
                    if k not in case_ctx:
                        case_ctx[k] = v
                case_ctx.setdefault("document_fullpath", matching_files[0]["fullpath"])
                case_ctx.setdefault("filename", matching_files[0]["filename"])
                case_ctx.setdefault("document_type", matching_files[0]["document_type"])

            return self.execute_steps(case_ctx, reporter=reporter)

        # LEGACY FILE-CENTRIC MODE: Run all steps per matching file
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
