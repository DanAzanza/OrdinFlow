"""Backward-compatibility re-export of OrdinFlow runtime state.

The canonical state container now lives in `core.state` to ensure clean
unidirectional architecture boundaries (`routes` -> `core`).
"""

from flask import current_app, has_app_context

from core.state import (
    DMSService,
    DashboardState,
    create_dms_service,
    dms_service,
    get_current_dms,
    register_dms_context_resolver,
    set_current_dms,
)


def _resolve_flask_dms() -> DMSService | None:
    if has_app_context():
        ext_dms = current_app.extensions.get("dms")
        if ext_dms is not None and isinstance(ext_dms, DMSService):
            return ext_dms
    return None


register_dms_context_resolver(_resolve_flask_dms)

__all__ = [
    "DMSService",
    "DashboardState",
    "create_dms_service",
    "dms_service",
    "get_current_dms",
    "register_dms_context_resolver",
    "set_current_dms",
]
