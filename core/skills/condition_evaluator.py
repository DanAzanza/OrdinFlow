"""Safe AST-based Condition Evaluator for OrdinFlow RPA Skills.

Evaluates declarative branching conditions without unsafe Python `eval()`.
Supports variable comparisons, window visibility checks, element existence,
regex matching, and boolean combinations with bounded recursion limits.
"""

from __future__ import annotations

import ast
import logging
import re
import sys
from collections.abc import Callable, Mapping
from typing import Any

logger = logging.getLogger(__name__)

# Constants for loop and recursion safety
MAX_BRANCH_DEPTH = 5
MAX_EVALUATION_STEPS = 300

# Supported AST comparison operators
SAFE_COMPARISON_OPERATORS: dict[type[ast.cmpop], Callable[[Any, Any], bool]] = {
    ast.Eq: lambda a, b: a == b,
    ast.NotEq: lambda a, b: a != b,
    ast.Lt: lambda a, b: a < b,
    ast.LtE: lambda a, b: a <= b,
    ast.Gt: lambda a, b: a > b,
    ast.GtE: lambda a, b: a >= b,
    ast.In: lambda a, b: a in b if b is not None else False,
    ast.NotIn: lambda a, b: a not in b if b is not None else True,
}


class ConditionEvaluationError(Exception):
    """Raised when an expression or condition cannot be safely evaluated."""


class SafeASTEvaluator(ast.NodeVisitor):
    """AST visitor that evaluates basic expressions safely without arbitrary code execution."""

    def __init__(self, context: Mapping[str, Any]):
        self.context = dict(context)

    def evaluate(self, expr_str: str) -> Any:
        """Parses and safely evaluates a single Python expression string."""
        clean_expr = str(expr_str).strip()
        if not clean_expr:
            return False

        try:
            tree = ast.parse(clean_expr, mode="eval")
            return self.visit(tree.body)
        except Exception as e:
            logger.debug("[SafeASTEvaluator] Error evaluating expression %r: %s", expr_str, e)
            raise ConditionEvaluationError(f"Invalid expression {expr_str!r}: {e}") from e

    def visit_Constant(self, node: ast.Constant) -> Any:
        return node.value

    def visit_Name(self, node: ast.Name) -> Any:
        var_name = node.id
        if var_name in self.context:
            return self.context[var_name]
        if var_name == "True":
            return True
        if var_name == "False":
            return False
        if var_name == "None":
            return None
        # Return empty string for unpopulated variables to preserve fail-safe evaluation
        return ""

    def visit_UnaryOp(self, node: ast.UnaryOp) -> Any:
        val = self.visit(node.operand)
        if isinstance(node.op, ast.Not):
            return not bool(val)
        if isinstance(node.op, ast.USub):
            return -val
        if isinstance(node.op, ast.UAdd):
            return +val
        raise ConditionEvaluationError(f"Unsupported unary operator: {type(node.op).__name__}")

    def visit_BoolOp(self, node: ast.BoolOp) -> bool:
        if isinstance(node.op, ast.And):
            for value_node in node.values:
                if not bool(self.visit(value_node)):
                    return False
            return True
        if isinstance(node.op, ast.Or):
            for value_node in node.values:
                if bool(self.visit(value_node)):
                    return True
            return False
        raise ConditionEvaluationError(f"Unsupported boolean operator: {type(node.op).__name__}")

    def visit_Compare(self, node: ast.Compare) -> bool:
        left = self.visit(node.left)
        for op, comparator in zip(node.ops, node.comparators, strict=False):
            op_type = type(op)
            if op_type not in SAFE_COMPARISON_OPERATORS:
                raise ConditionEvaluationError(f"Unsupported comparison operator: {op_type.__name__}")
            right = self.visit(comparator)
            op_fn = SAFE_COMPARISON_OPERATORS[op_type]

            # Safe numeric conversion if both operands look like numbers
            left_val, right_val = self._coerce_types_for_comparison(left, right)
            try:
                if not op_fn(left_val, right_val):
                    return False
            except TypeError:
                # String fallback comparison if type coercion fails
                if not op_fn(str(left_val), str(right_val)):
                    return False
            left = right
        return True

    def visit_Call(self, node: ast.Call) -> Any:
        # Support a limited whitelist of safe string methods
        if isinstance(node.func, ast.Attribute):
            caller_val = self.visit(node.func.value)
            method_name = node.func.attr
            args = [self.visit(arg) for arg in node.args]

            if method_name in ("startswith", "endswith"):
                if args and isinstance(caller_val, str):
                    return getattr(caller_val, method_name)(str(args[0]))
                return False
            if method_name in ("lower", "upper", "strip"):
                if isinstance(caller_val, str):
                    return getattr(caller_val, method_name)()
                return ""
            if method_name in ("contains", "includes"):
                if args and caller_val is not None:
                    return str(args[0]).lower() in str(caller_val).lower()
                return False

        raise ConditionEvaluationError(f"Arbitrary function calls are not permitted: {ast.dump(node)}")

    def generic_visit(self, node: ast.AST) -> Any:
        raise ConditionEvaluationError(f"Syntax element not allowed in safe conditions: {type(node).__name__}")

    @staticmethod
    def _coerce_types_for_comparison(left: Any, right: Any) -> tuple[Any, Any]:
        """Attempts safe numeric coercion for comparison operators."""
        if isinstance(left, int | float) and isinstance(right, int | float):
            return left, right
        if isinstance(left, str) and isinstance(right, int | float):
            try:
                return float(left) if "." in left else int(left), right
            except ValueError:
                pass
        elif isinstance(right, str) and isinstance(left, int | float):
            try:
                return left, float(right) if "." in right else int(right)
            except ValueError:
                pass
        return left, right


