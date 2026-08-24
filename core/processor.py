"""
OrdinFlow — Document Processor Orchestrator Module
Lean main orchestrator for classification, extraction, routing, and thread lifecycle control.
"""

import gc
import logging
import os
import threading
import time
from typing import Any

from core.config import AppConfig
from core.extraction_pipeline import ExtractionPipeline
from core.file_service import FileService
from core.image_processing import ImagePreprocessor
from core.routing import render_filename
from core.utils import (
    MISSING_PLACEHOLDER,
    clean_path_component,
    cleanup_empty_folder,
    format_result,
    is_missing_value,
    remove_source_with_meta,
    wait_until_unlocked,
)
from core.vision import LLMExtractor

logger = logging.getLogger(__name__)


class AllPagesEmptyError(Exception):
    """Raised when a document consists entirely of empty/blank pages."""


class DocumentProcessor:
    """Central orchestrator for document processing by combining specialized services."""

    def __init__(
        self,
        config: AppConfig,
        image_preprocessor: ImagePreprocessor | None = None,
        llm_extractor: LLMExtractor | None = None,
        file_service: FileService | None = None,
        extraction_pipeline: ExtractionPipeline | None = None,
    ):
        self.config = config
        self.image_preprocessor = image_preprocessor or ImagePreprocessor(config)
        self.llm_extractor = llm_extractor or LLMExtractor(config)
        self.file_service = file_service or FileService(config)
        self.extraction_pipeline = extraction_pipeline or ExtractionPipeline(
            config, self.image_preprocessor, self.llm_extractor
        )

        # Processing locks & thread control
        self.processing_lock = threading.Lock()
        self.processing_files: set = set()
        self.can_split_pdf = self.file_service.can_split_pdf

        # Pause/Resume event
        self._active_event = threading.Event()
        self._active_event.set()

        # Thread-safe statistics counters
        self._stats_lock = threading.Lock()
        self.stats_total = 0
        self.stats_success = 0
        self.stats_failed = 0
        self.stats_skipped = 0
        self.stats_total_duration = 0.0

        # Document context for inherited data across multi-part files
        self.last_context: dict = {}
        self.last_optional_fields: set = set()
        self.last_extraction_fields: set = set()

    # --- Pause/Resume Control ---
    def pause(self):
        """Pauses document processing."""
        self._active_event.clear()
        logger.info("[*] Processing PAUSED.")

    def resume(self):
        """Resumes document processing."""
        self._active_event.set()
        logger.info("[*] Processing RESUMED.")

    def is_paused(self) -> bool:
        """Returns True if processing is paused."""
        return not self._active_event.is_set()

    def wait_if_paused(self):
        """Blocks while processing is paused."""
        self._active_event.wait()

    # --- Statistics ---
    def get_stats(self) -> dict[str, Any]:
        """Returns a thread-safe snapshot of processing statistics."""
        with self._stats_lock:
            avg = (self.stats_total_duration / self.stats_total) if self.stats_total > 0 else 0.0
            queue_count = 0
            try:
                if os.path.exists(self.config.watch_dir):
                    valid_exts = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}
                    queue_count = sum(
                        1
                        for _, _, files in os.walk(self.config.watch_dir)
                        for f in files
                        if os.path.splitext(f.lower())[1] in valid_exts
                    )
            except (OSError, ValueError) as e:
                logger.debug("Error retrieving queue size: %s", e)

            return {
                "total": self.stats_total,
                "success": self.stats_success,
                "failed": self.stats_failed,
                "skipped": self.stats_skipped,
                "avg_duration": round(avg, 1),
                "paused": self.is_paused(),
                "queue_size": queue_count,
            }

    def log_stats(self):
        """Logs processing statistics."""
        stats = self.get_stats()
        logger.info("=" * 60)
        logger.info(
            f"[*] STATS: {stats['total']} processed, "
            f"{stats['success']} successful, "
            f"Ø {stats['avg_duration']:.1f}s per file"
        )
        logger.info("=" * 60)

    # --- Delegated helper methods for backward compatibility & tests ---
    def _classify_single_page(self, raw_img: Any, idx: int, pdf_path: str | None = None) -> dict[str, Any]:
        return self.extraction_pipeline.classify_single_page(raw_img, idx, pdf_path=pdf_path)

    def _process_page_group(self, doc_type: str, group_pages: list) -> dict | None:
        return self.extraction_pipeline.process_page_group(doc_type, group_pages)

    def _process_document_pages(self, document_pages: list) -> dict | None:
        return self.extraction_pipeline.process_document_pages(document_pages)

    def _validate_extracted_data(self, extracted: dict[str, Any] | None) -> tuple[bool, str]:
        return self.extraction_pipeline.validate_extracted_data(extracted)

    def _determine_target_directory(
        self,
        extracted: dict[str, Any],
        routing_cfg: dict[str, Any] | None = None,
        optional_fields: set | None = None,
        extraction_fields: set | None = None,
    ) -> str:
        return self.file_service.determine_target_directory(extracted, routing_cfg, optional_fields)

    def _move_and_compress_file(self, filepath: str, target_dir: str, target_filename: str) -> str:
        return self.file_service.move_file(filepath, target_dir, target_filename)

    def _mark_for_review(
        self,
        filepath: str,
        reason: str = "Extraction failed",
        extracted: dict[str, Any] | None = None,
    ) -> None:
        self.file_service.mark_for_review(filepath, reason, extracted)

    def _mark_as_pruefen(
        self,
        filepath: str,
        grund: str = "Extraction failed",
        extracted: dict[str, Any] | None = None,
    ) -> None:
        self.file_service.mark_for_review(filepath, grund, extracted)

    # --- Extraction & Hybrid Voting ---
    def extract_hybrid_voting(self, filepath: str, save_empty_pages: bool = False) -> dict[str, Any] | None:
        """Analyses and extracts data across all pages of a document."""
        raw_images = self.image_preprocessor.create_source_images(filepath, return_raw=True)
        if not raw_images:
            return None

        classified_pages = [
            self._classify_single_page(raw_img, idx, pdf_path=filepath) for idx, raw_img in enumerate(raw_images)
        ]

        is_all_empty = all(p["matched_name"].upper() == "LEER" for p in classified_pages)
        if is_all_empty and not save_empty_pages:
            raise AllPagesEmptyError("Document consists entirely of empty pages")

        if save_empty_pages:
            non_empty_pages = classified_pages
        else:
            non_empty_pages = [p for p in classified_pages if p["matched_name"].upper() != "LEER"]

        if not non_empty_pages:
            return None

        # 1. Unified Tiered Extraction across ALL pages in one pool
        doc_res = self._process_document_pages(non_empty_pages)
        if not doc_res:
            logger.warning(f"[-] No valid extraction results for '{os.path.basename(filepath)}'.")
            return None

        # 2. Group pages by document type for routing and optional PDF splitting
        groups = []
        current_group = []
        current_type = None
        for p in non_empty_pages:
            t = p["matched_name"]
            if save_empty_pages and t.upper() == "LEER" and current_type is not None:
                t = current_type
                p = dict(p)
                p["matched_name"] = current_type
            if current_type is None:
                current_type = t
                current_group.append(p)
            elif t == current_type:
                current_group.append(p)
            else:
                groups.append((current_type, current_group))
                current_type = t
                current_group = [p]
        if current_group:
            groups.append((current_type, current_group))

        page_results = []
        for doc_type, group_pages in groups:
            g_nums = [p["page_num"] for p in group_pages]
            g_res = dict(doc_res)
            g_res["Document"] = doc_type
            g_res["pages"] = g_nums
            g_info = group_pages[0].get("matched_info", {})
            if g_info.get("validation", {}).get("signature_required", False):
                g_res["Signed"] = doc_res.get("Signed", False)
            page_results.append(g_res)

        final_doc = dict(doc_res)
        dok_arten = [g[0] for g in groups if not is_missing_value(g[0])]
        final_doc["Document"] = "+".join(dok_arten) if dok_arten else MISSING_PLACEHOLDER
        final_doc["page_results"] = page_results

        logger.debug(f"[+] Consolidated final result: {format_result(final_doc)}")
        logger.info(f"[+] Final extraction result for document: {format_result(final_doc)}")
        return final_doc

    # --- Main Processing Logic ---
    def process_and_route_file(
        self,
        filepath: str,
        split_multi_documents: bool = True,
        save_empty_pages: bool = False,
    ) -> bool:
        """Classifies, extracts, and routes a document."""
        start_time = time.time()
        filename = os.path.basename(filepath)
        if not os.path.exists(filepath):
            logger.warning(f"[!] File '{filename}' no longer exists.")
            return False

        with self.processing_lock:
            if filepath in self.processing_files:
                logger.warning(f"[!] File '{filename}' is already being processed. Skipping duplicate invocation.")
                return False
            self.processing_files.add(filepath)

        try:
            self.wait_if_paused()
            logger.info(f"======== Processing: {filename} ========")
            if not wait_until_unlocked(filepath, retries=5, delay=1.0):
                logger.warning(f"[!] File '{filename}' remained locked after 5 attempts.")
                return False

            extracted = self.extract_hybrid_voting(filepath, save_empty_pages=save_empty_pages)

            is_dependent_doc = False
            routing_cfg = {}
            optional_fields = set()
            extraction_fields = set()
            is_valid, reason = False, "No data extracted"
            matched_type = ""
            dok_art_raw = ""

            if extracted:
                dok_art_raw = clean_path_component(extracted.get("Document", ""))
                matched_type, matched_info = self.llm_extractor.find_doc_type_config(dok_art_raw)

                if matched_info:
                    routing_cfg = matched_info.get("routing") or {}
                    validation_cfg = matched_info.get("validation") or {}
                    optional_fields = set(validation_cfg.get("optional_fields", []))
                    extraction_fields = set(matched_info.get("extraction_fields", {}).keys())

                if not routing_cfg.get("archive", True):
                    logger.warning(f"[-] '{matched_type}' has archive=False and will not be archived.")
                    self._mark_as_pruefen(filepath, f"{matched_type} – manual assignment required")
                    return False

                is_dependent_doc = bool(matched_info.get("dependent", False))

                if is_dependent_doc and self.last_context:
                    for k, v in self.last_context.items():
                        if is_missing_value(extracted.get(k)):
                            extracted[k] = v
                    optional_fields = optional_fields | self.last_optional_fields
                    extraction_fields = extraction_fields | self.last_extraction_fields

                for k, v in list(extracted.items()):
                    if isinstance(v, str) and not is_missing_value(v):
                        extracted[k] = clean_path_component(v).strip()

                if not is_dependent_doc:
                    self.last_context = dict(extracted)
                    self.last_optional_fields = set(optional_fields)
                    self.last_extraction_fields = set(extraction_fields)
                is_valid, reason = self._validate_extracted_data(extracted)

            if not os.path.exists(filepath):
                logger.warning(f"[!] File '{filename}' was removed or moved during processing. Skipping routing.")
                return False

            if is_valid and extracted:
                _, orig_ext = os.path.splitext(filepath.lower())

                def _route_single_file() -> tuple[str, str]:
                    td = self._determine_target_directory(
                        extracted=extracted,
                        routing_cfg=routing_cfg,
                        optional_fields=optional_fields,
                    )
                    tf = render_filename(
                        extracted,
                        routing_cfg=routing_cfg,
                        ext=orig_ext,
                        optional_fields=optional_fields,
                        fallbacks={"Document": matched_type if matched_type else dok_art_raw},
                    )
                    return td, tf

                page_results = extracted.get("page_results", [])
                if split_multi_documents and len(page_results) > 1:
                    success = self.file_service.split_multi_page_pdf(
                        filepath=filepath,
                        page_results=page_results,
                        extracted_base=extracted,
                        find_doc_type_cfg_fn=self.llm_extractor.find_doc_type_config,
                        optional_fields=optional_fields,
                    )
                    if not success:
                        target_dir, target_filename = _route_single_file()
                        self._move_and_compress_file(filepath, target_dir, target_filename)
                else:
                    target_dir, target_filename = _route_single_file()
                    target_filepath = os.path.join(target_dir, target_filename)

                    kept_pages = []
                    doc_len = 0
                    if self.can_split_pdf and os.path.exists(filepath):
                        try:
                            import fitz

                            with fitz.open(filepath) as doc:
                                doc_len = len(doc)
                            for pr in page_results:
                                if pr.get("Document", "").upper() not in (
                                    "LEER",
                                    "BLANK",
                                ):
                                    kept_pages.extend(pr.get("pages", []))
                            kept_pages = sorted(set(kept_pages))
                        except (AttributeError, OSError, RuntimeError, ValueError):
                            logger.debug("Unable to determine PDF page list", exc_info=True)

                    if self.can_split_pdf and doc_len > 0 and len(kept_pages) < doc_len:
                        logger.info(f"[*] Saving PDF without empty pages. Keeping pages {kept_pages} of {doc_len}.")
                        self.file_service.save_filtered_pdf(filepath, target_filepath, kept_pages)
                    else:
                        self._move_and_compress_file(filepath, target_dir, target_filename)

                duration = time.time() - start_time
                with self._stats_lock:
                    self.stats_total += 1
                    self.stats_success += 1
                    self.stats_total_duration += duration
                logger.info(f"[+] Processing of '{filename}' completed successfully after {duration:.2f} seconds.")
                return True
            else:
                if not os.path.exists(filepath):
                    logger.warning(f"[!] File '{filename}' no longer exists. Skipping sidecar creation.")
                    return False
                self._mark_for_review(filepath, reason, extracted)

                duration = time.time() - start_time
                with self._stats_lock:
                    self.stats_total += 1
                    self.stats_failed += 1
                    self.stats_total_duration += duration
                logger.warning(f"[-] Processing of '{filename}' incomplete ({duration:.2f}s) — Reason: {reason}.")
                if extracted:
                    logger.debug(f"[-] Raw extracted data: {format_result(extracted)}")
                return False
        except AllPagesEmptyError:
            logger.info(f"[-] '{filename}' consists only of empty pages and will be deleted.")
            remove_source_with_meta(filepath)
            with self._stats_lock:
                self.stats_total += 1
                self.stats_skipped += 1
            return True
        except FileNotFoundError:
            logger.warning(f"[!] File '{filename}' was deleted during processing.")
            with self._stats_lock:
                self.stats_skipped += 1
            return False
        except Exception as e:
            logger.exception(f"[!] Error: {e}")
            duration = time.time() - start_time
            logger.error(f"[-] Processing of '{filename}' aborted due to error after {duration:.2f} seconds.")
            return False
        finally:
            with self.processing_lock:
                self.processing_files.discard(filepath)
            cleanup_empty_folder(os.path.dirname(filepath), stop_at=self.config.watch_dir)
            gc.collect()
