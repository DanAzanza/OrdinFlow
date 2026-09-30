"""Domain exceptions for OrdinFlow RPA Skills execution."""

from __future__ import annotations


class SkillActionError(Exception):
    """Raised when an RPA skill step or action fails fatally."""

    def __init__(self, step_id: str, message: str, action_type: str = ""):
        self.step_id = step_id
        self.message = message
        self.action_type = action_type
        type_prefix = f" ({action_type})" if action_type else ""
        super().__init__(f"Step '{step_id}'{type_prefix} failed: {message}")
