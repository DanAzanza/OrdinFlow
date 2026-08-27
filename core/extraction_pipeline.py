"""
OrdinFlow — Extraction Pipeline Module
Domain-agnostic module for page classification, multi-resolution extraction tiers, and voting algorithms.
"""

import logging
import os
import threading
from typing import Any

from core.config import AppConfig
from core.image_processing import ImagePreprocessor
from core.utils import is_missing_value
from core.vision import LLMExtractor
from core.voting import (
    CONSENSUS_THRESHOLD,
    EXCLUDE_KEYS as _EXCLUDE_KEYS,
    evaluate_round as _evaluate_round,
    to_bool_value as _to_bool_value,
)

logger = logging.getLogger(__name__)

_RAPID_OCR_ENGINE = None
_OCR_LOCK = threading.Lock()


def _get_rapid_ocr():
    global _RAPID_OCR_ENGINE
    if _RAPID_OCR_ENGINE is None:
        with _OCR_LOCK:
            if _RAPID_OCR_ENGINE is None:
                try:
                    from rapidocr_onnxruntime import RapidOCR  # type: ignore[import-untyped]

                    _RAPID_OCR_ENGINE = RapidOCR()
                except (ImportError, RuntimeError, OSError):
                    _RAPID_OCR_ENGINE = False
    return _RAPID_OCR_ENGINE if _RAPID_OCR_ENGINE is not False else None


def _extract_page_spatial_and_plain_text(
    raw_img: Any, pdf_path: str | None = None, page_idx: int = 0
) -> tuple[str, str]:
    """Extracts layout-aware spatial text [pos: y=..., x=...] and plain text.

    1. For digital PDFs: uses PyMuPDF page.get_text("blocks")
    2. For scans/images: uses RapidOCR with word/line bounding boxes
    """
    spatial_lines: list[str] = []
    plain_lines: list[str] = []

    # 1. Try PyMuPDF digital text extraction if PDF path is provided
    if pdf_path and os.path.isfile(pdf_path) and pdf_path.lower().endswith(".pdf"):
        try:
            import fitz

            with fitz.open(pdf_path) as doc:
                if 0 <= page_idx < len(doc):
                    page = doc[page_idx]
                    page_w = page.rect.width
                    page_h = page.rect.height
                    text_dict = page.get_text("dict")
                    if isinstance(text_dict, dict):
                        for b in text_dict.get("blocks", []):
                            if isinstance(b, dict) and b.get("type") == 0:  # text block
                                for line in b.get("lines", []):
                                    if isinstance(line, dict):
                                        line_bbox = line.get("bbox", (0, 0, 0, 0))
                                        line_text = "".join(
                                            span.get("text", "")
                                            for span in line.get("spans", [])
                                            if isinstance(span, dict)
                                        ).strip()
                                        if line_text:
                                            norm_y = round(line_bbox[1] / page_h, 2) if page_h > 0 else 0.0
                                            norm_x = round(line_bbox[0] / page_w, 2) if page_w > 0 else 0.0
                                            spatial_lines.append(f"[pos: y={norm_y:.2f}, x={norm_x:.2f}] {line_text}")
                                            plain_lines.append(line_text)
                    total_chars = sum(len(line_item) for line_item in plain_lines)
                    if total_chars >= 30:
                        return "\n".join(spatial_lines), "\n".join(plain_lines)
        except Exception as e:
            logger.debug("PyMuPDF digital text extraction skipped: %s", e)

    # 2. RapidOCR fallback on raw_img (scans, photos, image files)
    if raw_img is not None:
        try:
            from PIL import Image

            if hasattr(raw_img, "samples") and hasattr(raw_img, "width"):
                raw_img = Image.frombytes("RGB", (raw_img.width, raw_img.height), raw_img.samples)
        except (AttributeError, OSError, ValueError):
            logger.debug("Image conversion for OCR failed", exc_info=True)

        engine = _get_rapid_ocr()
        if engine is not None:
            try:
                import numpy as np
                from PIL import Image

                if isinstance(raw_img, Image.Image):
                    img_np = np.array(raw_img)
                elif isinstance(raw_img, np.ndarray):
                    img_np = raw_img
                else:
                    img_np = None

                if img_np is not None:
                    with _OCR_LOCK:
                        res, _ = engine(img_np)
                    if res:
                        img_h, img_w = img_np.shape[:2]
                        ocr_spatial = []
                        ocr_plain = []
                        for item in res:
                            box, text, _ = item
                            t = text.strip()
                            if t:
                                xs = [float(p[0]) for p in box]
                                ys = [float(p[1]) for p in box]
                                min_x = min(xs) if xs else 0.0
                                min_y = min(ys) if ys else 0.0
                                norm_y = round(min_y / img_h, 2) if img_h > 0 else 0.0
                                norm_x = round(min_x / img_w, 2) if img_w > 0 else 0.0
                                ocr_spatial.append(f"[pos: y={norm_y:.2f}, x={norm_x:.2f}] {t}")
                                ocr_plain.append(t)
                        return "\n".join(ocr_spatial), "\n".join(ocr_plain)
            except Exception as e:
                logger.debug("RapidOCR spatial text extraction failed: %s", e)

    return "", ""


