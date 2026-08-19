"""Unit tests for decoupled voting consensus in the extraction pipeline."""

from core.extraction_pipeline import _evaluate_field_consensus


def test_evaluate_field_consensus_pure_llm_weights():
    """Tests that voting consensus accurately aggregates multi-tier LLM weights without synthetic OCR boost."""
    winner, k_score, counts = _evaluate_field_consensus(
        "Nachname",
        [[{"Nachname": "Müller"}], [{"Nachname": "Müller"}]],
        ["tier1", "text"],
    )

    assert winner == "Müller"
    # Weight 1.0 (Tier 1 Vision) + 1.0 (Spatial Text) = 2.0
    assert counts.get("Müller") == 2.0
    assert k_score == 1.0


def test_evaluate_field_consensus_disagreement_weights():
    """Tests consensus when Vision Tier 1 and Spatial Text disagree."""
    winner, k_score, counts = _evaluate_field_consensus(
        "Nachname",
        [[{"Nachname": "Müller"}], [{"Nachname": "Meier"}]],
        ["tier1", "text"],
    )

    assert counts.get("Müller") == 1.0
    assert counts.get("Meier") == 1.0
    assert k_score == 0.50
