"""Unit tests for the Safe AST Condition Evaluator in OrdinFlow RPA skills."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from core.skills.condition_evaluator import (
    ConditionEvaluationError,
    SafeASTEvaluator,
    evaluate_condition,
)


def test_eval_numeric_and_string_comparisons():
    """Tests basic comparisons (>, <, ==, !=, >=, <=) and numeric type coercion."""
    ctx = {"count": 15, "str_count": "15", "threshold": 10, "label": "Invoice"}

    # Numeric comparisons
    assert evaluate_condition("{count} > 10", ctx) is True
    assert evaluate_condition("{count} < 5", ctx) is False
    assert evaluate_condition("{count} >= 15", ctx) is True
    assert evaluate_condition("{count} <= 15", ctx) is True
    assert evaluate_condition("{count} == 15", ctx) is True
    assert evaluate_condition("{count} != 10", ctx) is True

    # Coercion: string in context compared with numeric literal
    assert evaluate_condition("{str_count} > 10", ctx) is True
    assert evaluate_condition("{str_count} == 15", ctx) is True

    # String comparisons
    assert evaluate_condition("{label} == 'Invoice'", ctx) is True
    assert evaluate_condition("{label} != 'DeliveryNote'", ctx) is True
    assert evaluate_condition("'Inv' in {label}", ctx) is True
    assert evaluate_condition("'Receipt' not in {label}", ctx) is True


def test_eval_whitelisted_string_methods():
    """Tests permitted AST string methods: startswith, endswith, lower, upper, strip, contains, includes."""
    ctx = {"filename": "  Invoice_2026.PDF  ", "doc_type": "MedicalReport"}

    # startswith / endswith
    assert evaluate_condition("{doc_type}.startswith('Medical')", ctx) is True
    assert evaluate_condition("{doc_type}.endswith('Report')", ctx) is True
    assert evaluate_condition("{doc_type}.startswith('Invoice')", ctx) is False

    # strip / lower / upper
    assert evaluate_condition("{filename}.strip().lower() == 'invoice_2026.pdf'", ctx) is True
    assert evaluate_condition("{doc_type}.upper() == 'MEDICALREPORT'", ctx) is True

    # contains / includes (case-insensitive AST helper)
    assert evaluate_condition("{filename}.contains('2026')", ctx) is True
    assert evaluate_condition("{filename}.includes('pdf')", ctx) is True
    assert evaluate_condition("{filename}.contains('scan')", ctx) is False


def test_eval_disallowed_syntax_and_injection():
    """Verifies that arbitrary code execution, imports, and comprehensions are strictly blocked."""
    ctx = {"cmd": "calc.exe"}

    # Function call not on whitelist
    assert evaluate_condition("__import__('os').system('calc')", ctx) is False

    # Builtins and comprehensions
    assert evaluate_condition("[x for x in (1, 2)] == [1, 2]", ctx) is False
    assert evaluate_condition("len({cmd}) > 0", ctx) is False

    # SafeASTEvaluator direct invocation raises ConditionEvaluationError
    evaluator = SafeASTEvaluator(ctx)
    with pytest.raises(ConditionEvaluationError):
        evaluator.evaluate("__import__('sys')")

    with pytest.raises(ConditionEvaluationError):
        evaluator.evaluate("(lambda: True)()")


def test_eval_boolean_ast_expressions():
    """Tests compound logical expressions (and, or, not) and unary operators."""
    ctx = {"is_verified": True, "amount": 250, "category": "Sanivision", "negative": -5}

    assert evaluate_condition("{is_verified} and {amount} > 200", ctx) is True
    assert evaluate_condition("{is_verified} and {amount} > 500", ctx) is False
    assert evaluate_condition("{amount} > 500 or {category} == 'Sanivision'", ctx) is True
    assert evaluate_condition("not ({amount} < 100)", ctx) is True
    assert evaluate_condition("{negative} == -5", ctx) is True

    # Missing context variables fail safely (resolve to empty string)
    assert evaluate_condition("{missing_key} == ''", ctx) is True
    assert evaluate_condition("{missing_key} and {amount} > 0", ctx) is False


def test_eval_structured_dict_conditions():
    """Tests structured dict condition specifications (VARIABLE_MATCHES, IS_EMPTY, IS_NOT_EMPTY, EXPRESSION)."""
    ctx = {"status": "completed", "empty_val": "", "present_val": "data", "none_val": None}

    # 1. VARIABLE_MATCHES
    cond_match = {"type": "VARIABLE_MATCHES", "variable": "status", "expected": "completed"}
    assert evaluate_condition(cond_match, ctx) is True

    cond_mismatch = {"type": "VARIABLE_MATCHES", "variable": "status", "expected": "pending"}
    assert evaluate_condition(cond_mismatch, ctx) is False

    # 2. IS_EMPTY / IS_NOT_EMPTY
    assert evaluate_condition({"type": "IS_EMPTY", "variable": "empty_val"}, ctx) is True
    assert evaluate_condition({"type": "IS_EMPTY", "variable": "none_val"}, ctx) is True
    assert evaluate_condition({"type": "IS_EMPTY", "variable": "missing"}, ctx) is True
    assert evaluate_condition({"type": "IS_EMPTY", "variable": "present_val"}, ctx) is False

    assert evaluate_condition({"type": "IS_NOT_EMPTY", "variable": "present_val"}, ctx) is True
    assert evaluate_condition({"type": "IS_NOT_EMPTY", "variable": "empty_val"}, ctx) is False
    assert evaluate_condition({"type": "IS_NOT_EMPTY", "variable": "none_val"}, ctx) is False

    # 3. EXPRESSION in dict
    cond_expr = {"type": "EXPRESSION", "expr": "{status} == 'completed'"}
    assert evaluate_condition(cond_expr, ctx) is True


def test_eval_regex_conditions():
    """Tests REGEX_MATCH with length ceiling, ReDoS nested quantifier rejection, and error safety."""
    ctx = {"filename": "Scan_2026-10-02_Mustermann.pdf"}

    # 1. Valid regex match
    cond_valid = {
        "type": "REGEX_MATCH",
        "variable": "filename",
        "pattern": r"^Scan_\d{4}-\d{2}-\d{2}",
    }
    assert evaluate_condition(cond_valid, ctx) is True

    cond_no_match = {
        "type": "REGEX_MATCH",
        "variable": "filename",
        "pattern": r"^Invoice_\d{4}",
    }
    assert evaluate_condition(cond_no_match, ctx) is False

    # 2. Pattern length limit (> 150 chars rejected)
    long_pattern = "a" * 151
    assert evaluate_condition({"type": "REGEX_MATCH", "variable": "filename", "pattern": long_pattern}, ctx) is False

    # 3. Nested quantifier ReDoS prevention: e.g. (a+)+ or (.*)*
    redos_pattern = r"(a+)+"
    assert evaluate_condition({"type": "REGEX_MATCH", "variable": "filename", "pattern": redos_pattern}, ctx) is False

    # 4. Malformed syntax safely caught
    malformed_pattern = r"[a-z("
    assert (
        evaluate_condition({"type": "REGEX_MATCH", "variable": "filename", "pattern": malformed_pattern}, ctx) is False
    )


def test_eval_window_and_element_conditions():
    """Tests WINDOW_EXISTS and ELEMENT_VISIBLE with mock checker callbacks."""
    ctx = {"app_title": "CorelDRAW"}

    def mock_window_checker(title: str) -> bool:
        return "CorelDRAW" in title

    def mock_element_checker(locator: dict, title: str) -> bool:
        return locator.get("automation_id") == "btn_ok" and "CorelDRAW" in title

    # WINDOW_EXISTS
    cond_win = {"type": "WINDOW_EXISTS", "target": "{app_title}*"}
    assert evaluate_condition(cond_win, ctx, window_checker=mock_window_checker) is True

    cond_win_fail = {"type": "WINDOW_EXISTS", "target": "Photoshop*"}
    assert evaluate_condition(cond_win_fail, ctx, window_checker=mock_window_checker) is False

    # ELEMENT_VISIBLE
    cond_elem = {
        "type": "ELEMENT_VISIBLE",
        "locator": {"automation_id": "btn_ok"},
        "target": "{app_title}*",
    }
    assert evaluate_condition(cond_elem, ctx, element_checker=mock_element_checker) is True

    cond_elem_fail = {
        "type": "ELEMENT_VISIBLE",
        "locator": {"automation_id": "btn_cancel"},
        "target": "{app_title}*",
    }
    assert evaluate_condition(cond_elem_fail, ctx, element_checker=mock_element_checker) is False


def test_eval_edge_cases_and_fallbacks(monkeypatch):
    """Verifies edge cases: None, bool literals, empty targets, invalid locators, and default window checker."""
    # 1. None and boolean literals
    assert evaluate_condition(None, {}) is True
    assert evaluate_condition(True, {}) is True
    assert evaluate_condition(False, {}) is False

    # 2. Empty string expression
    assert evaluate_condition("", {}) is False

    # 3. WINDOW_EXISTS with empty target
    assert evaluate_condition({"type": "WINDOW_EXISTS", "target": ""}, {}) is False

    # 4. ELEMENT_VISIBLE with invalid locator or missing checker
    assert evaluate_condition({"type": "ELEMENT_VISIBLE", "locator": "not a dict"}, {}) is False
    assert evaluate_condition({"type": "ELEMENT_VISIBLE", "locator": {"id": "x"}}, {}, element_checker=None) is False

    # 5. REGEX_MATCH with empty pattern or disallowed chars
    assert evaluate_condition({"type": "REGEX_MATCH", "pattern": ""}, {}) is False
    assert evaluate_condition({"type": "REGEX_MATCH", "pattern": "abc\x00def"}, {}) is False

    # 6. Unary + operator in AST
    assert evaluate_condition("+5 == 5", {}) is True

    # 7. Default window exists fallback with mocked find_window_hwnd
    mock_find_hwnd = MagicMock(return_value=12345)
    monkeypatch.setattr("core.skills.window_manager.find_window_hwnd", mock_find_hwnd)
    monkeypatch.setattr("core.skills.condition_evaluator.sys.platform", "win32")
    assert evaluate_condition({"type": "WINDOW_EXISTS", "target": "ActiveApp*"}, {}) is True


def test_evaluate_condition_german_umlaute_and_dashes():
    """Verifies that German umlauts and hyphenated variable names resolve properly."""
    context = {
        "Änderungsdatum": "2026-08-28",
        "Maßnahme": "Einlagenversorgung",
        "doc-type": "Fußscan",
    }
    assert evaluate_condition("'{Änderungsdatum}' == '2026-08-28'", context) is True
    assert evaluate_condition("'{Maßnahme}'.startswith('Einlagen')", context) is True
    assert evaluate_condition("'{doc-type}' == 'Fußscan'", context) is True


def test_regex_match_times_out_on_catastrophic_backtracking():
    """Verifies timeout protection on regex patterns with backtracking."""
    context = {"text": "a" * 300 + "!"}
    condition = {"type": "REGEX_MATCH", "variable": "text", "pattern": r"^(a|aa)+$"}
    assert evaluate_condition(condition, context) is False