class ExtractionPipeline:
    """Performs page classification, extraction tiers, and multi-resolution voting."""

    def __init__(
        self,
        config: AppConfig,
        image_preprocessor: ImagePreprocessor,
        llm_extractor: LLMExtractor,
    ):
        self.config = config
        self.image_preprocessor = image_preprocessor
        self.llm_extractor = llm_extractor

    def preload(self) -> None:
        """Preloads LLM, RapidOCR ONNX models, and pre-initializes execution graphs."""
        # 1. Warm up Vision-LLM
        try:
            self.llm_extractor.preload()
        except Exception as e:
            logger.warning("[!] LLM preload warning: %s", e)

        # 2. Warm up RapidOCR ONNX runtime providers & inference sessions
        try:
            engine = _get_rapid_ocr()
            if engine is not None and engine is not False:
                import numpy as np

                dummy_np = np.zeros((64, 64, 3), dtype=np.uint8)
                with _OCR_LOCK:
                    engine(dummy_np)
                logger.info("[+] RapidOCR engine warmed up.")
        except Exception as e:
            logger.debug("RapidOCR warmup pass skipped: %s", e)

        # 3. Pre-import fitz (PyMuPDF)
        try:
            import fitz  # noqa: F401
        except ImportError:
            pass

    def classify_single_page(self, raw_img: Any, idx: int, pdf_path: str | None = None) -> dict[str, Any]:
        """Pre-processing, spatial text extraction, and classification of a single page."""
        logger.debug(f"[*] Phase 1 (Classification): Page {idx + 1}")

        prep_img = self.image_preprocessor.prepare_base_image(raw_img)
        b64_img = self.image_preprocessor.scale_and_encode_image(prep_img, self.config.classify_dimension)

        doc_type_result = self.llm_extractor.classify_image(b64_img)
        doc_type = doc_type_result.get("Document", "") if isinstance(doc_type_result, dict) else str(doc_type_result)
        logger.info(f"[+] Page {idx + 1} classification: {doc_type}")

        matched_name, matched_info = self.llm_extractor.find_doc_type_config(doc_type)

        vision_description = ""
        if matched_name.upper() == "UNKNOWN" and idx == 0:
            vision_description = self.llm_extractor.describe_image(b64_img)
            if vision_description:
                logger.info(f"[+] Page {idx + 1} unknown document description: '{vision_description}'")

        if matched_name.upper() in {"UNKNOWN", "EMPTY"}:
            matched_info = {}

        spatial_text, ocr_text = _extract_page_spatial_and_plain_text(raw_img, pdf_path=pdf_path, page_idx=idx)

        return {
            "idx": idx,
            "page_num": idx + 1,
            "raw_img": raw_img,
            "prep_img": prep_img,
            "b64_img": b64_img,
            "doc_type": doc_type,
            "matched_name": matched_name,
            "matched_info": matched_info,
            "spatial_text": spatial_text,
            "ocr_text": ocr_text,
            "pdf_path": pdf_path,
            "vision_description": vision_description,
        }

    def run_extraction_tier(
        self,
        group_pages: list,
        doc_type: str,
        dimension: int,
        label: str,
        target_fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Runs a visual extraction tier at the given resolution (px).

        Optionally queries only specific conflict fields via target_fields.
        """
        logging.info(f"[*] Starting {label}...")
        tier_page_results = []
        for p in group_pages:
            p_num = p.get("page_num", 1)
            p_type = p.get("matched_name", doc_type)
            p_info = p.get("matched_info", {})
            p_fields = p_info.get("extraction_fields", {})
            p_sig = p_info.get("validation", {}).get("signature_required", False)

            # Skip KI request if page type has no extraction fields and no signature required
            if not p_fields and not p_sig:
                logging.info(f"[*] Page {p_num} ({p_type}): No extraction fields configured. Skipping KI request.")
                tier_page_results.append({})
                continue

            # Skip KI request if target_fields is set and page has none of the target fields
            if target_fields is not None:
                target_set_lower = {f.lower() for f in target_fields}
                page_fields_lower = {f.lower() for f in p_fields.keys()}
                if p_sig:
                    page_fields_lower.add("signed")
                if not (page_fields_lower & target_set_lower):
                    logging.debug(
                        f"[*] Page {p_num} ({p_type}) {label}: Skipped (no matching target fields for this page type)."
                    )
                    tier_page_results.append({})
                    continue

            img_b64 = self.image_preprocessor.get_prepared_page_image(p, dimension)
            ext = self.llm_extractor.extract_data_from_images_with_type(
                img_b64, p_type, temperature=0.0, target_fields=target_fields
            )
            res = ext if isinstance(ext, dict) else {}
            tier_page_results.append(res)
            logging.info(f"[*] Page {p_num} ({p_type}) {label} result: {res}")

        return tier_page_results

    def run_text_extraction_tier(
        self,
        group_pages: list,
        doc_type: str,
        label: str = "Tier 1 (Spatial Text)",
        target_fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Runs an extraction pass over layout-aware spatial text for all pages."""
        logging.info(f"[*] Starting {label}...")
        tier_page_results = []
        for p in group_pages:
            p_num = p.get("page_num", 1)
            p_type = p.get("matched_name", doc_type)
            p_info = p.get("matched_info", {})
            p_fields = p_info.get("extraction_fields", {})

            # Skip if page type has no extraction fields
            if not p_fields:
                tier_page_results.append({})
                continue

            # Skip if target_fields is set and page has none of the target fields (excluding Signed for text pass)
            if target_fields is not None:
                target_set_lower = {f.lower() for f in target_fields if f.lower() != "signed"}
                page_fields_lower = {f.lower() for f in p_fields.keys()}
                if not (page_fields_lower & target_set_lower):
                    logging.debug(
                        f"[*] Page {p_num} ({p_type}) {label}: Skipped (no matching target fields for this page type)."
                    )
                    tier_page_results.append({})
                    continue

            spatial_text = p.get("spatial_text", "")
            if not spatial_text or len(spatial_text.strip()) < 10:
                logging.debug(f"[*] Page {p_num} ({p_type}) {label}: No spatial text available. Skipping text pass.")
                tier_page_results.append({})
                continue

            ext = self.llm_extractor.extract_data_from_text_with_type(
                spatial_text, p_type, temperature=0.0, target_fields=target_fields
            )
            res = ext if isinstance(ext, dict) else {}
            tier_page_results.append(res)
            logging.info(f"[*] Page {p_num} ({p_type}) {label} result: {res}")

        return tier_page_results

    def process_page_group(self, doc_type: str, group_pages: list) -> dict | None:
        """Phase 2: Extraction and signature check on a bundled page group."""
        res = self.process_document_pages(group_pages)
        if res:
            res["Document"] = doc_type
        return res

    def process_document_pages(self, document_pages: list[dict[str, Any]]) -> dict[str, Any] | None:
        """Runs tiered extraction across ALL non-empty pages of a document in one unified pool."""
        if not document_pages:
            return None

        page_nums = [p["page_num"] for p in document_pages]

        # Collect validation configs across all pages
        optional_fields = set()
        expected_fields = set()
        needs_signature = False

        for p in document_pages:
            info = p.get("matched_info", {})
            if info:
                v_cfg = info.get("validation", {})
                optional_fields.update(v_cfg.get("optional_fields", []))
                expected_fields.update(info.get("extraction_fields", {}).keys())
                if v_cfg.get("signature_required", False):
                    needs_signature = True

        if needs_signature:
            expected_fields.add("Signed")

        # ── Fast path: No extraction fields AND no signature check needed → skip KI requests ──
        if not expected_fields and not needs_signature:
            d_type = document_pages[0].get("matched_name") or "UNKNOWN"
            logging.info(
                f"[+] Document '{d_type}' (pages {page_nums}): No extraction fields configured and no signature required. Skipping KI requests."
            )
            desc = next((p.get("vision_description") for p in document_pages if p.get("vision_description")), "")
            res: dict[str, Any] = {
                "Document": d_type,
                "pages": page_nums,
                "Signed": False,
                "_confidence": {},
            }
            if desc:
                res["vision_description"] = desc
            return res

        t1_dim = getattr(self.config, "tier1_dimension", 1260)
        t2_dim = getattr(self.config, "tier2_dimension", 1512)
        t3_dim = getattr(self.config, "tier3_dimension", 1764)

        # ── Step 1: Spatial OCR-LLM Pass (Layout-Aware Text) ──
        text_pass_results = self.run_text_extraction_tier(document_pages, "Document", "Spatial OCR-LLM Pass")

        # ── Step 2: Vision-LLM Tier 1 ──
        t1_vision_results = self.run_extraction_tier(document_pages, "Document", t1_dim, "Vision-LLM Tier 1")

        # ── Evaluate individual field consensus after Tier 1 ──
        all_keys_after_t1 = set()
        for res_list in (t1_vision_results, text_pass_results):
            for res in res_list:
                if isinstance(res, dict):
                    all_keys_after_t1.update(res.keys())
        all_keys_after_t1 -= _EXCLUDE_KEYS
        if needs_signature:
            all_keys_after_t1.add("Signed")

        MIN_EVIDENCE_WEIGHT = 1.25
        group_final, confidences, winning_weights, pending_fields = _evaluate_round(
            field_names=all_keys_after_t1,
            results_lists=[t1_vision_results, text_pass_results],
            tier_names=["tier1", "text"],
            optional_fields=optional_fields,
            min_evidence_weight=MIN_EVIDENCE_WEIGHT,
        )

        for pf in pending_fields:
            logger.info(
                "[*] Field '%s' pending after Tier 1 (consensus=%.2f, weight=%.2f < %.2f). Queued for Tier 2.",
                pf,
                confidences.get(pf, 0.0),
                winning_weights.get(pf, 0.0),
                MIN_EVIDENCE_WEIGHT,
            )

        # ── If all fields validated (evidence weight >= 1.25 and K >= 0.67), finalize ──
        if not pending_fields and len(all_keys_after_t1) > 0:
            logger.info(
                f"[+] All {len(all_keys_after_t1)} field(s) validated with >= 2 measurements (evidence weight >= {MIN_EVIDENCE_WEIGHT}). Finalizing document."
            )
            if "Signed" not in group_final:
                group_final["Signed"] = any(
                    _to_bool_value(res.get("Signed", False)) for res in t1_vision_results if isinstance(res, dict)
                )
            desc = next((p.get("vision_description") for p in document_pages if p.get("vision_description")), "")
            if desc and "vision_description" not in group_final:
                group_final["vision_description"] = desc
            group_final["pages"] = page_nums
            group_final["_confidence"] = confidences
            return group_final

        # ── Step 3: Vision-LLM Tier 2 for pending fields ──
        t2_target_fields = [
            f
            for f in (expected_fields | all_keys_after_t1)
            if confidences.get(f, 0.0) < CONSENSUS_THRESHOLD or winning_weights.get(f, 0.0) < MIN_EVIDENCE_WEIGHT
        ]
        if not t2_target_fields:
            t2_target_fields = None

        logger.info(f"[*] Starting Vision-LLM Tier 2 for pending fields: {t2_target_fields}...")
        t2_page_results = self.run_extraction_tier(
            document_pages,
            "Document",
            t2_dim,
            "Vision-LLM Tier 2",
            target_fields=t2_target_fields,
        )

        if (
            not any(bool(r) for r in t1_vision_results)
            and not any(bool(r) for r in text_pass_results)
            and not any(bool(r) for r in t2_page_results)
        ):
            logger.warning(f"[-] No valid extractions across all {len(document_pages)} pages.")
            return None

        all_keys = set()
        for res_list in (t1_vision_results, text_pass_results, t2_page_results):
            for res in res_list:
                if isinstance(res, dict):
                    all_keys.update(res.keys())
        all_keys -= _EXCLUDE_KEYS
        if needs_signature:
            all_keys.add("Signed")

        t2_final, t2_conf, t2_weights, conflicts = _evaluate_round(
            field_names=all_keys,
            results_lists=[t1_vision_results, text_pass_results, t2_page_results],
            tier_names=["tier1", "text", "tier2"],
            optional_fields=optional_fields,
            min_evidence_weight=0.0,
        )
        group_final.update(t2_final)
        confidences.update(t2_conf)
        winning_weights.update(t2_weights)

        # ── Step 4: Vision-LLM Tier 3 Tiebreaker on conflict fields ──
        if conflicts:
            logger.info(f"[*] Disagreement in field(s) {conflicts} detected. Starting Vision-LLM Tier 3 Tiebreaker...")
            t3_page_results = self.run_extraction_tier(
                document_pages,
                "Document",
                t3_dim,
                "Vision-LLM Tier 3 Tiebreaker",
                target_fields=conflicts,
            )

            t3_final, t3_conf, _, _ = _evaluate_round(
                field_names=set(conflicts),
                results_lists=[t1_vision_results, text_pass_results, t2_page_results, t3_page_results],
                tier_names=["tier1", "text", "tier2", "tier3"],
                optional_fields=optional_fields,
                min_evidence_weight=0.0,
            )
            group_final.update(t3_final)
            confidences.update(t3_conf)

        if "Signed" not in group_final:
            group_final["Signed"] = any(
                _to_bool_value(res.get("Signed", False))
                for res_list in (t1_vision_results, t2_page_results)
                for res in res_list
                if isinstance(res, dict)
            )

        desc = next((p.get("vision_description") for p in document_pages if p.get("vision_description")), "")
        if desc and "vision_description" not in group_final:
            group_final["vision_description"] = desc

        group_final["pages"] = page_nums
        group_final["_confidence"] = confidences
        return group_final

    def validate_extracted_data(self, extracted: dict[str, Any] | None) -> tuple[bool, str]:
        """Generically validates consistency and required fields of extracted data."""
        if not extracted:
            return False, "No data extracted"

        dok_art_raw = str(extracted.get("Document", "")).strip()
        if not dok_art_raw or is_missing_value(dok_art_raw) or dok_art_raw.upper() in ("UNKNOWN", "EMPTY"):
            return False, "Document unknown or missing"

        page_results = extracted.get("page_results") or [extracted]
        for idx, res in enumerate(page_results, 1):
            d_art = str(res.get("Document", "")).strip()
            if not d_art or is_missing_value(d_art) or d_art.upper() in ("UNKNOWN", "EMPTY"):
                page_info = f"on page group {idx}" if len(page_results) > 1 else "on the document"
                return False, f"Document unknown or missing {page_info}"

            matched_type, matched_info = self.llm_extractor.find_doc_type_config(d_art)
            if not matched_type or matched_type.upper() == "UNKNOWN":
                return False, f"Document type '{d_art}' unknown or missing"

            extraction_fields = matched_info.get("extraction_fields", {})
            validation_cfg: dict[str, Any] = matched_info.get("validation") or {}
            optional_fields = set(validation_cfg.get("optional_fields", []))
            confidences = dict(extracted.get("_confidence", {}))
            if isinstance(res.get("_confidence"), dict):
                confidences.update(res["_confidence"])

            for field in extraction_fields:
                if field in optional_fields:
                    continue
                val = res.get(field)
                if is_missing_value(val):
                    val = extracted.get(field)
                if isinstance(val, bool):
                    continue
                if is_missing_value(val):
                    return (
                        False,
                        f"Required field '{field}' is missing or invalid in {matched_type}",
                    )
                conf = confidences.get(field, 1.0)
                if conf < CONSENSUS_THRESHOLD:
                    return (
                        False,
                        f"Low confidence for required field '{field}' (K={conf:.2f}) in {matched_type} – manual review required",
                    )

            if validation_cfg.get("signature_required", False):
                has_sig = _to_bool_value(res.get("Signed", False)) or _to_bool_value(extracted.get("Signed", False))
                if not has_sig:
                    return False, f"Signature missing on document ({matched_type})"

        return True, "OK"
