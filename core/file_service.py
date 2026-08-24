"""
OrdinFlow — File Service Module
Handles all filesystem operations, sidecar metadata, target directory determination, and PDF splitting.
"""

import datetime
import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

try:
    import fitz
except ImportError:
    fitz = None

from core.config import AppConfig
from core.routing import render_filename, render_folder_name
from core.utils import (
    MISSING_PLACEHOLDER,
    clean_path_component,
    deduplicate_path,
    is_missing_value,
    remove_source_with_meta,
    safe_move,
)


def _clean_folder_match_name(name: str) -> str:
    if not name:
        return ""
    name = name.replace(".", " ")
    return name.lower().replace("-", " ").strip()


class FileService:
    """Encapsulates filesystem operations, sidecar creation, PDF splitting, and routing."""

    def __init__(self, config: AppConfig):
        self.config = config
        self.can_split_pdf = fitz is not None

    def find_existing_folder_by_keywords(self, base_dir: str, keywords: list[str]) -> str | None:
        """Searches base directory for a matching folder based on a list of keywords."""
        if not os.path.exists(base_dir) or not keywords:
            return None
        valid_kw = [_clean_folder_match_name(k) for k in keywords if k and not is_missing_value(k)]
        valid_kw = [k for k in valid_kw if k]
        if not valid_kw:
            return None

        for item in os.listdir(base_dir):
            item_path = os.path.join(base_dir, item)
            if os.path.isdir(item_path):
                item_clean = _clean_folder_match_name(item)
                if all(kw in item_clean for kw in valid_kw):
                    return item_path
        return None

    def determine_target_directory(
        self,
        extracted: dict[str, Any],
        routing_cfg: dict[str, Any] | None = None,
        optional_fields: set | None = None,
    ) -> str:
        """Determines or creates the target directory for a document based on extraction data."""
        routing_cfg = routing_cfg or {}
        optional_fields = optional_fields or set()

        match_folder_by = routing_cfg.get("match_folder_by") or getattr(self.config, "match_folder_by", None) or []
        existing_folder = None
        if match_folder_by:
            match_keywords = [
                clean_path_component(str(extracted.get(k, ""))).strip()
                for k in match_folder_by
                if not is_missing_value(extracted.get(k))
            ]
            if match_keywords:
                existing_folder = self.find_existing_folder_by_keywords(
                    self.config.target_base_dir, match_keywords
                )

        target_folder_name = render_folder_name(
            extracted,
            routing_cfg=routing_cfg,
            optional_fields=optional_fields,
            folder_structure=getattr(self.config, "folder_structure", None),
            delimiter=getattr(self.config, "folder_delimiter", "--"),
        )

        target_dir = os.path.join(self.config.target_base_dir, target_folder_name)

        if existing_folder:
            existing_folder_name = os.path.basename(existing_folder)
            existing_fehlt_count = existing_folder_name.upper().count("MISSING") + existing_folder_name.count("----")
            target_fehlt_count = target_folder_name.upper().count("MISSING") + target_folder_name.count("----")

            if target_fehlt_count < existing_fehlt_count and os.path.abspath(existing_folder) != os.path.abspath(
                target_dir
            ):
                try:
                    logger.info(
                        f"[+] Renaming existing case folder: '{existing_folder_name}' -> '{target_folder_name}'"
                    )
                    os.rename(existing_folder, target_dir)
                    return target_dir
                except OSError as e:
                    logger.warning(f"[!] Renaming of case folder failed: {e}")
            logger.info(f"[*] Using existing case folder: '{existing_folder_name}'")
            return existing_folder

        logger.info(f"[+] Creating new case folder: '{target_folder_name}'")
        os.makedirs(target_dir, exist_ok=True)
        return target_dir

    def move_file(self, filepath: str, target_dir: str, target_filename: str) -> str:
        """Safely moves a file into the target directory."""
        target_filepath = deduplicate_path(os.path.join(target_dir, target_filename))
        logger.info(f"[+] Moving file '{os.path.basename(filepath)}' -> '{target_filepath}'")
        safe_move(filepath, target_filepath)
        return target_filepath

    def mark_for_review(
        self,
        filepath: str,
        reason: str = "Extraction failed",
        extracted: dict[str, Any] | None = None,
    ) -> None:
        """Creates a sidecar .meta JSON file to flag documents requiring manual review."""
        meta_path = filepath + ".meta"
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
        meta: dict[str, Any] = {
            "status": "review",
            "reason": reason,
            "grund": reason,  # Backward compatibility alias
            "zeit": now_iso,
            "timestamp": now_iso,
            "filename": os.path.basename(filepath),
            "dateiname": os.path.basename(filepath),
        }
        if extracted:
            extracted_raw = {}
            for k, v in extracted.items():
                if k == "page_results" and isinstance(v, list):
                    clean_page_results = []
                    for pr in v:
                        if isinstance(pr, dict):
                            clean_pr = {}
                            for pr_k, pr_v in pr.items():
                                if pr_k not in ["images", "raw_images", "_img", "raw"]:
                                    if isinstance(pr_v, str):
                                        clean_pr[pr_k] = clean_path_component(pr_v)
                                    elif isinstance(pr_v, (set, tuple)):
                                        clean_pr[pr_k] = list(pr_v)
                                    else:
                                        clean_pr[pr_k] = pr_v
                            clean_page_results.append(clean_pr)
                    extracted_raw["page_results"] = clean_page_results
                elif k not in ["images", "raw_images", "_img", "raw"]:
                    if isinstance(v, str):
                        extracted_raw[k] = clean_path_component(v)
                    elif isinstance(v, (set, tuple)):
                        extracted_raw[k] = list(v)
                    else:
                        extracted_raw[k] = v
            meta["extracted"] = extracted_raw

        try:
            tmp_path = meta_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, meta_path)
            logger.info("[*] Marked file for review: '%s' (Reason: %s)", os.path.basename(filepath), reason)
        except (OSError, TypeError, ValueError) as e:
            logger.error(f"[!] Error writing sidecar file '{meta_path}': {e}")

    def split_multi_page_pdf(
        self,
        filepath: str,
        page_results: list[dict[str, Any]],
        extracted_base: dict[str, Any],
        find_doc_type_cfg_fn: Any,
        optional_fields: set | None = None,
    ) -> bool:
        """Splits a batch PDF into multiple partial PDFs based on page groups."""
        if not self.can_split_pdf:
            logger.error("[!] PyMuPDF ('fitz') is missing. Cannot split batch PDF!")
            return False

        filename = os.path.basename(filepath)
        if not os.path.exists(filepath):
            logger.warning(f"[!] Source file '{filepath}' no longer exists for splitting.")
            return False

        logger.info(f"[*] Splitting batch PDF '{filename}' into {len(page_results)} separate files...")
        optional_fields = optional_fields or set()

        try:
            with fitz.open(filepath) as doc:  # type: ignore[assignment]
                for group_res in page_results:
                    g_type = group_res.get("Document", "UNKNOWN")
                    g_pages = group_res.get("pages", [])

                    part_extracted = dict(group_res)
                    part_extracted["Document"] = g_type

                    for k, v in extracted_base.items():
                        if k not in {
                            "Document",
                            "pages",
                            "page_results",
                            "vision_description",
                        } and (
                            k not in part_extracted or not part_extracted[k] or part_extracted[k] == MISSING_PLACEHOLDER
                        ):
                            part_extracted[k] = v

                    _, g_info = find_doc_type_cfg_fn(g_type)
                    g_routing = g_info.get("routing") or {} if g_info else {}
                    g_val = g_info.get("validation") or {} if g_info else {}
                    g_opt = set(g_val.get("optional_fields", []))

                    g_is_dependent = bool(g_info.get("dependent", False)) if g_info else False
                    if g_is_dependent:
                        g_opt = g_opt | optional_fields

                    target_dir = self.determine_target_directory(
                        extracted=part_extracted,
                        routing_cfg=g_routing,
                        optional_fields=g_opt,
                    )

                    _, orig_ext = os.path.splitext(filepath.lower())
                    target_filename = render_filename(
                        part_extracted,
                        routing_cfg=g_routing,
                        ext=orig_ext,
                        optional_fields=g_opt,
                        fallbacks={"Document": g_type},
                    )

                    with fitz.open() as new_doc:  # type: ignore[assignment]
                        for p_idx in g_pages:
                            new_doc.insert_pdf(doc, from_page=p_idx - 1, to_page=p_idx - 1)

                        target_filepath = deduplicate_path(os.path.join(target_dir, target_filename))
                        new_doc.save(target_filepath, garbage=4, deflate=True, clean=True)
                    logger.info(
                        f"[+] Partial PDF '{os.path.basename(target_filepath)}' (pages {g_pages}) saved successfully."
                    )
            remove_source_with_meta(filepath)
            return True
        except Exception as e:
            logger.error(f"[!] Error reading or splitting '{filepath}': {e}")
            return False

    def save_filtered_pdf(self, src_path: str, dst_path: str, kept_pages: list[int]) -> bool:
        """Saves a PDF without empty pages."""
        if not self.can_split_pdf:
            return False
        if not os.path.exists(src_path):
            logger.warning(f"[!] Source file '{src_path}' no longer exists for filtering.")
            return False
        try:
            with fitz.open(src_path) as doc:  # type: ignore[assignment]
                with fitz.open() as new_doc:  # type: ignore[assignment]
                    for p_idx in kept_pages:
                        new_doc.insert_pdf(doc, from_page=p_idx - 1, to_page=p_idx - 1)
                    new_doc.save(dst_path, garbage=4, deflate=True, clean=True)
            remove_source_with_meta(src_path)
            return True
        except Exception as e:
            logger.error(f"[!] Error saving filtered PDF for '{src_path}': {e}")
            return False
