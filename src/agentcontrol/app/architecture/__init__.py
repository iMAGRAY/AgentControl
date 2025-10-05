"""Architecture services package."""

from .generator import (
    DocSections,
    compute_hash,
    ensure_json_serialisable,
    generate_doc_sections,
    generate_doc_sections_for,
    generate_outputs,
    load_manifest_from_path,
)
from .progress import (
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
    "DocSections",
    "compute_hash",
    "ensure_json_serialisable",
    "generate_doc_sections",
    "generate_doc_sections_for",
    "generate_outputs",
    "load_manifest_from_path",
    "PHASE_ORDER",
    "STATUS_WEIGHTS",
    "compute_phase_progress",
    "status_from_progress",
    "status_score",
    "utc_now_iso",
    "weighted_numeric_average",
    "weighted_status_average",
]
