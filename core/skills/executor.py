"""Skill Executor Engine for domain-agnostic UI and RDP step automation."""

import base64
import ctypes
import json
import logging
import os
import re
import sys
import time
from collections.abc import Mapping
from io import BytesIO
from typing import Any, cast

from core.skills.grounder import SoMGrounder
from core.skills.manager import SkillManager
from core.skills.shield import input_shield

logger = logging.getLogger(__name__)

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore[assignment]


def _type_unicode_text(text: str, press_enter: bool = False) -> None:
    """Types unicode characters reliably on Windows using KEYEVENTF_UNICODE without layout or shift bugs."""
    if sys.platform != "win32":
        return

    keybd_event = ctypes.windll.user32.keybd_event  # type: ignore[union-attr]
    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_UNICODE = 0x0004

    for char in text:
        code = ord(char)
        keybd_event(0, code, KEYEVENTF_UNICODE, 0)
        keybd_event(0, code, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0)
        time.sleep(0.008)

    if press_enter:
        time.sleep(0.05)
        keybd_event(0x0D, 0, 0, 0)
        keybd_event(0x0D, 0, KEYEVENTF_KEYUP, 0)


class SkillExecutor:
    """Executes a skill step-by-step in a domain-agnostic manner."""

    def __init__(
        self, skill_manager: SkillManager, vision_extractor: object | None = None
    ):
        self.skill_manager = skill_manager
        self.vision_extractor = vision_extractor

    def _save_failure_screenshot(
        self, step_id: str, desc: str = "", window_title: str | None = None
    ) -> str | None:
        """Captures and saves a diagnostic screenshot when a skill step fails."""
        try:
            screen = SoMGrounder.capture_screen(window_title)
            if screen is None:
                screen = SoMGrounder.capture_screen(None)
            if screen is not None:
                base_dir = os.path.dirname(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                )
                fail_dir = os.path.join(base_dir, "scratch", "rpa_failures")
                os.makedirs(fail_dir, exist_ok=True)
                sanitized_step = re.sub(r"[^\w\-_\.]", "_", step_id)
                filename = f"failure_{int(time.time())}_{sanitized_step}.png"
                target_path = os.path.join(fail_dir, filename)
                screen.save(target_path)
                logger.info("[SkillExecutor] Saved failure screenshot to: %s", target_path)
                return target_path
        except Exception as e:
            logger.debug("[SkillExecutor] Could not save failure screenshot: %s", e)
        return None

    def _substitute_placeholders(self, text: str, context: Mapping[str, object]) -> str:
        """Dynamically substitutes placeholders such as {FieldName} from context without synthetic fallbacks."""
        if not isinstance(text, str) or "{" not in text:
            return text

        def replace_match(match: re.Match) -> str:
            key = match.group(1).strip()
            val = context.get(key)
            return str(val) if val is not None else ""

        return re.sub(r"\{([^{}]+)\}", replace_match, text)

    def _locate_target(
        self, locator: dict[str, object], window_title: str | None = None
    ) -> tuple[int, int] | None:
        """Determines the (x, y) pixel coordinates for a locator with auto-adaptive OCR & VLM fallback."""
        loc_type = str(locator.get("type", "auto"))
        loc_val = str(locator.get("value", "") or locator.get("prompt", "") or locator.get("target", ""))
        prompt = str(locator.get("prompt", "") or locator.get("value", "") or locator.get("target", ""))
        search_term = prompt or loc_val

        screen = SoMGrounder.capture_screen(window_title)
        if not screen:
            logger.error("[SkillExecutor] Screenshot could not be captured.")
            return None

        # 1. Fast OCR Exact/Contains Match (RapidOCR)
        if loc_type in ("auto", "smart", "ocr_exact", "ocr_contains") and search_term:
            from core.extraction_pipeline import _get_rapid_ocr

            engine = _get_rapid_ocr()
            if engine is not None:
                try:
                    img_np = np.array(screen) if np is not None else None
                    if img_np is not None:
                        res, _ = engine(img_np)
                        if res:
                            # Pass 1: Exact match
                            for line in res:
                                box, text, _ = line
                                t = text.strip()
                                if not t:
                                    continue
                                if search_term.lower() == t.lower():
                                    xs = [float(p[0]) for p in box]
                                    ys = [float(p[1]) for p in box]
                                    cx = int(sum(xs) / len(xs))
                                    cy = int(sum(ys) / len(ys))
                                    offset = cast(
                                        list[int], locator.get("offset", [0, 0])
                                    )
                                    return cx + offset[0], cy + offset[1]

                            # Pass 2: Contains match
                            for line in res:
                                box, text, _ = line
                                t = text.strip()
                                if not t:
                                    continue
                                if search_term.lower() in t.lower() or t.lower() in search_term.lower():
                                    xs = [float(p[0]) for p in box]
                                    ys = [float(p[1]) for p in box]
                                    cx = int(sum(xs) / len(xs))
                                    cy = int(sum(ys) / len(ys))
                                    offset = cast(
                                        list[int], locator.get("offset", [0, 0])
                                    )
                                    return cx + offset[0], cy + offset[1]
                except Exception as e:
                    logger.warning("[SkillExecutor] RapidOCR Locator error: %s", e)

        # 2. Set-of-Mark (SoM) Grounding via VLM
        if (loc_type in ("auto", "smart", "som_vlm")) and self.vision_extractor and search_term:
            som_img, candidates = SoMGrounder.generate_som_overlay(screen)
            buf = BytesIO()
            som_img.save(buf, format="JPEG", quality=85)
            b64_som = base64.b64encode(buf.getvalue()).decode("utf-8")

            ground_prompt = (
                f"Interactive UI elements are marked with red badges `[1]`, `[2]`, ... in this image.\n"
                f"Which element number best matches: '{search_term}'?\n"
                f"Reply ONLY with the exact number in square brackets, e.g. `[14]`."
            )
            payload = {
                "messages": [
                    {"role": "user", "content": ground_prompt, "images": [b64_som]}
                ]
            }

            resp = self.vision_extractor.call_vision_api(payload)  # type: ignore[union-attr]
            if resp:
                match = re.search(r"\[(\d+)\]", resp)
                if match:
                    elem_id = int(match.group(1))
                    if elem_id in candidates:
                        target = candidates[elem_id]
                        offset_raw = locator.get("offset")
                        offset_x, offset_y = 0, 0
                        if isinstance(offset_raw, (list, tuple)) and len(offset_raw) >= 2:
                            ox, oy = offset_raw[0], offset_raw[1]
                            if isinstance(ox, (int, float)):
                                offset_x = int(ox)
                            if isinstance(oy, (int, float)):
                                offset_y = int(oy)
                        cx = int(target["center_x"]) if isinstance(target.get("center_x"), (int, float)) else 0  # type: ignore[arg-type]
                        cy = int(target["center_y"]) if isinstance(target.get("center_y"), (int, float)) else 0  # type: ignore[arg-type]
                        return cx + offset_x, cy + offset_y

        logger.warning("[SkillExecutor] Locator could not be resolved: %s", locator)
        return None

    def execute_skill(
        self, skill_id: str, context: dict[str, object], depth: int = 0
    ) -> bool:
        """Executes the skill with the specified context (metadata & paths)."""
        if depth > 5:
            logger.error(
                "[SkillExecutor] Maximum recursion depth reached for CALL_SKILL: %s",
                skill_id,
            )
            return False

        skill = self.skill_manager.get_skill(skill_id)
        if not skill or not skill.get("enabled", True):
            logger.warning(
                "[SkillExecutor] Skill '%s' not found or disabled.", skill_id
            )
            return False

        logger.info(
            "[*] Starting skill '%s' (Depth %d)...", skill.get("name", skill_id), depth
        )
        steps: list[dict[str, object]] = list(skill.get("steps", []))  # type: ignore[arg-type]
        window_title = skill.get("target_window")
        rdp_prefix = skill.get("rdp_path_prefix", "")

        step_idx = 0
        step_map = {
            str(step.get("id")): idx for idx, step in enumerate(steps) if step.get("id")
        }

        while step_idx < len(steps):
            step: dict[str, Any] = steps[step_idx]  # type: ignore[assignment]
            step_id = step.get("id", f"step_{step_idx}")
            action_type = step.get("action_type", "NONE")
            desc = step.get("description", action_type)

            logger.info(
                "  [Step %d/%d] %s: %s", step_idx + 1, len(steps), step_id, desc
            )

            # 1. FOCUS_WINDOW
            if action_type == "FOCUS_WINDOW":
                win_pattern = self._substitute_placeholders(
                    step.get("window_title", window_title or ""), context
                )
                max_retries = int(step.get("max_retries", 5))
                retry_delay_s = float(step.get("retry_delay_s", 1.0))
                screen = None
                for attempt in range(1, max_retries + 1):
                    screen = SoMGrounder.capture_screen(win_pattern)
                    if screen is not None:
                        break
                    if attempt < max_retries:
                        logger.info(
                            "  [Attempt %d/%d] Window '%s' not ready yet, retrying in %.1fs...",
                            attempt,
                            max_retries,
                            win_pattern,
                            retry_delay_s,
                        )
                        time.sleep(retry_delay_s)

                if screen is None and win_pattern:
                    logger.warning(
                        "[SkillExecutor] Window '%s' could not be found or focused in step '%s'.",
                        win_pattern,
                        step_id,
                    )

            # 2. CALL_SKILL (Sub-Skill)
            elif action_type == "CALL_SKILL":
                sub_id = step.get("skill_id")
                if sub_id:
                    success = self.execute_skill(sub_id, context, depth=depth + 1)
                    if not success:
                        logger.error("[!] Sub-skill '%s' failed.", sub_id)
                        return False

            # 3. CLICK / DOUBLE_CLICK
            elif action_type in ("CLICK", "DOUBLE_CLICK"):
                locator = step.get("locator", {})
                loc_copy = dict(locator)
                if "value" in loc_copy:
                    loc_copy["value"] = self._substitute_placeholders(
                        loc_copy["value"], context
                    )
                if "prompt" in loc_copy:
                    loc_copy["prompt"] = self._substitute_placeholders(
                        loc_copy["prompt"], context
                    )

                max_retries = int(step.get("max_retries", 3))
                retry_delay_s = float(step.get("retry_delay_s", 1.0))
                coords = None
                for attempt in range(1, max_retries + 1):
                    coords = self._locate_target(
                        loc_copy,
                        str(window_title) if window_title is not None else None,
                    )
                    if coords:
                        break
                    if attempt < max_retries:
                        logger.info(
                            "  [Attempt %d/%d] Target not found, retrying in %.1fs...",
                            attempt,
                            max_retries,
                            retry_delay_s,
                        )
                        time.sleep(retry_delay_s)

                if coords:
                    cx, cy = coords
                    with input_shield(enabled=True):
                        if sys.platform == "win32":
                            ctypes.windll.user32.SetCursorPos(cx, cy)  # type: ignore[union-attr]
                            time.sleep(0.05)
                            ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)  # type: ignore[union-attr]
                            ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)  # type: ignore[union-attr]
                            if action_type == "DOUBLE_CLICK":
                                time.sleep(0.1)
                                ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)  # type: ignore[union-attr]
                                ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)  # type: ignore[union-attr]
                else:
                    logger.error(
                        "[SkillExecutor] Target for click in step '%s' (%s) not found.",
                        step_id,
                        desc,
                    )
                    self._save_failure_screenshot(
                        step_id,
                        desc,
                        str(window_title) if window_title is not None else None,
                    )
                    return False

            # 4. TYPE_TEXT / TYPE_FILE_PATH
            elif action_type in ("TYPE_TEXT", "TYPE_FILE_PATH"):
                text_to_type = ""
                if action_type == "TYPE_FILE_PATH":
                    raw_path = context.get(
                        "document_fullpath", step.get("file_path", "")
                    )
                    raw_path = self._substitute_placeholders(raw_path, context)  # type: ignore[arg-type]
                    if rdp_prefix and not raw_path.startswith("\\\\"):
                        clean_p = raw_path.replace(":", "").replace("/", "\\")
                        text_to_type = os.path.join(str(rdp_prefix), str(clean_p))
                    else:
                        text_to_type = raw_path
                else:
                    text_to_type = self._substitute_placeholders(
                        step.get("text", ""), context
                    )

                with input_shield(enabled=True):
                    _type_unicode_text(
                        text_to_type, press_enter=bool(step.get("press_enter", False))
                    )

            # 5. VERIFY_SCREEN (Conditional Branching & Fallback Routines)
            elif action_type == "VERIFY_SCREEN":
                locator = step.get("locator", {})
                loc_copy = dict(locator)
                if "value" in loc_copy:
                    loc_copy["value"] = self._substitute_placeholders(
                        loc_copy["value"], context
                    )
                if "prompt" in loc_copy:
                    loc_copy["prompt"] = self._substitute_placeholders(
                        loc_copy["prompt"], context
                    )

                max_retries = int(step.get("max_retries", 2))
                retry_delay_s = float(step.get("retry_delay_s", 1.0))
                found = False
                for attempt in range(1, max_retries + 1):
                    if (
                        self._locate_target(
                            loc_copy,
                            str(window_title) if window_title is not None else None,
                        )
                        is not None
                    ):
                        found = True
                        break
                    if attempt < max_retries:
                        time.sleep(retry_delay_s)

                if not found:
                    on_failure_action = str(step.get("on_failure_action", "")).lower()
                    on_failure_skill = step.get("on_failure_skill")

                    if (on_failure_action == "run_skill" or on_failure_skill) and on_failure_skill:
                        logger.info(
                            "[SkillExecutor] Verification not found on screen. Running fallback routine '%s'...",
                            on_failure_skill,
                        )
                        fallback_ok = self.execute_skill(
                            str(on_failure_skill),
                            context,
                            depth=depth + 1,
                        )
                        if not fallback_ok:
                            logger.error(
                                "[SkillExecutor] Fallback routine '%s' failed.",
                                on_failure_skill,
                            )
                            return False
                    elif on_failure_action == "pause_prompt":
                        logger.warning(
                            "[SkillExecutor] Verification '%s' failed. Pausing execution for human intervention.",
                            step.get("description", step_id),
                        )
                        return False
                    elif on_failure_action == "skip":
                        logger.warning(
                            "[SkillExecutor] Verification '%s' failed. Skipping case.",
                            step.get("description", step_id),
                        )
                        return False

                next_target = (
                    step.get("on_success") if found else step.get("on_failure")
                )
                if next_target and next_target in step_map:
                    step_idx = step_map[next_target]
                    continue

            delay_ms = step.get("delay_ms", 500)
            time.sleep(delay_ms / 1000.0)

            next_step_id = step.get("next_step")
            if next_step_id and next_step_id in step_map:
                step_idx = step_map[next_step_id]
            else:
                step_idx += 1

        logger.info(
            "[+] Skill '%s' completed successfully.", skill.get("name", skill_id)
        )
        return True

    def mark_file_skill_executed(self, filepath: str, skill_id: str) -> bool:
        """Records the successful execution of a skill in the document's .meta sidecar file."""
        meta_path = filepath + ".meta"
        data: dict[str, Any] = {}
        if os.path.exists(meta_path):
            try:
                with open(meta_path, encoding="utf-8") as f:
                    loaded = json.load(f)
                    if isinstance(loaded, dict):
                        data = loaded
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("[SkillExecutor] Could not read .meta before recording skill: %s", e)

        executed_skills = data.get("executed_skills", [])
        if not isinstance(executed_skills, list):
            executed_skills = []
        if skill_id not in executed_skills:
            executed_skills.append(skill_id)
        data["executed_skills"] = executed_skills

        # Also store execution timestamps
        history = data.get("skill_execution_history", {})
        if not isinstance(history, dict):
            history = {}
        history[skill_id] = time.time()
        data["skill_execution_history"] = history

        try:
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info("[SkillExecutor] Marked file '%s' as executed by skill '%s'", filepath, skill_id)
            return True
        except OSError as e:
            logger.error("[SkillExecutor] Failed to write skill execution marker to %s: %s", meta_path, e)
            return False

    def filter_matching_files(
        self, folder_path: str, allowed_types: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """Filters PDF files in a case folder according to the skill's allowed document types and loads metadata."""
        matching_files: list[dict[str, Any]] = []
        if not os.path.exists(folder_path) or not os.path.isdir(folder_path):
            return matching_files

        # Normalize allowed_types
        if (
            not allowed_types
            or "*" in allowed_types
            or "ALL" in [t.upper() for t in allowed_types]
        ):
            allowed_types_clean = None
        else:
            allowed_types_clean = [
                t.strip().lower() for t in allowed_types if t.strip()
            ]

        for fname in sorted(os.listdir(folder_path)):
            if fname.lower().endswith(".pdf"):
                full_path = os.path.join(folder_path, fname)
                meta_path = full_path + ".meta"
                doc_type = "UNKNOWN"
                meta_data: dict[str, Any] = {}

                # Try to read document type and full metadata from .meta file
                if os.path.exists(meta_path):
                    try:
                        with open(meta_path, encoding="utf-8") as f:
                            loaded = json.load(f)
                            if isinstance(loaded, dict):
                                meta_data = loaded
                                doc_type = (
                                    loaded.get("Document")
                                    or loaded.get("Dokument")
                                    or loaded.get("document_type")
                                    or "UNKNOWN"
                                )
                    except (json.JSONDecodeError, OSError):
                        logger.debug(
                            "[SkillExecutor] .meta file could not be read: %s",
                            meta_path,
                        )

                # If no type in .meta, try to infer from filename (Name__Type__Date.pdf)
                if doc_type == "UNKNOWN" and "__" in fname:
                    parts = fname.split("__")
                    if len(parts) >= 2:
                        doc_type = parts[0]

                # Check filter
                if (
                    allowed_types_clean is None
                    or doc_type.lower() in allowed_types_clean
                ):
                    executed_skills = meta_data.get("executed_skills", [])
                    if not isinstance(executed_skills, list):
                        executed_skills = []
                    matching_files.append(
                        {
                            "filename": fname,
                            "fullpath": full_path,
                            "document_type": doc_type,
                            "meta": meta_data,
                            "executed_skills": executed_skills,
                        }
                    )

        return matching_files

    def find_pending_cases_for_skill(
        self, skill_id: str, target_base_dir: str
    ) -> list[dict[str, Any]]:
        """Finds all approved case folders containing matching files that have NOT yet been processed by skill_id."""
        skill = self.skill_manager.get_skill(skill_id)
        if not skill or not skill.get("enabled", True):
            return []

        if not os.path.exists(target_base_dir):
            return []

        allowed_types = skill.get("document_types", ["*"])
        pending_cases: list[dict[str, Any]] = []

        for folder_name in sorted(os.listdir(target_base_dir)):
            folder_path = os.path.join(target_base_dir, folder_name)
            if not os.path.isdir(folder_path):
                continue

            # Must be approved
            if not os.path.exists(os.path.join(folder_path, ".approved")):
                continue

            matching = self.filter_matching_files(folder_path, allowed_types)  # type: ignore[arg-type]
            # Filter files where skill_id has NOT been executed yet
            unprocessed_files = [
                f for f in matching if skill_id not in f.get("executed_skills", [])
            ]

            if unprocessed_files:
                pending_cases.append(
                    {
                        "folder_name": folder_name,
                        "folder_path": folder_path,
                        "matching_files": unprocessed_files,
                        "unprocessed_count": len(unprocessed_files),
                    }
                )

        return pending_cases

    def execute_skill_for_folder(
        self, skill_id: str, folder_path: str, context: dict[str, object] | None = None
    ) -> bool:
        """Executes a skill for an approved folder, merging extracted metadata into context and recording execution."""
        skill = self.skill_manager.get_skill(skill_id)
        if not skill:
            logger.error("[SkillExecutor] Skill '%s' not found.", skill_id)
            return False

        allowed_types = skill.get("document_types", [])
        all_matching = self.filter_matching_files(folder_path, allowed_types)  # type: ignore[arg-type]

        # Process only files that have not yet been executed with this skill
        matching_files = [
            f for f in all_matching if skill_id not in f.get("executed_skills", [])
        ]

        if not matching_files:
            logger.info(
                "[SkillExecutor] No pending un-exported files for skill '%s' in %s.",
                skill_id,
                folder_path,
            )
            # If all were already executed, consider it satisfied
            return True

        base_ctx = dict(context or {})
        base_ctx["folder_path"] = folder_path
        base_ctx["matching_files"] = [f["fullpath"] for f in matching_files]

        # Execution in 'each_file' or 'single_file' mode
        upload_mode = skill.get("upload_mode", "single_file")

        if upload_mode == "each_file":
            all_success = True
            for file_info in matching_files:
                file_ctx = dict(base_ctx)
                # Merge file metadata into context
                for k, v in file_info.get("meta", {}).items():
                    if k not in file_ctx:
                        file_ctx[k] = v

                file_ctx["document_fullpath"] = file_info["fullpath"]
                file_ctx["document_type"] = file_info["document_type"]
                file_ctx["filename"] = file_info["filename"]

                if self.execute_skill(skill_id, file_ctx):
                    self.mark_file_skill_executed(file_info["fullpath"], skill_id)
                else:
                    all_success = False
            return all_success
        else:
            # Single file mode: use the first pending file
            primary_file = matching_files[0]
            for k, v in primary_file.get("meta", {}).items():
                if k not in base_ctx:
                    base_ctx[k] = v

            base_ctx["document_fullpath"] = primary_file["fullpath"]
            base_ctx["document_type"] = primary_file["document_type"]
            base_ctx["filename"] = primary_file["filename"]

            if self.execute_skill(skill_id, base_ctx):
                self.mark_file_skill_executed(primary_file["fullpath"], skill_id)
                return True
            return False
