"""
OrdinFlow — Extraction Pipeline Module
Domain-agnostic module for page classification, multi-resolution extraction tiers, and voting algorithms.
"""

import logging
import os
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any

logger = logging.getLogger(__name__)

from core.config import AppConfig
from core.image_processing import ImagePreprocessor
from core.utils import (
    MISSING_PLACEHOLDER,
    is_missing_value,
)
from core.vision import LLMExtractor

_RAPID_OCR_ENGINE = None


def _get_rapid_ocr():
    global _RAPID_OCR_ENGINE
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

            doc = fitz.open(pdf_path)
            if 0 <= page_idx < len(doc):
                page = doc[page_idx]
                page_w = page.rect.width
                page_h = page.rect.height
                blocks = page.get_text("blocks")
                for b in blocks:
                    if len(b) >= 7 and b[6] == 0:  # text block
                        text = str(b[4]).strip()
                        if text:
                            norm_y = round(b[1] / page_h, 2) if page_h > 0 else 0.0
                            norm_x = round(b[0] / page_w, 2) if page_w > 0 else 0.0
                            for line in text.split("\n"):
                                l_str = line.strip()
                                if l_str:
                                    spatial_lines.append(
                                        f"[pos: y={norm_y:.2f}, x={norm_x:.2f}] {l_str}"
                                    )
                                    plain_lines.append(l_str)
                doc.close()
                total_chars = sum(len(line_item) for line_item in plain_lines)
                if total_chars >= 30:
                    return "\n".join(spatial_lines), "\n".join(plain_lines)
            else:
                doc.close()
        except Exception as e:
            logger.debug("PyMuPDF digital text extraction skipped: %s", e)

    # 2. RapidOCR fallback on raw_img (scans, photos, image files)
    if raw_img is not None:
        try:
            from PIL import Image

            if hasattr(raw_img, "samples") and hasattr(raw_img, "width"):
                raw_img = Image.frombytes(
                    "RGB", (raw_img.width, raw_img.height), raw_img.samples
                )
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
                                ocr_spatial.append(
                                    f"[pos: y={norm_y:.2f}, x={norm_x:.2f}] {t}"
                                )
                                ocr_plain.append(t)
                        return "\n".join(ocr_spatial), "\n".join(ocr_plain)
            except Exception as e:
                logger.debug("RapidOCR spatial text extraction failed: %s", e)

    return "", ""


def _run_ocr_with_bin_filter(raw_img: Any) -> str:
    """Runs OCR on the raw image for name matching (uses RapidOCR/ONNX)."""
    _, plain = _extract_page_spatial_and_plain_text(raw_img)
    return plain


def _is_bool_value(val: Any) -> bool:
    """Generically checks whether a value is a boolean."""
    if isinstance(val, bool):
        return True
    if isinstance(val, str) and val.strip().lower() in (
        "true",
        "false",
        "yes",
        "no",
        "ja",
        "nein",
        "1",
        "0",
    ):
        return True
    return False


def _to_bool_value(val: Any) -> bool:
    """Generically converts a string or boolean value to a Python bool."""
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().lower() in ("true", "1", "yes", "ja")
    return bool(val)


# ──────────────────────────────────────────────────────────────
# Empirical weighting (based on log data)
# Dual-Source Tier 1: 1396px (weight 1.0) + Spatial Text (weight 1.0)
# Tier 2: 1536px (weight 1.25), Tier 3: 1676px (weight 1.5)
# ──────────────────────────────────────────────────────────────
TIER_WEIGHTS: dict[int | str, float] = {
    1396: 1.0,
    "text": 1.0,
    1536: 1.25,
    1676: 1.5,
    0: 1.0,
}
KONSENS_THRESHOLD = 0.67

# Fields excluded when collecting keys from extraction results
_EXCLUDE_KEYS = {
    "Document",
    "pages",
    "page_results",
    "description",
    "vision_description",
}


_UMLAUT_MAP = str.maketrans(
    {
        "ä": "ae",
        "ö": "oe",
        "ü": "ue",
        "ß": "ss",
    }
)


