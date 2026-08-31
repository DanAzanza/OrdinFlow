"""Loop and Iteration Execution Engine for OrdinFlow RPA Skills.

Handles FOR_EACH_DOCUMENT (case-centric document loops), generic FOR_EACH collections,
and guarded WHILE_LOOP polling actions with iteration caps and failure policies.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
import time
from collections.abc import Callable, Mapping
from typing import Any

from core.skills.case_router import filter_matching_files, mark_file_skill_executed
from core.skills.condition_evaluator import evaluate_condition
from core.skills.models import TaskProgress
from core.utils import is_within_allowed_roots, sanitize_safe_path

logger = logging.getLogger(__name__)

MAX_LOOP_ITERATIONS = 50
MAX_BRANCH_DEPTH = 5


def has_for_each_document(skill_def: Mapping[str, Any]) -> bool:
    """Checks whether the skill definition contains a FOR_EACH_DOCUMENT action."""
    if not isinstance(skill_def, dict):
        return False

    def _walk_actions(actions: list[dict[str, Any]]) -> bool:
        for act in actions:
            if not isinstance(act, dict):
                continue
            act_type = str(act.get("action_type") or act.get("type", "")).upper()
            if act_type == "FOR_EACH_DOCUMENT":
                return True
            if act_type in ("BRANCH", "IF_CONDITION"):
                if _walk_actions(act.get("then_actions", [])) or _walk_actions(act.get("else_actions", [])):
                    return True
            if act_type in ("FOR_EACH", "WHILE_LOOP"):
                if _walk_actions(act.get("actions", [])):
                    return True
        return False

    for task in skill_def.get("tasks", []):
        if isinstance(task, dict) and _walk_actions(task.get("actions", [])):
            return True

    for step in skill_def.get("steps", []) + skill_def.get("actions", []):
        if isinstance(step, dict) and _walk_actions([step]):
            return True

    return False


def execute_for_each_document(
    step: Mapping[str, Any],
    skill_id: str,
    context: dict[str, Any],
    sub_executor_fn: Callable[[list[dict[str, Any]], dict[str, Any], int], bool],
    depth: int = 0,
    dry_run: bool = False,
    reporter: Callable[[TaskProgress], None] | None = None,
    wait_for_queue_fn: Callable[..., bool] | None = None,
) -> bool:
    """Executes child actions for all unexecuted matching documents in the case folder."""
    if depth >= MAX_BRANCH_DEPTH:
        logger.error("[LoopRunner] Maximum loop/recursion depth (%d) exceeded.", MAX_BRANCH_DEPTH)
        return False

    raw_folder = str(context.get("folder_path") or "").strip()
    is_safe_folder, clean_folder = sanitize_safe_path(raw_folder)
    folder_path = ""
    if is_safe_folder and clean_folder and is_within_allowed_roots(clean_folder):
        resolved_folder = Path(clean_folder).resolve()
        if resolved_folder.is_dir():
            folder_path = str(resolved_folder)

    if not folder_path:
        # If single document was provided without folder, treat as single item iteration
        raw_doc = str(context.get("document_fullpath") or "").strip()
        is_safe_doc, clean_doc = sanitize_safe_path(raw_doc)
        if is_safe_doc and clean_doc and is_within_allowed_roots(clean_doc):
            resolved_doc = Path(clean_doc).resolve()
            if resolved_doc.is_file():
                folder_path = str(resolved_doc.parent)

    if not folder_path:
        logger.error("[LoopRunner] FOR_EACH_DOCUMENT requires a valid folder_path or document_fullpath in context.")
        return False

    allowed_types = step.get("document_types") or step.get("allowed_types") or ["*"]
    if isinstance(allowed_types, str):
        allowed_types = [allowed_types]

    matching = filter_matching_files(folder_path, allowed_types)
    unexecuted_docs = [f for f in matching if skill_id not in f.get("executed_skills", [])]

    if not unexecuted_docs:
        logger.info("[LoopRunner] No unexecuted documents matching %s in '%s'.", allowed_types, folder_path)
        return True

    loop_actions = step.get("actions") or step.get("then_actions") or []
    if not isinstance(loop_actions, list) or not loop_actions:
        logger.warning("[LoopRunner] FOR_EACH_DOCUMENT action %s has no nested actions.", step.get("id"))
        return True

    on_item_error = str(step.get("on_item_error") or step.get("on_error") or "ABORT").upper()
    total_docs = len(unexecuted_docs)
    all_success = True

    logger.info("[LoopRunner] Starting FOR_EACH_DOCUMENT on %d doc(s) in '%s'.", total_docs, folder_path)

    for idx, doc in enumerate(unexecuted_docs, start=1):
        if wait_for_queue_fn and not wait_for_queue_fn(reporter, "Skill paused during document loop..."):
            logger.info("[LoopRunner] Execution paused/stopped by queue.")
            return False

        doc_ctx = dict(context)
        doc_ctx["document_fullpath"] = doc["fullpath"]
        doc_ctx["document_filename"] = doc["filename"]
        doc_ctx["document_name"] = os.path.splitext(doc["filename"])[0]
        doc_ctx["document_type"] = doc["document_type"]
        doc_ctx["category"] = doc["document_type"]
        doc_ctx["doc_index"] = idx
        doc_ctx["total_docs"] = total_docs

        for k, v in doc.get("meta", {}).items():
            if k not in doc_ctx:
                doc_ctx[k] = v

        if reporter:
            msg = f"Document {idx}/{total_docs}: {doc['filename']}"
            pct = int((idx / total_docs) * 100)
            reporter(TaskProgress(current=idx, total=total_docs, percent=pct, message=msg))

        doc_success = sub_executor_fn(loop_actions, doc_ctx, depth + 1)

        for k, v in doc_ctx.items():
            if k not in (
                "document_fullpath",
                "document_filename",
                "document_name",
                "document_type",
                "doc_index",
                "total_docs",
            ):
                context[k] = v

        if doc_success:
            if not dry_run:
                mark_file_skill_executed(doc["fullpath"], skill_id)
            logger.info("[LoopRunner] Successfully processed & marked doc %d/%d: %s", idx, total_docs, doc["filename"])
        else:
            all_success = False
            logger.error("[LoopRunner] Failed processing doc %d/%d: %s (Policy: %s)", idx, total_docs, doc["filename"], on_item_error)
            if on_item_error == "ABORT":
                return False
            elif on_item_error == "RETRY":
                # Retry once
                time.sleep(1.0)
                retry_ok = sub_executor_fn(loop_actions, doc_ctx, depth + 1)
                for k, v in doc_ctx.items():
                    if k not in (
                        "document_fullpath",
                        "document_filename",
                        "document_name",
                        "document_type",
                        "doc_index",
                        "total_docs",
                    ):
                        context[k] = v
                if retry_ok:
                    if not dry_run:
                        mark_file_skill_executed(doc["fullpath"], skill_id)
                    all_success = True
                else:
                    return False

    return all_success


def execute_for_each_collection(
    step: Mapping[str, Any],
    context: dict[str, Any],
    sub_executor_fn: Callable[[list[dict[str, Any]], dict[str, Any], int], bool],
    depth: int = 0,
    reporter: Callable[[TaskProgress], None] | None = None,
    wait_for_queue_fn: Callable[..., bool] | None = None,
) -> bool:
    """Iterates over a list variable in context, injecting item and index into child steps."""
    if depth >= MAX_BRANCH_DEPTH:
        return False

    var_name = str(step.get("collection_var") or step.get("variable") or "").strip("{} ")
    items = context.get(var_name, [])
    if not isinstance(items, list) or not items:
        logger.info("[LoopRunner] FOR_EACH collection '%s' is empty or not a list.", var_name)
        return True

    loop_actions = step.get("actions", [])
    if not isinstance(loop_actions, list) or not loop_actions:
        return True

    item_var_name = str(step.get("item_var") or "item").strip("{} ")
    total_items = min(len(items), MAX_LOOP_ITERATIONS)

    for idx, itm in enumerate(items[:total_items], start=1):
        if wait_for_queue_fn and not wait_for_queue_fn(reporter, "Skill paused during loop..."):
            return False

        iter_ctx = dict(context)
        iter_ctx[item_var_name] = itm
        iter_ctx["@index"] = idx
        iter_ctx["item_index"] = idx
        iter_ctx["@total"] = total_items
        iter_ctx["item_total"] = total_items
        iter_ctx["@first"] = idx == 1
        iter_ctx["@last"] = idx == total_items

        sub_ok = sub_executor_fn(loop_actions, iter_ctx, depth + 1)
        for k, v in iter_ctx.items():
            if k not in ("@index", "@total", "@first", "@last", "item_index", "item_total", item_var_name):
                context[k] = v

        if not sub_ok:
            if step.get("on_item_error", "ABORT").upper() == "ABORT":
                return False

    return True


def execute_while_loop(
    step: Mapping[str, Any],
    context: dict[str, Any],
    sub_executor_fn: Callable[[list[dict[str, Any]], dict[str, Any], int], bool],
    window_checker: Callable[[str], bool] | None = None,
    element_checker: Callable[[Mapping[str, Any], str], bool] | None = None,
    depth: int = 0,
    reporter: Callable[[TaskProgress], None] | None = None,
    wait_for_queue_fn: Callable[..., bool] | None = None,
) -> bool:
    """Repeats child actions while a condition evaluates to True, up to max_iterations."""
    if depth >= MAX_BRANCH_DEPTH:
        return False

    cond = step.get("condition")
    loop_actions = step.get("actions", [])
    if not cond or not isinstance(loop_actions, list) or not loop_actions:
        return True

    max_iters = min(int(step.get("max_iterations", MAX_LOOP_ITERATIONS)), MAX_LOOP_ITERATIONS)
    poll_delay_s = float(step.get("poll_delay_s", 0.3))

    for iteration in range(1, max_iters + 1):
        if wait_for_queue_fn and not wait_for_queue_fn(reporter, "Skill paused during while loop..."):
            return False

        is_true = evaluate_condition(
            condition=cond,
            context=context,
            window_checker=window_checker,
            element_checker=element_checker,
        )

        if not is_true:
            logger.info("[LoopRunner] WHILE_LOOP condition '%s' became False after %d iterations.", cond, iteration - 1)
            return True

        iter_ctx = dict(context)
        iter_ctx["@iteration"] = iteration

        sub_ok = sub_executor_fn(loop_actions, iter_ctx, depth + 1)
        for k, v in iter_ctx.items():
            if k != "@iteration":
                context[k] = v

        if not sub_ok:
            if step.get("on_item_error", "ABORT").upper() == "ABORT":
                return False

        if poll_delay_s > 0:
            time.sleep(poll_delay_s)

    logger.warning("[LoopRunner] WHILE_LOOP reached max iterations limit (%d) without condition flipping to False.", max_iters)
    return True
