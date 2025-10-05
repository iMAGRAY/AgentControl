"""Compatibility shim for relocated progress utilities."""
from __future__ import annotations

from agentcontrol.app.architecture.progress import (
    PHASE_ORDER,
    STATUS_WEIGHTS,
    compute_phase_progress,
    status_from_progress,
    status_score,
    utc_now_iso,
    weighted_numeric_average,
    weighted_status_average,
)

__all__ = [
    "PHASE_ORDER",
    "STATUS_WEIGHTS",
    "compute_phase_progress",
    "status_from_progress",
    "status_score",
    "utc_now_iso",
    "weighted_numeric_average",
    "weighted_status_average",
]