def _normalize_for_clustering(val: str) -> str:
    """Normalizes text for fuzzy voting."""
    if not isinstance(val, str):
        val = str(val)
    normed = val.casefold().translate(_UMLAUT_MAP)
    normed = "".join(
        c
        for c in unicodedata.normalize("NFD", normed)
        if unicodedata.category(c) != "Mn"
    )
    normed = re.sub(r"\s+", " ", normed).strip()
    return normed


def _fuzz_similarity(a: str, b: str) -> float:
    """Calculates similarity between two strings (0.0 to 1.0)."""
    return SequenceMatcher(
        None, _normalize_for_clustering(a), _normalize_for_clustering(b)
    ).ratio()


def _are_similar_or_substring(a: str, b: str, threshold: float = 0.80) -> bool:
    """Checks whether two strings are fuzzy similar OR if one is a token/substring subset of the other."""
    # Differing numbers/digits indicate distinct IDs, dates, or amounts and must not be clustered
    digits_a = re.findall(r"\d+", a)
    digits_b = re.findall(r"\d+", b)
    if digits_a and digits_b and digits_a != digits_b:
        return False

    if _fuzz_similarity(a, b) >= threshold:
        return True

    norm_a = _normalize_for_clustering(a)
    norm_b = _normalize_for_clustering(b)
    if not norm_a or not norm_b or len(norm_a) < 3 or len(norm_b) < 3:
        return False

    # 1-character typo allowance for short names (e.g. Audre vs Andre)
    if (
        abs(len(norm_a) - len(norm_b)) <= 1
        and min(len(norm_a), len(norm_b)) >= 4
        and _fuzz_similarity(norm_a, norm_b) >= 0.75
    ):
        return True

    # Direct substring inclusion
    if norm_a in norm_b or norm_b in norm_a:
        return True

    # Token/word subset check (e.g. 'Wannink' inside 'Bramkamp-Wannink')
    clean_a = re.sub(r"[-,\s]+", " ", norm_a).split()
    clean_b = re.sub(r"[-,\s]+", " ", norm_b).split()
    set_a = set(clean_a)
    set_b = set(clean_b)
    if set_a and set_b and (set_a.issubset(set_b) or set_b.issubset(set_a)):
        return True

    return False


def _pick_best_representative(members: list[tuple[str, float]]) -> str:
    """Selects the cleanest/most canonical spelling from cluster members.

    Priority order:
    1. Vote weight count (the most frequently extracted spelling wins)
    2. String length (longest name breaks ties between equal vote counts)
    3. Casing score (prefer uppercase / proper capitalization)
    """
    counts: dict[str, float] = {}
    for val, w in members:
        counts[val] = counts.get(val, 0.0) + w

    def score(v: str) -> tuple[float, int, int]:
        casing_score = sum(1 for c in v if c.isupper())
        return (counts[v], len(v), casing_score)

    return max(counts.keys(), key=score)


def _cluster_votes(
    votes: list[tuple[str, float]],
    threshold: float = 0.85,
) -> list[dict]:
    """Groups similarly-sounding or substring-related values into clusters and selects the best spelling."""
    clusters: list[dict] = []

    for val, weight in votes:
        matched_cluster = None
        for cluster in clusters:
            if _are_similar_or_substring(
                val, cluster["representative"], threshold=threshold
            ):
                matched_cluster = cluster
                break

        if matched_cluster:
            matched_cluster["members"].append((val, weight))
            matched_cluster["total_weight"] += weight
            matched_cluster["representative"] = _pick_best_representative(
                matched_cluster["members"]
            )
        else:
            clusters.append(
                {
                    "representative": _pick_best_representative([(val, weight)]),
                    "members": [(val, weight)],
                    "total_weight": weight,
                }
            )

    return clusters


