"""Progress recalculation utilities for SDK."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Iterable, Mapping

STATUS_WEIGHTS: Mapping[str, float] = {
    "done": 1.0,
    "review": 0.8,
    "in_progress": 0.6,
    "at_risk": 0.4,
    "blocked": 0.3,
    "planned": 0.0,
    "backlog": 0.0,
}

PHASE_ORDER: tuple[str, ...] = (
    "Phase 0 – Feasibility",
    "Phase 1 – Foundation",
    "Phase 2 – Core Build",
    "Phase 3 – Beta",
    "Phase 4 – GA",
    "Phase 5 – Ops & Scaling",
    "Phase 6 – Optimization",
    "Phase 7 – Sustain & Innovate",
)


def status_score(status: str) -> float:
    try:
        return STATUS_WEIGHTS[status]
    except KeyError as exc:
        raise ValueError(f"Unknown status '{status}'") from exc


def _normalise_weight(weight: float | int | None) -> float:
    if weight is None:
        return 1.0
    try:
        numeric = float(weight)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Weight '{weight}' non-numeric") from exc
    if numeric <= 0:
        return 1.0
    return numeric


def weighted_status_average(items: Iterable[dict], status_key: str, weight_key: str | None = None) -> int:
    total_weight = 0.0
    accumulated = 0.0
    for item in items:
        status = item.get(status_key)
        if status is None:
            continue
        weight = _normalise_weight(item.get(weight_key)) if weight_key else 1.0
        total_weight += weight
        accumulated += status_score(status) * weight
    if total_weight == 0:
        return 0
    return int(round(accumulated / total_weight * 100))


def weighted_numeric_average(items: Iterable[dict], value_key: str, weight_key: str | None = None) -> int:
    total_weight = 0.0
    accumulated = 0.0
    for item in items:
        value = item.get(value_key)
        if value is None:
            continue
        weight = _normalise_weight(item.get(weight_key)) if weight_key else 1.0
        total_weight += weight
        accumulated += float(value) * weight
    if total_weight == 0:
        return 0
    return int(round(accumulated / total_weight))


def compute_phase_progress(tasks: list[dict], milestones: list[dict], default_value: int) -> Dict[str, int]:
    id_to_title = {m["id"]: m["title"] for m in milestones if "id" in m and "title" in m}
    title_to_id = {title: mid for mid, title in id_to_title.items()}
    phase_values: Dict[str, int] = {}

    for title in PHASE_ORDER:
        phase_id = title_to_id.get(title)
        if phase_id is None:
            phase_values[title] = default_value
            continue
        relevant = [task for task in tasks if task.get("roadmap_phase") == phase_id]
        phase_values[title] = weighted_status_average(relevant, "status", "size_points") if relevant else default_value

    extra_titles = [m["title"] for m in milestones if m["title"] not in PHASE_ORDER]
    for title in extra_titles:
        phase_id = title_to_id.get(title)
        relevant = [task for task in tasks if task.get("roadmap_phase") == phase_id]
        if relevant:
            phase_values[title] = weighted_status_average(relevant, "status", "size_points")
        elif title not in phase_values:
            phase_values[title] = default_value

    return phase_values


def status_from_progress(progress: int) -> str:
    if progress >= 100:
        return "done"
    if progress <= 0:
        return "planned"
    return "in_progress"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
