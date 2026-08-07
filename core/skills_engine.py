"""
OrdinFlow — Skills Execution & Automation Engine
Fully domain- and data-agnostic system for executing desktop/RDP automations.
"""

import atexit
import base64
import ctypes
import glob
import json
import logging
import os
import re
import sys
import threading
import time
from collections.abc import Mapping
from contextlib import contextmanager
from io import BytesIO
from typing import Any, cast

import yaml
from PIL import Image, ImageDraw, ImageFont, ImageGrab

logger = logging.getLogger(__name__)

_block_input_active = False

try:
    import cv2  # type: ignore[import-untyped]
    import numpy as np
except ImportError:
    cv2 = None  # type: ignore[assignment]
    np = None  # type: ignore[assignment]

# CRASH-SAFE INPUT SHIELD (BlockInput)


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
    global _block_input_active
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


# SET-OF-MARK (SoM) PREPROCESSOR FOR VLM GROUNDING


class SoMGrounder:
    """Generates Set-of-Mark overlays for screen captures to enable precise VLM clicking."""

    @staticmethod
    def capture_screen(window_title: str | None = None) -> Image.Image | None:
        """Captures a screenshot of the entire screen or focuses the target window title."""
        if window_title and sys.platform == "win32":
            try:
                hwnd = ctypes.windll.user32.FindWindowW(None, window_title)  # type: ignore[union-attr]
                if not hwnd:
                    # Try partial match
                    found: list[int] = []

                    def enum_windows_proc(h: int, _lparam: int) -> bool:
                        length = ctypes.windll.user32.GetWindowTextLengthW(h)  # type: ignore[union-attr]
                        if length > 0:
                            buff = ctypes.create_unicode_buffer(length + 1)
                            ctypes.windll.user32.GetWindowTextW(h, buff, length + 1)  # type: ignore[union-attr]
                            if (
                                window_title.lower().replace("*", "")
                                in buff.value.lower()
                            ):
                                found.append(h)
                        return True

                    cb = ctypes.WINFUNCTYPE(
                        ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p
                    )(enum_windows_proc)
                    ctypes.windll.user32.EnumWindows(cb, 0)
                    if found:
                        hwnd = found[0]

                if hwnd:
                    ctypes.windll.user32.SetForegroundWindow(hwnd)  # type: ignore[union-attr]
                    time.sleep(0.2)
            except OSError as e:
                logger.warning(
                    "[SoMGrounder] Error focusing window '%s': %s", window_title, e
                )

        if ImageGrab is not None:
            try:
                return ImageGrab.grab()  # type: ignore[attr-defined]
            except OSError as e:
                logger.error("[SoMGrounder] Screenshot via ImageGrab failed: %s", e)
        return None

    @staticmethod
    def generate_som_overlay(
        img: Image.Image,
    ) -> tuple[Image.Image, dict[int, dict[str, int | list[int]]]]:
        """Segments the image into candidate UI bounding boxes and draws numbered badges [1], [2], ...

        Returns: (som_image, candidates_map)
        candidates_map[id] = {"center_x": int, "center_y": int, "bbox": [x1, y1, x2, y2]}
        """
        candidates_map: dict[int, dict[str, int | list[int]]] = {}
        som_img = img.copy()
        draw = ImageDraw.Draw(som_img, "RGBA")

        boxes: list[tuple[int, int, int, int]] = []

        # 1. RapidOCR Bounding Boxes (ONNX Engine)
        from core.extraction_pipeline import _get_rapid_ocr

        engine = _get_rapid_ocr()
        if engine is not None:
            try:
                img_np = np.array(img) if np is not None else None
                if img_np is not None:
                    res, _ = engine(img_np)
                    if res:
                        for line in res:
                            box = line[0]
                            xs = [p[0] for p in box]
                            ys = [p[1] for p in box]
                            w = max(xs) - min(xs)
                            h = max(ys) - min(ys)
                            if w > 15 and h > 8:
                                boxes.append(
                                    (
                                        int(min(xs)),
                                        int(min(ys)),
                                        int(max(xs)),
                                        int(max(ys)),
                                    )
                                )
            except Exception as e:
                logger.debug("[SoMGrounder] RapidOCR box extraction skipped: %s", e)

        # 2. Contour detection via OpenCV (for textless buttons & icons)
        if cv2 is not None and np is not None:
            try:
                open_cv_image = np.array(img.convert("RGB"))
                gray = cv2.cvtColor(open_cv_image, cv2.COLOR_RGB2GRAY)
                blur = cv2.GaussianBlur(gray, (3, 3), 0)
                thresh = cv2.adaptiveThreshold(
                    blur,
                    255,
                    cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                    cv2.THRESH_BINARY_INV,
                    11,
                    2,
                )
                contours, _ = cv2.findContours(
                    thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
                )

                for cnt in contours:
                    x, y, w, h = cv2.boundingRect(cnt)
                    if 15 < w < img.width * 0.8 and 12 < h < img.height * 0.8:
                        boxes.append((x, y, x + w, y + h))
            except Exception as e:
                logger.debug("[SoMGrounder] Contour extraction skipped: %s", e)

        # Non-Maximum Suppression / Overlap Filtering
        filtered_boxes: list[tuple[int, int, int, int]] = []
        for box in boxes:
            x1, y1, x2, y2 = box
            overlap = False
            for fb in filtered_boxes:
                fx1, fy1, _fx2, _fy2 = fb
                # Check overlap
                if abs(x1 - fx1) < 20 and abs(y1 - fy1) < 15:
                    overlap = True
                    break
            if not overlap:
                filtered_boxes.append(box)

        # Max 80 elements per screenshot to avoid overloading the VLM
        filtered_boxes = filtered_boxes[:80]

        # Draw Numbered Badges
        try:
            font = ImageFont.load_default()
        except OSError:
            font = None

        for idx, (x1, y1, x2, y2) in enumerate(filtered_boxes, start=1):
            cx = (x1 + x2) // 2
            cy = (y1 + y2) // 2
            candidates_map[idx] = {
                "center_x": cx,
                "center_y": cy,
                "bbox": [x1, y1, x2, y2],
            }

            # Draw translucent box & badge
            draw.rectangle([x1, y1, x2, y2], outline=(255, 0, 0, 180), width=2)
            badge_text = f"[{idx}]"
            badge_w = len(badge_text) * 7 + 4
            badge_h = 14
            draw.rectangle(
                [x1, max(0, y1 - badge_h), x1 + badge_w, y1], fill=(255, 0, 0, 220)
            )
            draw.text(
                (x1 + 2, max(0, y1 - badge_h) + 1),
                badge_text,
                fill=(255, 255, 255, 255),
                font=font,
            )

        return som_img, candidates_map


