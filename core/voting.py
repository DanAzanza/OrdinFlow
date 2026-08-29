"""
OrdinFlow — Voting and Consensus Clustering Module
Empirical multi-tier extraction consensus weighting and fuzzy vote clustering.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from difflib import SequenceMatcher
from typing import Any

from core.utils import MISSING_PLACEHOLDER, is_bool_value, is_missing_value, to_bool_value

# Empirical weighting for multi-tier extraction
# Dual-Source Tier 1 (weight 1.0) + Spatial Text (weight 1.0)
# Tier 2 (weight 1.25), Tier 3 (weight 1.5)
TIER_WEIGHTS: dict[str, float] = {
    "tier1": 1.0,
    "text": 1.0,
    "tier2": 1.25,
    "tier3": 1.5,
}
CONSENSUS_THRESHOLD = 0.67

# Fields excluded when collecting keys from extraction results
EXCLUDE_KEYS = {
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


def normalize_for_clustering(val: str) -> str:
    """Normalizes text for fuzzy voting."""
    if not isinstance(val, str):
        val = str(val)
    normed = val.casefold().translate(_UMLAUT_MAP)
    normed = "".join(c for c in unicodedata.normalize("NFD", normed) if unicodedata.category(c) != "Mn")
    normed = re.sub(r"\s+", " ", normed).strip()
    return normed


def fuzz_similarity(a: str, b: str) -> float:
    """Calculates similarity between two strings (0.0 to 1.0)."""
    return SequenceMatcher(None, normalize_for_clustering(a), normalize_for_clustering(b)).ratio()


def are_similar_or_substring(a: str, b: str, threshold: float = 0.80) -> bool:
    """Checks whether two strings are fuzzy similar OR if one is a token/substring subset of the other."""
    # Differing numbers/digits indicate distinct IDs, dates, or amounts and must not be clustered
    digits_a = re.findall(r"\d+", a)
    digits_b = re.findall(r"\d+", b)
    if digits_a and digits_b:
        if len(digits_a) == len(digits_b):
            try:
                if [int(d) for d in digits_a] != [int(d) for d in digits_b]:
                    return False
            except ValueError:
                if digits_a != digits_b:
                    return False
        elif digits_a != digits_b:
            return False

    if fuzz_similarity(a, b) >= threshold:
        return True

    norm_a = normalize_for_clustering(a)
    norm_b = normalize_for_clustering(b)
    if not norm_a or not norm_b or len(norm_a) < 3 or len(norm_b) < 3:
        return False

    # 1-character typo allowance for short names (e.g. Audre vs Andre)
    if (
        abs(len(norm_a) - len(norm_b)) <= 1
        and min(len(norm_a), len(norm_b)) >= 4
        and fuzz_similarity(norm_a, norm_b) >= 0.75
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


def casing_score(v: str) -> int:
    """Evaluates the typographical quality of a string representative."""
    s = v.strip()
    if not s:
        return 0
    # Heavy penalty for screaming all-caps (if longer than 3 chars)
    if s.isupper() and len(s) > 3:
        return -10
    # Moderate penalty for all-lowercase
    if s.islower():
        return -5
    # Reward natural mixed case (has both upper and lower letters, e.g. 'Mustermann', 'Dr. med.')
    has_upper = any(c.isupper() for c in s)
    has_lower = any(c.islower() for c in s)
    bonus = 10 if (has_upper and has_lower) else 0
    return bonus + sum(1 for c in s if c.isupper())


def pick_best_representative(members: list[tuple[str, float]]) -> str:
    """Selects the cleanest/most canonical spelling from cluster members.

    Priority order:
    1. Vote weight count (the most frequently extracted spelling wins)
    2. String length (longest name breaks ties between equal vote counts)
    3. Casing score (prefer natural mixed case over screaming ALL CAPS)
    """
    counts: dict[str, float] = {}
    for val, w in members:
        counts[val] = counts.get(val, 0.0) + w

    def score(v: str) -> tuple[float, int, int]:
        return (counts[v], len(v), casing_score(v))

    return max(counts.keys(), key=score)


def cluster_votes(
    votes: list[tuple[str, float]],
    threshold: float = 0.85,
) -> list[dict]:
    """Groups similarly-sounding or substring-related values into clusters and selects the best spelling."""
    clusters: list[dict] = []

    for val, weight in votes:
        matched_cluster = None
        for cluster in clusters:
            if are_similar_or_substring(val, cluster["representative"], threshold=threshold):
                matched_cluster = cluster
                break

        if matched_cluster:
            matched_cluster["members"].append((val, weight))
            matched_cluster["total_weight"] += weight
            matched_cluster["representative"] = pick_best_representative(matched_cluster["members"])
        else:
            clusters.append(
                {
                    "representative": pick_best_representative([(val, weight)]),
                    "members": [(val, weight)],
                    "total_weight": weight,
                }
            )

    return clusters


def evaluate_field_consensus(
    field: str,
    page_results_lists: list[list[dict]],
    tier_resolutions: Sequence[str],
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
            if is_bool_value(v):
                is_boolean_field = True
                bool_str = "True" if to_bool_value(v) else "False"
                weighted_votes.append((bool_str, weight))
            elif not is_missing_value(v):
                weighted_votes.append((str(v), weight))

    if not weighted_votes:
        return (False, 1.0, {}) if is_boolean_field else (MISSING_PLACEHOLDER, 0.0, {})

    clusters = cluster_votes(weighted_votes, threshold=0.80)
    if not clusters:
        return (False, 1.0, {}) if is_boolean_field else (MISSING_PLACEHOLDER, 0.0, {})

    top_cluster = max(clusters, key=lambda c: c["total_weight"])
    total_weight = sum(c["total_weight"] for c in clusters)
    confidence_k = top_cluster["total_weight"] / total_weight if total_weight > 0 else 0.0

    raw_winner = top_cluster["representative"]
    if is_boolean_field:
        winner_value = to_bool_value(raw_winner)
        counts_info = {to_bool_value(c["representative"]): round(c["total_weight"], 2) for c in clusters}
    else:
        winner_value = raw_winner
        counts_info = {c["representative"]: round(c["total_weight"], 2) for c in clusters}

    return winner_value, confidence_k, counts_info


def evaluate_round(
    field_names: set[str],
    results_lists: list[list[dict]],
    tier_names: Sequence[str],
    optional_fields: set[str],
    min_evidence_weight: float = 0.0,
) -> tuple[dict[str, Any], dict[str, float], dict[str, float], list[str]]:
    """Evaluates consensus round across specified tiers and field names."""
    field_results: dict[str, Any] = {}
    confidences: dict[str, float] = {}
    winning_weights: dict[str, float] = {}
    pending_or_conflicts: list[str] = []

    for field_name in field_names:
        is_optional_empty = field_name in optional_fields and all(
            is_missing_value(res.get(field_name))
            for res_list in results_lists
            for res in res_list
            if isinstance(res, dict)
        )
        if is_optional_empty:
            confidences[field_name] = 1.0
            winning_weights[field_name] = max(min_evidence_weight, 1.0)
            field_results[field_name] = MISSING_PLACEHOLDER
        else:
            winner, k_score, counts = evaluate_field_consensus(
                field_name,
                results_lists,
                tier_names,
            )
            w_weight = counts.get(winner, 0.0)
            confidences[field_name] = k_score
            winning_weights[field_name] = w_weight
            if k_score >= CONSENSUS_THRESHOLD and (min_evidence_weight <= 0.0 or w_weight >= min_evidence_weight):
                field_results[field_name] = winner
            else:
                pending_or_conflicts.append(field_name)

    return field_results, confidences, winning_weights, pending_or_conflicts
