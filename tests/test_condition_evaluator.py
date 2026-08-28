"""Unit tests for the Safe AST Condition Evaluator."""

from __future__ import annotations

import pytest
from core.skills.condition_evaluator import (
    ConditionEvaluationError,
    SafeASTEvaluator,
    evaluate_condition,
)


def test_safe_ast_evaluator_basic_literals_and_names():
    evaluator = SafeASTEvaluator({"category": "Fußscan", "age": 25, "is_active": True})

    assert evaluator.evaluate("True") is True
    assert evaluator.evaluate("False") is False
    assert evaluator.evaluate("category == 'Fußscan'") is True
    assert evaluator.evaluate("category != 'Rezept'") is True
    assert evaluator.evaluate("age > 18") is True
    assert evaluator.evaluate("age <= 25") is True
    assert evaluator.evaluate("is_active == True") is True


def test_safe_ast_evaluator_boolean_combinations():
    evaluator = SafeASTEvaluator({"category": "Fußscan", "age": 30, "doc_type": "PDF"})

    assert evaluator.evaluate("category == 'Fußscan' and age >= 30") is True
    assert evaluator.evaluate("category == 'Rezept' or doc_type == 'PDF'") is True
    assert evaluator.evaluate("not (category == 'Rezept')") is True
    assert evaluator.evaluate("category == 'Fußscan' and (doc_type == 'DOCX' or age == 30)") is True


def test_safe_ast_evaluator_string_helpers():
    evaluator = SafeASTEvaluator({"filename": "Scan_Patient_2026.pdf", "prefix": "Scan_"})

    assert evaluator.evaluate("filename.startswith('Scan_')") is True
    assert evaluator.evaluate("filename.endswith('.pdf')") is True
    assert evaluator.evaluate("filename.contains('Patient')") is True
    assert evaluator.evaluate("filename.lower().startswith('scan_')") is True


def test_safe_ast_evaluator_blocks_rce_and_arbitrary_calls():
    evaluator = SafeASTEvaluator({"name": "Test"})

    # Attempting to call unauthorized functions must raise ConditionEvaluationError
    with pytest.raises(ConditionEvaluationError):
        evaluator.evaluate("__import__('os').system('calc')")

    with pytest.raises(ConditionEvaluationError):
        evaluator.evaluate("open('/etc/passwd').read()")

    with pytest.raises(ConditionEvaluationError):
        evaluator.evaluate("exec('import sys')")


def test_evaluate_condition_structured_dicts():
    context = {
        "category": "Fußscan",
        "document_name": "Fußscan__12.11.2025",
        "missing_var": "",
    }

    # 1. VARIABLE_MATCHES
    assert evaluate_condition({"type": "VARIABLE_MATCHES", "variable": "category", "expected": "Fußscan"}, context) is True
    assert evaluate_condition({"type": "VARIABLE_MATCHES", "variable": "category", "expected": "Rezept"}, context) is False

    # 2. REGEX_MATCH
    assert evaluate_condition({"type": "REGEX_MATCH", "variable": "document_name", "pattern": r"^Fußscan__\d{2}\.\d{2}"}, context) is True
    assert evaluate_condition({"type": "REGEX_MATCH", "variable": "document_name", "pattern": r"^Rezept__"}, context) is False

    # 3. IS_EMPTY / IS_NOT_EMPTY
    assert evaluate_condition({"type": "IS_EMPTY", "variable": "missing_var"}, context) is True
    assert evaluate_condition({"type": "IS_NOT_EMPTY", "variable": "category"}, context) is True

    # 4. WINDOW_EXISTS with custom checker
    assert evaluate_condition({"type": "WINDOW_EXISTS", "target": "CorelDRAW*"}, context, window_checker=lambda t: "Corel" in t) is True
    assert evaluate_condition({"type": "WINDOW_EXISTS", "target": "Photoshop*"}, context, window_checker=lambda t: "Corel" in t) is False

    # 5. String expression with placeholders
    assert evaluate_condition("'{category}' == 'Fußscan'", context) is True


def test_evaluate_condition_german_umlaute_and_dashes():
    context = {
        "Änderungsdatum": "2026-08-28",
        "Maßnahme": "Einlagenversorgung",
        "doc-type": "Fußscan",
    }
    assert evaluate_condition("'{Änderungsdatum}' == '2026-08-28'", context) is True
    assert evaluate_condition("'{Maßnahme}'.startswith('Einlagen')", context) is True
    assert evaluate_condition("'{doc-type}' == 'Fußscan'", context) is True