def evaluate_condition(
    condition: Mapping[str, Any] | str | bool | None,
    context: Mapping[str, Any],
    window_checker: Callable[[str], bool] | None = None,
    element_checker: Callable[[dict[str, Any], str], bool] | None = None,
) -> bool:
    """Evaluates a condition object or expression string against the active execution context.

    Supported condition specifications:
    1. Boolean literal: True / False
    2. String expression: "{category} == 'Fußscan' and {age} >= 18"
    3. Structured dict:
       - type: "WINDOW_EXISTS", target: "CorelDRAW*"
       - type: "ELEMENT_VISIBLE", locator: {...}, window: "CorelDRAW*"
       - type: "VARIABLE_MATCHES", variable: "category", expected: "Fußscan"
       - type: "REGEX_MATCH", variable: "document_name", pattern: "^Fußscan__\\d{2}\\.\\d{2}"
       - type: "EXPRESSION", expr: "{is_signed} == True"
    """
    if condition is None:
        return True

    if isinstance(condition, bool):
        return condition

    if isinstance(condition, str):
        # Substitute curly-brace placeholders from context before parsing
        expr_str = _substitute_placeholders_for_ast(condition, context)
        evaluator = SafeASTEvaluator(context)
        try:
            return bool(evaluator.evaluate(expr_str))
        except ConditionEvaluationError as e:
            logger.warning("[ConditionEvaluator] Failed to evaluate expression %r: %s", condition, e)
            return False

    if isinstance(condition, Mapping):
        cond_type = str(condition.get("type", "EXPRESSION")).upper()

        # 1. WINDOW_EXISTS
        if cond_type in ("WINDOW_EXISTS", "WINDOW_ACTIVE"):
            target_win = str(condition.get("target") or condition.get("window_title") or "")
            if not target_win:
                return False
            # Resolve placeholders in target title
            target_win = _substitute_placeholders_for_ast(target_win, context)
            if window_checker:
                return window_checker(target_win)
            return _default_window_exists(target_win)

        # 2. ELEMENT_VISIBLE / ELEMENT_EXISTS
        if cond_type in ("ELEMENT_VISIBLE", "ELEMENT_EXISTS"):
            locator = condition.get("locator")
            if not isinstance(locator, dict):
                return False
            target_win = str(condition.get("window_title") or condition.get("target") or "")
            target_win = _substitute_placeholders_for_ast(target_win, context)
            if element_checker:
                return element_checker(locator, target_win)
            return False

        # 3. VARIABLE_MATCHES / VARIABLE_EQUALS
        if cond_type in ("VARIABLE_MATCHES", "VARIABLE_EQUALS"):
            var_name = str(condition.get("variable") or condition.get("var") or "").strip().strip("{}")
            expected = condition.get("expected") or condition.get("value")
            actual = context.get(var_name, "")
            return str(actual).strip() == str(expected).strip()

        # 4. REGEX_MATCH
        if cond_type == "REGEX_MATCH":
            var_name = str(condition.get("variable") or condition.get("var") or "").strip().strip("{}")
            pattern = str(condition.get("pattern") or condition.get("regex") or "")
            actual = str(context.get(var_name, ""))
            if not pattern:
                return False
            try:
                return bool(re.search(pattern, actual))
            except re.error as e:
                logger.warning("[ConditionEvaluator] Invalid regex pattern %r: %s", pattern, e)
                return False

        # 5. IS_EMPTY / IS_NOT_EMPTY
        if cond_type in ("IS_EMPTY", "EMPTY"):
            var_name = str(condition.get("variable") or condition.get("var") or "").strip().strip("{}")
            actual = context.get(var_name)
            return actual is None or str(actual).strip() == ""

        if cond_type in ("IS_NOT_EMPTY", "NOT_EMPTY"):
            var_name = str(condition.get("variable") or condition.get("var") or "").strip().strip("{}")
            actual = context.get(var_name)
            return actual is not None and str(actual).strip() != ""

        # 6. EXPRESSION (Default dict wrapper)
        expr = str(condition.get("expr") or condition.get("expression") or "")
        if expr:
            expr_str = _substitute_placeholders_for_ast(expr, context)
            evaluator = SafeASTEvaluator(context)
            try:
                return bool(evaluator.evaluate(expr_str))
            except ConditionEvaluationError:
                return False

    return False