# SKILL MANAGER (YAML STORAGE)


class SkillManager:
    """Manages loading, saving, deleting, and duplicating skill YAML files."""

    def __init__(self, skills_dir: str = "./settings/skills"):
        self.skills_dir = os.path.abspath(skills_dir)
        os.makedirs(self.skills_dir, exist_ok=True)

    def list_skills(self) -> list[dict[str, Any]]:
        """Loads all skills from the skills/ directory."""
        skills: list[dict[str, Any]] = []
        yaml_files = glob.glob(os.path.join(self.skills_dir, "*.yaml")) + glob.glob(
            os.path.join(self.skills_dir, "*.yml")
        )
        for filepath in sorted(yaml_files):
            try:
                with open(filepath, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                    if isinstance(data, dict) and "id" in data:
                        skills.append(data)
            except OSError as e:
                logger.error("[SkillManager] Error reading %s: %s", filepath, e)
        return skills

    def get_skill(self, skill_id: str) -> dict[str, Any] | None:
        """Finds a skill by ID."""
        for skill in self.list_skills():
            if skill.get("id") == skill_id:
                return skill
        return None

    def save_skill(self, skill_data: dict[str, Any]) -> str:
        """Saves a skill to its individual YAML file."""
        skill_id = skill_data.get("id", "").strip()  # type: ignore[union-attr]
        if not skill_id:
            name_slug = re.sub(
                r"[^a-z0-9_]", "_", skill_data.get("name", "unnamed").lower()
            )  # type: ignore[arg-type]
            skill_id = f"skill_{name_slug}_{int(time.time())}"
            skill_data["id"] = skill_id

        filepath = os.path.join(self.skills_dir, f"{skill_id}.yaml")
        with open(filepath, "w", encoding="utf-8") as f:
            yaml.safe_dump(skill_data, f, allow_unicode=True, sort_keys=False)
        logger.info("[SkillManager] Skill '%s' saved to %s", skill_id, filepath)
        return skill_id

    def delete_skill(self, skill_id: str) -> bool:
        """Deletes a skill's YAML file."""
        filepath = os.path.join(self.skills_dir, f"{skill_id}.yaml")
        if os.path.exists(filepath):
            os.remove(filepath)
            logger.info("[SkillManager] Skill '%s' deleted.", skill_id)
            return True
        return False

    def duplicate_skill(self, skill_id: str) -> dict[str, Any] | None:
        """Duplicates an existing skill."""
        original = self.get_skill(skill_id)
        if not original:
            return None

        new_data = dict(original)
        new_id = f"{skill_id}_copy_{int(time.time()) % 10000}"
        new_data["id"] = new_id
        new_data["name"] = f"{original.get('name', 'Skill')} (Copy)"
        self.save_skill(new_data)
        return new_data


# SKILL EXECUTOR ENGINE


class SkillExecutor:
    """Executes a skill step-by-step in a domain-agnostic manner."""

    def __init__(
        self, skill_manager: SkillManager, vision_extractor: object | None = None
    ):
        self.skill_manager = skill_manager
        self.vision_extractor = vision_extractor

    def _substitute_placeholders(self, text: str, context: Mapping[str, object]) -> str:
        """Dynamically substitutes placeholders such as {Nachname} or {document_fullpath}."""
        if not isinstance(text, str) or "{" not in text:
            return text

        def replace_match(match: re.Match) -> str:
            key = match.group(1).strip()
            val = context.get(key, match.group(0))
            return str(val) if val is not None else ""

        return re.sub(r"\{([^{}]+)\}", replace_match, text)

    def _locate_target(
        self, locator: dict[str, object], window_title: str | None = None
    ) -> tuple[int, int] | None:
        """Determines the (x, y) pixel coordinates for a locator."""
        loc_type = str(locator.get("type", "ocr_exact"))
        loc_val = str(locator.get("value", ""))
        prompt = str(locator.get("prompt", ""))

        screen = SoMGrounder.capture_screen(window_title)
        if not screen:
            logger.error("[SkillExecutor] Screenshot could not be captured.")
            return None

        # 1. Fast OCR Exact/Contains Match (RapidOCR)
        if loc_type in ("ocr_exact", "ocr_contains"):
            from core.extraction_pipeline import _get_rapid_ocr

            engine = _get_rapid_ocr()
            if engine is not None:
                try:
                    img_np = np.array(screen) if np is not None else None
                    if img_np is not None:
                        res, _ = engine(img_np)
                        if res:
                            for line in res:
                                box, text, _ = line
                                t = text.strip()
                                if not t:
                                    continue
                                matched = (
                                    (loc_val.lower() == t.lower())
                                    if loc_type == "ocr_exact"
                                    else (loc_val.lower() in t.lower())
                                )
                                if matched:
                                    xs = [p[0] for p in box]
                                    ys = [p[1] for p in box]
                                    cx = int(sum(xs) / len(xs))
                                    cy = int(sum(ys) / len(ys))
                                    offset = cast(
                                        list[int], locator.get("offset", [0, 0])
                                    )
                                    return cx + offset[0], cy + offset[1]
                except Exception as e:
                    logger.warning("[SkillExecutor] RapidOCR Locator error: %s", e)

        # 2. Set-of-Mark (SoM) Grounding via VLM
        if loc_type == "som_vlm" and self.vision_extractor:
            som_img, candidates = SoMGrounder.generate_som_overlay(screen)
            buf = BytesIO()
            som_img.save(buf, format="JPEG", quality=85)
            b64_som = base64.b64encode(buf.getvalue()).decode("utf-8")

            ground_prompt = (
                f"Interactive UI elements are marked with red badges `[1]`, `[2]`, ... in this image.\n"
                f"Which element number best matches: '{prompt if prompt else loc_val}'?\n"
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
                        offset = locator.get("offset", [0, 0])
                        return target["center_x"] + offset[0], target[
                            "center_y"
                        ] + offset[1]  # type: ignore[return-value]

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
                        "[!] Target for click in step '%s' not found.", step_id
                    )

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
                    for char in text_to_type:
                        if sys.platform == "win32":
                            vk = ctypes.windll.user32.VkKeyScanW(ord(char))  # type: ignore[union-attr]
                            ctypes.windll.user32.keybd_event(vk & 0xFF, 0, 0, 0)  # type: ignore[union-attr]
                            ctypes.windll.user32.keybd_event(vk & 0xFF, 0, 2, 0)  # type: ignore[union-attr]
                            time.sleep(0.01)

                    if step.get("press_enter", False) and sys.platform == "win32":
                        ctypes.windll.user32.keybd_event(0x0D, 0, 0, 0)  # type: ignore[union-attr]
                        ctypes.windll.user32.keybd_event(0x0D, 0, 2, 0)  # type: ignore[union-attr]

            # 5. VERIFY_SCREEN (Conditional Branching)
            elif action_type == "VERIFY_SCREEN":
                locator = step.get("locator", {})
                loc_copy = dict(locator)
                if "value" in loc_copy:
                    loc_copy["value"] = self._substitute_placeholders(
                        loc_copy["value"], context
                    )

                max_retries = int(step.get("max_retries", 3))
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

    def filter_matching_files(
        self, folder_path: str, allowed_types: list[str] | None = None
    ) -> list[dict[str, str]]:
        """Filters PDF files in a case folder according to the skill's allowed document types."""
        matching_files: list[dict[str, str]] = []
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

        for fname in os.listdir(folder_path):
            if fname.lower().endswith(".pdf"):
                full_path = os.path.join(folder_path, fname)
                meta_path = full_path + ".meta"
                doc_type = "UNBEKANNT"

                # Try to read document type from .meta file
                if os.path.exists(meta_path):
                    try:
                        with open(meta_path, encoding="utf-8") as f:
                            meta = json.load(f)
                            doc_type = (
                                meta.get("Dokument")
                                or meta.get("document_type")
                                or "UNBEKANNT"
                            )
                    except (json.JSONDecodeError, OSError):
                        logger.debug(
                            "[SkillExecutor] .meta file could not be read: %s",
                            meta_path,
                        )

                # If no type in .meta, try to infer from filename (Name__Type__Date.pdf)
                if doc_type == "UNBEKANNT" and "__" in fname:
                    parts = fname.split("__")
                    if len(parts) >= 2:
                        doc_type = parts[0]

                # Check filter
                if (
                    allowed_types_clean is None
                    or doc_type.lower() in allowed_types_clean
                ):
                    matching_files.append(
                        {
                            "filename": fname,
                            "fullpath": full_path,
                            "document_type": doc_type,
                        }
                    )

        return matching_files

    def execute_skill_for_folder(
        self, skill_id: str, folder_path: str, context: dict[str, object] | None = None
    ) -> bool:
        """Executes a skill for a processed folder, filtering by the document_types registered in the skill."""
        skill = self.skill_manager.get_skill(skill_id)
        if not skill:
            logger.error("[SkillExecutor] Skill '%s' not found.", skill_id)
            return False

        allowed_types = skill.get("document_types", [])
        matching_files = self.filter_matching_files(folder_path, allowed_types)  # type: ignore[arg-type]

        if not matching_files:
            logger.warning(
                "[SkillExecutor] No matching files found for skill '%s' in %s (Filter: %s).",
                skill_id,
                folder_path,
                allowed_types,
            )

        base_ctx = dict(context or {})
        base_ctx["folder_path"] = folder_path
        base_ctx["matching_files"] = [f["fullpath"] for f in matching_files]

        # If matching files exist, set the first as primary document_fullpath
        if matching_files:
            base_ctx["document_fullpath"] = matching_files[0]["fullpath"]
            base_ctx["document_type"] = matching_files[0]["document_type"]
            base_ctx["filename"] = matching_files[0]["filename"]

        # Execution in 'each_file' or 'single' mode
        upload_mode = skill.get("upload_mode", "single_file")
        if upload_mode == "each_file" and len(matching_files) > 1:
            success = True
            for file_info in matching_files:
                file_ctx = dict(base_ctx)
                file_ctx["document_fullpath"] = file_info["fullpath"]
                file_ctx["document_type"] = file_info["document_type"]
                file_ctx["filename"] = file_info["filename"]
                if not self.execute_skill(skill_id, file_ctx):
                    success = False
            return success
        else:
            return self.execute_skill(skill_id, base_ctx)


# SKILL QUEUE MANAGER (MUTUALLY EXCLUSIVE SEQUENTIAL EXECUTION)


class SkillQueueManager:
    """Manages a single-threaded queue for executing Import and Export skills sequentially."""

    def __init__(self, skill_manager: SkillManager):
        self.skill_manager = skill_manager
        self.lock = threading.Lock()
        self.queue: list[dict[str, Any]] = []
        self.is_running = False
        self._stop_requested = False
        self._worker_thread: threading.Thread | None = None

    def get_queue_state(self) -> dict[str, Any]:
        """Returns current items and running state."""
        with self.lock:
            return {
                "is_running": self.is_running,
                "items": [dict(item) for item in self.queue],
            }

    def add_to_queue(
        self, skill_id: str, context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Adds a skill to the queue."""
        skill = self.skill_manager.get_skill(skill_id)
        skill_name = skill.get("name", skill_id) if skill else skill_id
        skill_type = skill.get("type", "export") if skill else "export"

        item_id = f"q_{int(time.time() * 1000)}_{len(self.queue) + 1}"
        item = {
            "id": item_id,
            "skill_id": skill_id,
            "skill_name": skill_name,
            "skill_type": skill_type,
            "status": "pending",
            "context": context or {},
            "created_at": time.time(),
        }
        with self.lock:
            self.queue.append(item)
            logger.info(
                "[SkillQueueManager] Added skill '%s' (%s) to queue as %s",
                skill_name,
                skill_type,
                item_id,
            )
        return item

    def remove_from_queue(self, queue_id: str) -> bool:
        """Removes a pending item from the queue."""
        with self.lock:
            for idx, item in enumerate(self.queue):
                if item["id"] == queue_id:
                    if item["status"] == "running":
                        logger.warning(
                            "[SkillQueueManager] Cannot remove currently running queue item %s",
                            queue_id,
                        )
                        return False
                    self.queue.pop(idx)
                    logger.info(
                        "[SkillQueueManager] Removed item %s from queue", queue_id
                    )
                    return True
        return False

    def reorder_queue(self, item_ids: list[str]) -> bool:
        """Reorders pending items in the queue according to the provided ID list."""
        with self.lock:
            id_to_item = {item["id"]: item for item in self.queue}
            new_queue = []
            # Keep running item at the front if present
            for item in self.queue:
                if item["status"] == "running":
                    new_queue.append(item)

            for i_id in item_ids:
                if i_id in id_to_item and id_to_item[i_id]["status"] != "running":
                    new_queue.append(id_to_item[i_id])

            # Append any unmentioned pending items
            seen = {it["id"] for it in new_queue}
            for item in self.queue:
                if item["id"] not in seen:
                    new_queue.append(item)

            self.queue = new_queue
            logger.info(
                "[SkillQueueManager] Queue reordered: %s",
                [it["id"] for it in self.queue],
            )
            return True

    def start_queue(self) -> bool:
        """Starts processing the queue in a background worker thread."""
        with self.lock:
            if self.is_running:
                logger.info("[SkillQueueManager] Queue is already running.")
                return True
            self.is_running = True
            self._stop_requested = False
            self._worker_thread = threading.Thread(
                target=self._worker_loop, daemon=True
            )
            self._worker_thread.start()
            logger.info("[SkillQueueManager] Queue started.")
            return True

    def stop_queue(self) -> bool:
        """Stopps processing the queue after the currently executing item finishes."""
        with self.lock:
            self._stop_requested = True
            self.is_running = False
            logger.info("[SkillQueueManager] Queue stop requested.")
            return True

    def _worker_loop(self):
        """Sequential execution loop for queued skills."""
        from routes.state import DashboardState

        while not self._stop_requested:
            target_item = None
            with self.lock:
                for item in self.queue:
                    if item["status"] == "pending":
                        target_item = item
                        target_item["status"] = "running"
                        break

            if not target_item:
                # No more pending items
                logger.info("[SkillQueueManager] No more pending items in queue.")
                with self.lock:
                    self.is_running = False
                break

            logger.info(
                "[SkillQueueManager] Executing queued item %s (Skill: %s)",
                target_item["id"],
                target_item["skill_id"],
            )
            success = False

            try:
                if target_item["skill_type"] == "import":
                    # Run Import skill logic
                    if DashboardState.processor:
                        import queue

                        from main import process_existing_files

                        skill_obj = self.skill_manager.get_skill(
                            target_item["skill_id"]
                        )
                        allowed_exts = (
                            cast(list[str] | None, skill_obj.get("allowed_extensions"))
                            if skill_obj
                            else None
                        )

                        temp_q = queue.Queue()
                        process_existing_files(
                            DashboardState.processor,
                            temp_q,
                            allowed_extensions=allowed_exts,
                        )
                        while not temp_q.empty():
                            fp = temp_q.get()
                            if fp:
                                try:
                                    DashboardState.processor.process_and_route_file(fp)
                                except Exception as e:
                                    logger.error(
                                        "[SkillQueueManager] Error processing file %s: %s",
                                        fp,
                                        e,
                                    )
                                finally:
                                    temp_q.task_done()
                    success = True
                else:
                    # Run Export skill logic
                    extractor = (
                        DashboardState.processor.llm_extractor
                        if DashboardState.processor
                        else None
                    )
                    executor = SkillExecutor(
                        self.skill_manager, vision_extractor=extractor
                    )

                    folder_name = target_item["context"].get("folder_name")
                    if folder_name and DashboardState.config:
                        folder_path = os.path.abspath(
                            os.path.join(
                                DashboardState.config.target_base_dir, folder_name
                            )
                        )
                        success = executor.execute_skill_for_folder(
                            target_item["skill_id"], folder_path, target_item["context"]
                        )
                    else:
                        success = executor.execute_skill(
                            target_item["skill_id"], target_item["context"]
                        )

            except Exception as e:
                logger.error(
                    "[SkillQueueManager] Error executing queued item %s: %s",
                    target_item["id"],
                    e,
                    exc_info=True,
                )
                success = False

            with self.lock:
                target_item["status"] = "completed" if success else "failed"

            time.sleep(0.5)

        with self.lock:
            self.is_running = False
        logger.info("[SkillQueueManager] Worker loop ended.")


_SKILL_QUEUE_MANAGER = None


def get_skill_queue_manager(
    skill_manager: SkillManager | None = None,
) -> SkillQueueManager:
    global _SKILL_QUEUE_MANAGER
    if _SKILL_QUEUE_MANAGER is None:
        if skill_manager is None:
            skills_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "settings",
                "skills",
            )
            skill_manager = SkillManager(skills_dir=skills_dir)
        _SKILL_QUEUE_MANAGER = SkillQueueManager(skill_manager)
    return _SKILL_QUEUE_MANAGER
