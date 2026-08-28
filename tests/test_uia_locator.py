"""Unit tests for the UIALocator Provider."""

from __future__ import annotations

from unittest.mock import patch
from core.skills.uia_locator import UIALocator


def test_uia_locator_availability_and_fallback():
    # If not running on Windows or mock is supplied, locator should handle gracefully
    with patch("core.skills.uia_locator.UIALocator.is_available", return_value=False):
        assert UIALocator.find_element({"name": "Save"}) is None
        assert UIALocator.get_element_text({"name": "Save"}) == ""
        assert UIALocator.set_element_text({"name": "Edit"}, "test") is False
        assert UIALocator.click_element({"name": "Button"}) is False
        assert UIALocator.is_element_visible({"name": "Button"}) is False


def test_uia_locator_element_mocked_interaction():
    mock_element = {
        "hwnd": 12345,
        "name": "Patientenakte Müller",
        "class_name": "Edit",
        "id": 101,
        "rect": {"left": 100, "top": 100, "right": 200, "bottom": 130},
    }

    with (
        patch("core.skills.uia_locator.UIALocator.is_available", return_value=True),
        patch("core.skills.uia_locator.UIALocator.find_element", return_value=mock_element),
    ):
        assert UIALocator.is_element_visible({"automation_id": "101"}) is True
        text = UIALocator.get_element_text({"automation_id": "101"})
        assert text == "Patientenakte Müller"