def _substitute_placeholders_for_ast(text: str, context: Mapping[str, Any]) -> str:
    """Safely substitutes `{var_name}` inside expression strings with literal representation."""
    if "{" not in text:
        return text

    # First handle placeholders already wrapped in single or double quotes
    def repl_quoted(match: re.Match) -> str:
        key = match.group(1)
        if key in context:
            val = context[key]
            if isinstance(val, str):
                escaped = val.replace("\\", "\\\\").replace("'", "\\'")
                return f"'{escaped}'"
            if isinstance(val, bool):
                return "True" if val else "False"
            if val is None:
                return "None"
            return str(val)
        return "''"

    processed = re.sub(r"['\"]\{([\w\-]+)\}['\"]", repl_quoted, text)

    # Next handle unquoted placeholders
    def repl_unquoted(match: re.Match) -> str:
        key = match.group(1)
        if key in context:
            val = context[key]
            if isinstance(val, str):
                escaped = val.replace("\\", "\\\\").replace("'", "\\'")
                return f"'{escaped}'"
            if isinstance(val, bool):
                return "True" if val else "False"
            if val is None:
                return "None"
            return str(val)
        return "''"

    return re.sub(r"\{([\w\-]+)\}", repl_unquoted, processed)


def _default_window_exists(pattern: str) -> bool:
    """Checks if a top-level window matching the pattern exists on Windows."""
    if sys.platform != "win32" or not pattern:
        return False
    from core.skills.window_manager import find_window_hwnd

    return find_window_hwnd(pattern, require_visible=True) is not None
