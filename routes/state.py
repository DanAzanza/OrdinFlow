"""Backward-compatibility re-export of OrdinFlow runtime state.

The canonical state container now lives in `core.state` to ensure clean
unidirectional architecture boundaries (`routes` -> `core`).
"""

from core.state import (
    DMSService,
    DashboardState,
    create_dms_service,
    dms_service,
    get_current_dms,
    set_current_dms,
)

__all__ = [
    "DMSService",
    "DashboardState",
    "create_dms_service",
    "dms_service",
    "get_current_dms",
    "set_current_dms",
]
