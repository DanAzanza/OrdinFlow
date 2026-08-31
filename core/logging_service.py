"""Service for parsing and computing log analytics and statistics."""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


def get_empty_log_stats() -> dict[str, Any]:
    """Returns baseline zeroed statistics structure."""
    return {
        "recordsCount": 0,
        "totalFiles": 0,
        "completedFiles": 0,
        "manualReviewFiles": 0,
        "abortedFiles": 0,
        "emptyFiles": 0,
        "splitBatches": 0,
        "partialDocsSaved": 0,
        "directDocsMoved": 0,
        "totalArchivedDocs": 0,
        "successRate": "100.0",
        "totalProcessingTime": "0.0",
        "maxProcessingTime": "0.0",
        "avgTimePerFile": "0.0",
        "avgTimePerPage": "0.0",
        "totalPages": 0,
        "categoryCounts": {},
        "tier1Count": 0,
        "tier1DirectConsensus": 0,
        "tier2Count": 0,
        "tier2Resolved": 0,
        "tier3Count": 0,
        "tier3Resolved": 0,
        "earlyStopCount": 0,
        "infoCount": 0,
        "warnCount": 0,
        "errorCount": 0,
    }


def compute_log_stats(lines: list[str], valid_doc_types: list[str] | None = None) -> dict[str, Any]:
    """Parses log lines to compute aggregate performance and routing metrics."""
    completed_files = 0
    manual_review_files = 0
    aborted_files = 0
    empty_files = 0

    total_processing_time = 0.0
    max_processing_time = 0.0
    total_pages = 0

    split_batches = 0
    partial_docs_saved = 0
    direct_docs_moved = 0

    category_counts: dict[str, int] = {}
    tier1_count = 0
    tier1_direct_consensus = 0
    tier2_count = 0
    tier3_count = 0

    info_count = 0
    warn_count = 0
    error_count = 0

    for line in lines:
        if " [INFO] " in line:
            info_count += 1
        elif " [WARNING] " in line or " [WARN] " in line:
            warn_count += 1
        elif " [ERROR] " in line or " [CRITICAL] " in line:
            error_count += 1

        match_completed = re.search(r"completed successfully after ([\d\.]+) seconds", line, re.IGNORECASE)
        if match_completed:
            completed_files += 1
            secs = float(match_completed.group(1))
            total_processing_time += secs
            if secs > max_processing_time:
                max_processing_time = secs

        match_incomplete = re.search(r"incomplete \(([\d\.]+)s\)", line, re.IGNORECASE)
        if match_incomplete:
            manual_review_files += 1
            secs = float(match_incomplete.group(1))
            total_processing_time += secs
            if secs > max_processing_time:
                max_processing_time = secs

        match_abort = re.search(r"aborted due to error after ([\d\.]+) seconds", line, re.IGNORECASE)
        if match_abort:
            aborted_files += 1
            secs = float(match_abort.group(1))
            total_processing_time += secs
            if secs > max_processing_time:
                max_processing_time = secs

        if "consists only of empty pages and will be deleted" in line:
            empty_files += 1

        # Document routing & splitting counters
        if "Splitting batch PDF" in line:
            split_batches += 1
        if "saved successfully" in line and ("Partial PDF" in line or "partial PDF" in line):
            partial_docs_saved += 1
        if "Moving file" in line:
            direct_docs_moved += 1

        match_class = re.search(r"Page \d+ classification:\s*(.+)", line)
        if match_class:
            total_pages += 1
            cat = match_class.group(1).strip()
            if "\ufffd" in cat and valid_doc_types:
                for valid_type in valid_doc_types:
                    if len(valid_type) == len(cat) and all(
                        c1 == c2 for c1, c2 in zip(valid_type, cat, strict=False) if c2 != "\ufffd"
                    ):
                        cat = valid_type
                        break
            category_counts[cat] = category_counts.get(cat, 0) + 1

        # Tier 1 Invocations: Base Vision-LLM or Spatial OCR pass started
        if "Starting Vision-LLM Tier 1" in line:
            tier1_count += 1

        # Tier 1 Direct Consensus (Early Stop / Resolved without Tier 2)
        if (
            "validated with >= 2 measurements" in line
            or "Finalizing document" in line
            or "Early stop after Tier 1" in line
        ):
            tier1_direct_consensus += 1

        # Tier 2 Invocations: Escalation for pending / unconfident fields
        if "Starting Vision-LLM Tier 2 for pending fields" in line or "Starting Tier 2" in line:
            tier2_count += 1

        # Tier 3 Invocations: Tiebreaker escalation on conflict fields
        if (
            "Starting Vision-LLM Tier 3 Tiebreaker" in line
            or "Disagreement in field(s)" in line
            or "Starting Tier 3" in line
        ):
            tier3_count += 1

    total_files = completed_files + manual_review_files + aborted_files + empty_files
    total_archived_docs = partial_docs_saved + direct_docs_moved

    tier2_resolved = max(0, tier2_count - tier3_count)
    tier3_resolved = tier3_count

    success_rate = f"{((completed_files / total_files) * 100):.1f}" if total_files > 0 else "100.0"
    avg_time_file = f"{(total_processing_time / total_files):.1f}" if total_files > 0 else "0.0"
    avg_time_page = f"{(total_processing_time / total_pages):.1f}" if total_pages > 0 else "0.0"

    return {
        "recordsCount": len(lines),
        "totalFiles": total_files,
        "completedFiles": completed_files,
        "manualReviewFiles": manual_review_files,
        "abortedFiles": aborted_files,
        "emptyFiles": empty_files,
        "splitBatches": split_batches,
        "partialDocsSaved": partial_docs_saved,
        "directDocsMoved": direct_docs_moved,
        "totalArchivedDocs": total_archived_docs,
        "successRate": success_rate,
        "totalProcessingTime": f"{total_processing_time:.1f}",
        "maxProcessingTime": f"{max_processing_time:.1f}",
        "avgTimePerFile": avg_time_file,
        "avgTimePerPage": avg_time_page,
        "totalPages": total_pages,
        "categoryCounts": category_counts,
        "tier1Count": tier1_count,
        "tier1DirectConsensus": tier1_direct_consensus,
        "tier2Count": tier2_count,
        "tier2Resolved": tier2_resolved,
        "tier3Count": tier3_count,
        "tier3Resolved": tier3_resolved,
        "earlyStopCount": tier1_direct_consensus,
        "infoCount": info_count,
        "warnCount": warn_count,
        "errorCount": error_count,
    }
