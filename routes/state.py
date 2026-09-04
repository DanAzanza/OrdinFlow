"""Backward-compatibility re-export of OrdinFlow runtime state.

The canonical state container now lives in `core.state` to ensure clean
unidirectional architecture boundaries (`routes` -> `core`).
"""

from __future__ import annotations

from core.state import DMSService, DashboardState, dms_service

__all__ = ["DMSService", "DashboardState", "dms_service"]
