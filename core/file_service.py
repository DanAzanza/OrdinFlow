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
from core.matcher import FileSystemRouter
from core.routing import render_filename, render_folder_name
from core.utils import (
    MISSING_PLACEHOLDER,
    _deduplicate_path,
    _remove_source_with_meta,
    clean_path_component,
    is_missing_value,
    safe_move,
)


class FileService:
    """Encapsulates filesystem operations, sidecar creation, PDF splitting, and routing."""

    def __init__(self, config: AppConfig, fs_router: FileSystemRouter | None = None):
        self.config = config
        self.fs_router = fs_router or FileSystemRouter(config)
        self.can_split_pdf = fitz is not None

    def determine_target_directory(
        self,
        extracted: dict[str, Any],
        routing_cfg: dict[str, Any] | None = None,
        optional_fields: set | None = None,
        extraction_fields: set | None = None,
    ) -> str:
        """Determines or creates the target directory for a document based on extraction data."""
        routing_cfg = routing_cfg or {}
        optional_fields = optional_fields or set()
        extraction_fields = extraction_fields or set()

        match_folder_by = routing_cfg.get("match_folder_by") or getattr(self.config, "match_folder_by", None) or []
        existing_folder = None
        if match_folder_by:
            match_keywords = [
                clean_path_component(str(extracted.get(k, ""))).strip()
                for k in match_folder_by
                if not is_missing_value(extracted.get(k))
            ]
            if match_keywords:
                existing_folder = self.fs_router.find_existing_folder_by_keywords(
                    self.config.target_base_dir, match_keywords
                )

        target_folder_name = render_folder_name(
            extracted,
            routing_cfg=routing_cfg,
            optional_fields=optional_fields,
            extraction_fields=extraction_fields,
            folder_structure=getattr(self.config, "folder_structure", None),
            delimiter=getattr(self.config, "folder_delimiter", "--"),
        )

        target_dir = os.path.join(self.config.target_base_dir, target_folder_name)

        if existing_folder:
            existing_folder_name = os.path.basename(existing_folder)
            existing_fehlt_count = (
                existing_folder_name.upper().count("FEHLT")
                + existing_folder_name.upper().count("MISSING")
                + existing_folder_name.count("----")
            )
            target_fehlt_count = (
                target_folder_name.upper().count("FEHLT")
                + target_folder_name.upper().count("MISSING")
                + target_folder_name.count("----")
            )

            if target_fehlt_count < existing_fehlt_count:
                if os.path.abspath(existing_folder) != os.path.abspath(target_dir):
                    try:
                        logger.info(
                            f"[+] Renaming existing case folder: '{existing_folder_name}' -> '{target_folder_name}'"
                        )
                        os.rename(existing_folder, target_dir)
                        return target_dir
                    except OSError as e:
                        logger.warning(
                            f"[!] Renaming of case folder failed: {e}"
                        )
            logger.info(
                f"[*] Using existing case folder: '{existing_folder_name}'"
            )
            return existing_folder

        logger.info(f"[+] Creating new case folder: '{target_folder_name}'")
        os.makedirs(target_dir, exist_ok=True)
        return target_dir

    def move_file(
        self, filepath: str, target_dir: str, target_filename: str
    ) -> str:
        """Safely moves a file into the target directory."""
        target_filepath = _deduplicate_path(os.path.join(target_dir, target_filename))
        logger.info(
            f"[+] Moving file '{os.path.basename(filepath)}' -> '{target_filepath}'"
        )
        safe_move(filepath, target_filepath)
        return target_filepath

    def mark_as_pruefen(
        self,
        filepath: str,
        grund: str = "Extraction failed",
        extracted: dict[str, Any] | None = None,
    ) -> None:
        """Creates a sidecar .meta JSON file to flag documents requiring manual review."""
        meta_path = filepath + ".meta"
        meta: dict[str, Any] = {
            "status": "pruefen",
            "grund": grund,
            "zeit": datetime.datetime.now().isoformat(timespec="seconds"),
            "dateiname": os.path.basename(filepath),
        }
        if extracted:
            extracted_raw = {}
            for k, v in extracted.items():
                if k not in ["page_results", "images"]:
                    if isinstance(v, str):
                        extracted_raw[k] = clean_path_component(v)
                    elif isinstance(v, bool):
                        extracted_raw[k] = v
                    else:
                        extracted_raw[str(k)] = str(v)
            meta_extracted: dict[str, Any] = {"raw": extracted_raw}
            desc = extracted.get("description") or extracted.get("vision_description") or ""
            if isinstance(desc, str) and desc.strip():
                meta_extracted["description"] = desc.strip()
            meta["extracted"] = meta_extracted
        try:
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
            logger.info(f"[*] Sidecar file created: {os.path.basename(meta_path)}")
        except Exception as e:
            logger.error(
                f"[!] Error writing sidecar file '{meta_path}': {e}"
            )

    def split_multi_page_pdf(
        self,
        filepath: str,
        page_results: list[dict[str, Any]],
        extracted_base: dict[str, Any],
        find_doc_type_cfg_fn: Any,
        optional_fields: set | None = None,
        extraction_fields: set | None = None,
    ) -> bool:
        """Splits a batch PDF into multiple partial PDFs based on page groups."""
        if not self.can_split_pdf:
            logger.error(
                "[!] PyMuPDF ('fitz') is missing. Cannot split batch PDF!"
            )
            return False

        filename = os.path.basename(filepath)
        logger.info(
            f"[*] Splitting batch PDF '{filename}' into {len(page_results)} separate files..."
        )
        optional_fields = optional_fields or set()
        extraction_fields = extraction_fields or set()

        doc = fitz.open(filepath)  # type: ignore[assignment]
        try:
            for group_res in page_results:
                g_type = group_res.get("Dokument", "UNKNOWN")
                g_pages = group_res.get("pages", [])

                part_extracted = dict(group_res)
                part_extracted["Dokument"] = g_type

                for k, v in extracted_base.items():
                    if k not in [
                        "Dokument",
                        "pages",
                        "page_results",
                        "vision_description",
                    ]:
                        if (
                            k not in part_extracted
                            or not part_extracted[k]
                            or part_extracted[k] == MISSING_PLACEHOLDER
                        ):
                            part_extracted[k] = v

                _, g_info = find_doc_type_cfg_fn(g_type)
                g_routing = g_info.get("routing") or {} if g_info else {}
                g_val = g_info.get("validation") or {} if g_info else {}
                g_opt = set(g_val.get("optional_fields", []))
                g_ext_fields = g_info.get("extraction_fields", {}) if g_info else {}

                g_is_dependent = bool(g_info.get("dependent", False)) if g_info else False
                if g_is_dependent:
                    g_opt = g_opt | optional_fields
                    g_ext_fields_keys = set(g_ext_fields.keys()) | extraction_fields
                else:
                    g_ext_fields_keys = set(g_ext_fields.keys())

                target_dir = self.determine_target_directory(
                    extracted=part_extracted,
                    routing_cfg=g_routing,
                    optional_fields=g_opt,
                    extraction_fields=g_ext_fields_keys,
                )

                _, orig_ext = os.path.splitext(filepath.lower())
                target_filename = render_filename(
                    part_extracted,
                    routing_cfg=g_routing,
                    ext=orig_ext,
                    optional_fields=g_opt,
                    extraction_fields=g_ext_fields_keys,
                    fallbacks={"Dokument": g_type},
                )

                new_doc = fitz.open()  # type: ignore[assignment]
                try:
                    for p_idx in g_pages:
                        new_doc.insert_pdf(doc, from_page=p_idx - 1, to_page=p_idx - 1)

                    target_filepath = _deduplicate_path(
                        os.path.join(target_dir, target_filename)
                    )
                    new_doc.save(target_filepath)
                finally:
                    new_doc.close()
                logger.info(
                    f"[+] Partial PDF '{os.path.basename(target_filepath)}' (pages {g_pages}) saved successfully."
                )
        finally:
            doc.close()
        _remove_source_with_meta(filepath)
        return True

    def save_filtered_pdf(self, src_path: str, dst_path: str, kept_pages: list[int]) -> bool:
        """Saves a PDF without empty pages."""
        if not self.can_split_pdf:
            return False
        doc = fitz.open(src_path)  # type: ignore[assignment]
        try:
            new_doc = fitz.open()  # type: ignore[assignment]
            try:
                for p_idx in kept_pages:
                    new_doc.insert_pdf(doc, from_page=p_idx - 1, to_page=p_idx - 1)
                new_doc.save(dst_path)
            finally:
                new_doc.close()
        finally:
            doc.close()
        _remove_source_with_meta(src_path)
        return True