def _evaluate_field_consensus(
    field: str,
    page_results_lists: list[list[dict]],
    tier_resolutions: list[int | str],
) -> tuple[Any, float, dict]:
    """Calculates the weighted consensus for a field.

    Logic:
    1. Collects all votes with resolution weighting (incl. explicit True/False for booleans)
    2. Fuzzy clustering (Levenshtein >= 0.85) with canonical representative
    3. Calculates K(f) = sum_w_top / sum_w_total
    """
    weighted_votes: list[tuple[str, float]] = []
    is_boolean_field = False

    for tier_idx, res_list in enumerate(page_results_lists):
        weight = TIER_WEIGHTS.get(tier_resolutions[tier_idx], 1.0)
        for res in res_list:
            if not isinstance(res, dict):
                continue
            v = res.get(field)
            if _is_bool_value(v):
                is_boolean_field = True
                bool_str = "True" if _to_bool_value(v) else "False"
                weighted_votes.append((bool_str, weight))
            elif not is_missing_value(v):
                weighted_votes.append((str(v), weight))

    if not weighted_votes:
        return (False, 1.0, {}) if is_boolean_field else (MISSING_PLACEHOLDER, 0.0, {})

    clusters = _cluster_votes(weighted_votes, threshold=0.80)
    if not clusters:
        return (False, 1.0, {}) if is_boolean_field else (MISSING_PLACEHOLDER, 0.0, {})

    top_cluster = max(clusters, key=lambda c: c["total_weight"])
    total_weight = sum(c["total_weight"] for c in clusters)
    confidence_k = (
        top_cluster["total_weight"] / total_weight if total_weight > 0 else 0.0
    )

    raw_winner = top_cluster["representative"]
    if is_boolean_field:
        winner_value = _to_bool_value(raw_winner)
        counts_info = {
            _to_bool_value(c["representative"]): round(c["total_weight"], 2)
            for c in clusters
        }
    else:
        winner_value = raw_winner
        counts_info = {
            c["representative"]: round(c["total_weight"], 2) for c in clusters
        }

    return winner_value, confidence_k, counts_info


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

    def classify_single_page(
        self, raw_img: Any, idx: int, pdf_path: str | None = None
    ) -> dict[str, Any]:
        """Pre-processing, spatial text extraction, and classification of a single page."""
        logger.debug(f"[*] Phase 1 (Classification): Page {idx + 1}")

        prep_img = self.image_preprocessor.prepare_base_image(raw_img)
        b64_img = self.image_preprocessor.scale_and_encode_image(
            prep_img, self.config.classify_dimension
        )

        doc_type_result = self.llm_extractor.classify_image(b64_img)
        doc_type = (
            doc_type_result.get("Document", "")
            if isinstance(doc_type_result, dict)
            else str(doc_type_result)
        )
        logger.info(f"[+] Page {idx + 1} classification: {doc_type}")

        matched_name, matched_info = self.llm_extractor.find_doc_type_config(doc_type)
        if matched_name.upper() in {"UNKNOWN", "EMPTY"}:
            matched_info = {}

        spatial_text, ocr_text = _extract_page_spatial_and_plain_text(
            raw_img, pdf_path=pdf_path, page_idx=idx
        )

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
        logging.info(f"[*] Starting {label} ({dimension}px)...")
        tier_page_results = []
        for p in group_pages:
            p_num = p.get("page_num", 1)
            p_type = p.get("matched_name", doc_type)
            p_info = p.get("matched_info", {})
            p_fields = p_info.get("extraction_fields", {})
            p_sig = p_info.get("validation", {}).get("signature_required", False)

            # Skip KI request if page type has no extraction fields and no signature required
            if not p_fields and not p_sig:
                logging.info(
                    f"[*] Page {p_num} ({p_type}): No extraction fields configured. Skipping KI request."
                )
                tier_page_results.append({})
                continue

            img_b64 = (
                p.get("b64_img")
                if p.get("prep_img") is None
                else self.image_preprocessor.scale_and_encode_image(
                    p["prep_img"], dimension
                )
            )
            ext = self.llm_extractor.extract_data_from_images_with_type(
                img_b64, p_type, temperature=0.0, target_fields=target_fields
            )
            res = ext if isinstance(ext, dict) else {}
            tier_page_results.append(res)
            if not res and target_fields:
                logging.debug(
                    f"[*] Page {p_num} ({p_type}) {label}: Skipped (no matching target fields for this page type)."
                )
            else:
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

            spatial_text = p.get("spatial_text", "")
            if not spatial_text or len(spatial_text.strip()) < 10:
                logging.debug(
                    f"[*] Page {p_num} ({p_type}) {label}: No spatial text available. Skipping text pass."
                )
                tier_page_results.append({})
                continue

            ext = self.llm_extractor.extract_data_from_text_with_type(
                spatial_text, p_type, temperature=0.0, target_fields=target_fields
            )
            res = ext if isinstance(ext, dict) else {}
            tier_page_results.append(res)
            if not res and target_fields:
                logging.debug(
                    f"[*] Page {p_num} ({p_type}) {label}: Skipped (no matching target fields for this page type)."
                )
            else:
                logging.info(f"[*] Page {p_num} ({p_type}) {label} result: {res}")

        return tier_page_results

    def process_page_group(self, doc_type: str, group_pages: list) -> dict | None:
        """Phase 2: Extraction and signature check on a bundled page group."""
        res = self.process_document_pages(group_pages)
        if res:
            res["Document"] = doc_type
        return res

    def process_document_pages(
        self, document_pages: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
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
            return {
                "Document": d_type,
                "pages": page_nums,
                "Signed": False,
                "_confidence": {},
            }

        # ── Step 1: Spatial OCR-LLM Pass (Layout-Aware Text) ──
        text_pass_results = self.run_text_extraction_tier(
            document_pages, "Document", "Spatial OCR-LLM Pass"
        )

        # ── Step 2: Vision-LLM Tier 1 (1396px) ──
        t1_vision_results = self.run_extraction_tier(
            document_pages, "Document", 1396, "Vision-LLM Tier 1 (1396px)"
        )

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
        confidences: dict[str, float] = {}
        winning_weights: dict[str, float] = {}
        group_final: dict[str, Any] = {}
        pending_fields: list[str] = []

        for field_name in all_keys_after_t1:
            is_optional_empty = field_name in optional_fields and all(
                is_missing_value(res.get(field_name))
                for res_list in (t1_vision_results, text_pass_results)
                for res in res_list
                if isinstance(res, dict)
            )
            if is_optional_empty:
                confidences[field_name] = 1.0
                winning_weights[field_name] = MIN_EVIDENCE_WEIGHT
                group_final[field_name] = MISSING_PLACEHOLDER
            else:
                winner, k_score, counts = _evaluate_field_consensus(
                    field_name,
                    [t1_vision_results, text_pass_results],
                    [1396, "text"],
                )
                w_weight = counts.get(winner, 0.0)
                confidences[field_name] = k_score
                winning_weights[field_name] = w_weight
                if k_score >= KONSENS_THRESHOLD and w_weight >= MIN_EVIDENCE_WEIGHT:
                    group_final[field_name] = winner
                else:
                    pending_fields.append(field_name)
                    logging.info(
                        "[*] Field '%s' pending after Tier 1 (consensus=%.2f, weight=%.2f < %.2f). Queued for Tier 2.",
                        field_name,
                        k_score,
                        w_weight,
                        MIN_EVIDENCE_WEIGHT,
                    )

        # ── If all fields validated (evidence weight >= 1.25 and K >= 0.67), finalize ──
        if not pending_fields and len(all_keys_after_t1) > 0:
            logging.info(
                f"[+] All {len(all_keys_after_t1)} field(s) validated with >= 2 measurements (evidence weight >= {MIN_EVIDENCE_WEIGHT}). Finalizing document."
            )
            if "Signed" not in group_final:
                group_final["Signed"] = any(
                    _to_bool_value(res.get("Signed", False))
                    for res in t1_vision_results
                    if isinstance(res, dict)
                )
            group_final["pages"] = page_nums
            group_final["_confidence"] = confidences
            return group_final

        # ── Step 3: Vision-LLM Tier 2 (1536px) for pending fields ──
        t2_target_fields = [
            f
            for f in (expected_fields | all_keys_after_t1)
            if confidences.get(f, 0.0) < KONSENS_THRESHOLD
            or winning_weights.get(f, 0.0) < MIN_EVIDENCE_WEIGHT
        ]
        if not t2_target_fields:
            t2_target_fields = None

        logging.info(
            f"[*] Starting Vision-LLM Tier 2 (1536px) for pending fields: {t2_target_fields}..."
        )
        t2_page_results = self.run_extraction_tier(
            document_pages,
            "Document",
            1536,
            "Vision-LLM Tier 2 (1536px)",
            target_fields=t2_target_fields,
        )

        if (
            not any(bool(r) for r in t1_vision_results)
            and not any(bool(r) for r in text_pass_results)
            and not any(bool(r) for r in t2_page_results)
        ):
            logger.warning(
                f"[-] No valid extractions across all {len(document_pages)} pages."
            )
            return None

        all_keys = set()
        for res_list in (t1_vision_results, text_pass_results, t2_page_results):
            for res in res_list:
                if isinstance(res, dict):
                    all_keys.update(res.keys())
        all_keys -= _EXCLUDE_KEYS
        if needs_signature:
            all_keys.add("Signed")

        conflicts: list[str] = []

        for field_name in all_keys:
            is_optional_empty = field_name in optional_fields and all(
                is_missing_value(res.get(field_name))
                for res_list in (t1_vision_results, text_pass_results, t2_page_results)
                for res in res_list
                if isinstance(res, dict)
            )
            if is_optional_empty:
                confidences[field_name] = 1.0
                group_final[field_name] = MISSING_PLACEHOLDER
            else:
                winner, k_score, counts = _evaluate_field_consensus(
                    field_name,
                    [t1_vision_results, text_pass_results, t2_page_results],
                    [1396, "text", 1536],
                )
                w_weight = counts.get(winner, 0.0)
                confidences[field_name] = k_score
                winning_weights[field_name] = w_weight
                if k_score >= KONSENS_THRESHOLD:
                    group_final[field_name] = winner
                else:
                    conflicts.append(field_name)

        # ── Step 4: Vision-LLM Tier 3 Tiebreaker (1676px) on conflict fields ──
        if conflicts:
            logger.info(
                f"[*] Disagreement in field(s) {conflicts} detected. Starting Vision-LLM Tier 3 Tiebreaker (1676px)..."
            )
            t3_page_results = self.run_extraction_tier(
                document_pages,
                "Document",
                1676,
                "Vision-LLM Tier 3 Tiebreaker (1676px)",
                target_fields=conflicts,
            )

            for field_name in conflicts:
                winner, k_score, counts = _evaluate_field_consensus(
                    field_name,
                    [
                        t1_vision_results,
                        text_pass_results,
                        t2_page_results,
                        t3_page_results,
                    ],
                    [1396, "text", 1536, 1676],
                )
                confidences[field_name] = k_score
                if winner and not is_missing_value(winner):
                    group_final[field_name] = winner
                else:
                    group_final[field_name] = MISSING_PLACEHOLDER

        if "Signed" not in group_final:
            group_final["Signed"] = any(
                _to_bool_value(res.get("Signed", False))
                for res_list in (t1_vision_results, t2_page_results)
                for res in res_list
                if isinstance(res, dict)
            )

        group_final["pages"] = page_nums
        group_final["_confidence"] = confidences
        return group_final

    def validate_extracted_data(
        self, extracted: dict[str, Any] | None
    ) -> tuple[bool, str]:
        """Generically validates consistency and required fields of extracted data."""
        if not extracted:
            return False, "No data extracted"

        dok_art_raw = str(extracted.get("Document", "")).strip()
        if (
            not dok_art_raw
            or is_missing_value(dok_art_raw)
            or dok_art_raw.upper() in ("UNKNOWN", "EMPTY")
        ):
            return False, "Document unknown or missing"

        page_results = extracted.get("page_results") or [extracted]
        for idx, res in enumerate(page_results, 1):
            d_art = str(res.get("Document", "")).strip()
            if (
                not d_art
                or is_missing_value(d_art)
                or d_art.upper() in ("UNKNOWN", "EMPTY")
            ):
                page_info = (
                    f"on page group {idx}"
                    if len(page_results) > 1
                    else "on the document"
                )
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
                if conf < KONSENS_THRESHOLD:
                    return (
                        False,
                        f"Low confidence for required field '{field}' (K={conf:.2f}) in {matched_type} – manual review required",
                    )

            if validation_cfg.get("signature_required", False):
                has_sig = _to_bool_value(res.get("Signed", False)) or _to_bool_value(
                    extracted.get("Signed", False)
                )
                if not has_sig:
                    return False, f"Signature missing on document ({matched_type})"

        return True, "OK"
