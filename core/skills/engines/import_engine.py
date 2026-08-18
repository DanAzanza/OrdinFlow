"""Document Pipeline Import Skill Engine."""

from __future__ import annotations

import gc
import logging
import os
from collections.abc import Callable
from typing import Any

from core.skills.base import BaseSkill
from core.skills.models import SkillTask, TaskProgress, TaskResult

logger = logging.getLogger(__name__)

DEFAULT_ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}


class ImportEngine(BaseSkill):
    """Executes document pipeline processing (OCR, Vision VLM classification, splitting, routing)."""

    def __init__(
        self,
        definition: dict[str, Any],
        processor: Any = None,
    ):
        super().__init__(definition)
        self.processor = processor
        self.document_types: dict[str, Any] = dict(definition.get("document_types") or {})
        raw_exts = definition.get("allowed_extensions")
        self.allowed_extensions = set(raw_exts) if raw_exts else DEFAULT_ALLOWED_EXTENSIONS

    def _get_processor(self):
        if self.processor is not None:
            return self.processor
        from routes.state import DashboardState

        return DashboardState.processor

    def _wait_for_queue(
        self,
        reporter: Callable[[TaskProgress], None] | None = None,
        paused_msg: str = "Processing paused...",
    ) -> bool:
        """Blocks while SkillQueueManager is paused. Returns False if execution was stopped."""
        try:
            from core.skills.queue import get_skill_queue_manager

            qm = get_skill_queue_manager()
            if not qm.is_running and not qm.is_paused:
                return True
            if qm.is_stopped:
                return False
            was_paused = False
            while qm.is_paused and not qm.is_stopped:
                if not was_paused and reporter:
                    reporter(TaskProgress(message=f"⏸️ {paused_msg}"))
                    was_paused = True
                qm.wait_if_paused()
            return not qm.is_stopped
        except Exception:
            return True

    def execute(
        self,
        task: SkillTask,
        reporter: Callable[[TaskProgress], None] | None = None,
    ) -> TaskResult:
        """Executes document import and AI routing."""
        processor = self.processor
        if not processor:
            from routes.state import DashboardState

            processor = DashboardState.processor

        if not processor:
            return TaskResult(
                success=False,
                error="DocumentProcessor not initialized in DashboardState.",
            )

        # Temporarily apply document types from this specific skill if defined
        original_doc_types = processor.config.document_types
        if self.document_types:
            processor.config.document_types = self.document_types

        try:
            filepath = task.context.get("filepath")
            if filepath and isinstance(filepath, str) and os.path.isfile(filepath):
                # Single file execution
                if not self._wait_for_queue(reporter, f"Paused before {os.path.basename(filepath)}"):
                    return TaskResult(success=False, error="Execution stopped.")

                if reporter:
                    reporter(
                        TaskProgress(
                            current=1,
                            total=1,
                            message=f"Processing {os.path.basename(filepath)}",
                            percent=50.0,
                        )
                    )

                logger.info("[ImportEngine] Processing single file: %s", filepath)
                processor.wait_if_paused()
                processor.process_and_route_file(filepath)
                gc.collect()

                if reporter:
                    reporter(
                        TaskProgress(
                            current=1,
                            total=1,
                            message=f"Completed {os.path.basename(filepath)}",
                            percent=100.0,
                        )
                    )

                return TaskResult(
                    success=True,
                    data={"processed_files": [filepath], "count": 1},
                )
            else:
                # Batch inbox scan execution
                watch_dir = processor.config.watch_dir
                if not os.path.exists(watch_dir):
                    return TaskResult(
                        success=True,
                        data={"processed_files": [], "count": 0, "message": "Watch directory does not exist."},
                    )

                unprocessed_files: list[str] = []
                for root, dirs, files in os.walk(watch_dir, topdown=True):
                    dirs.sort()
                    for f in sorted(files):
                        fp = os.path.abspath(os.path.join(root, f))
                        if not os.path.isfile(fp) or f.endswith(".meta"):
                            continue
                        if os.path.splitext(f.lower())[1] not in self.allowed_extensions:
                            continue
                        if os.path.exists(fp + ".meta"):
                            continue
                        unprocessed_files.append(fp)

                total = len(unprocessed_files)
                if total == 0:
                    if reporter:
                        reporter(
                            TaskProgress(
                                current=0,
                                total=0,
                                message="Inbox clear (no unprocessed files).",
                                percent=100.0,
                            )
                        )
                    return TaskResult(
                        success=True,
                        data={"processed_files": [], "count": 0, "message": "No files found."},
                    )

                processed: list[str] = []
                for idx, fp in enumerate(unprocessed_files, 1):
                    fname = os.path.basename(fp)
                    if not self._wait_for_queue(reporter, f"Paused before ({idx}/{total}): {fname}"):
                        logger.info("[ImportEngine] Batch execution stopped by user request.")
                        break

                    processor.wait_if_paused()
                    if reporter:
                        pct = round(((idx - 1) / total) * 100, 1)
                        reporter(
                            TaskProgress(
                                current=idx,
                                total=total,
                                message=f"Processing ({idx}/{total}): {fname}",
                                percent=pct,
                            )
                        )

                    try:
                        processor.process_and_route_file(fp)
                        processed.append(fp)
                    except Exception as e:
                        logger.error("[ImportEngine] Error processing file %s: %s", fname, e, exc_info=True)
                    finally:
                        gc.collect()

                if reporter:
                    reporter(
                        TaskProgress(
                            current=total,
                            total=total,
                            message=f"Completed {len(processed)} of {total} document(s).",
                            percent=100.0,
                        )
                    )

                return TaskResult(
                    success=True,
                    data={"processed_files": processed, "count": len(processed), "total_found": total},
                )

        except Exception as e:
            logger.error("[ImportEngine] Execution failure: %s", e, exc_info=True)
            return TaskResult(success=False, error=str(e))
        finally:
            # Restore original document types
            processor.config.document_types = original_doc_types
