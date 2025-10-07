#!/usr/bin/env python3
"""Compare docs benchmark results against historical runs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List


@dataclass(frozen=True)
class DiffEntry:
    operation: str
    previous: float | None
    current: float | None
    delta_ms: float | None
    delta_pct: float | None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "operation": self.operation,
            "previous_p95_ms": self.previous,
            "current_p95_ms": self.current,
            "delta_ms": self.delta_ms,
            "delta_pct": self.delta_pct,
        }


def load_report(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"report not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_history(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    entries: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def save_history(path: Path, entries: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(json.dumps(entry, ensure_ascii=False))
            handle.write("\n")


def _percent_delta(previous: float | None, current: float | None) -> float | None:
    if previous is None or current is None:
        return None
    if previous == 0:
        return None
    return ((current - previous) / previous) * 100.0


def build_diff(
    current: Dict[str, Any],
    previous: Dict[str, Any] | None,
    *,
    regression_pct: float,
    regression_ms: float,
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    current_ops: Dict[str, Dict[str, Any]] = current.get("operations", {}) or {}
    previous_ops: Dict[str, Dict[str, Any]] = previous.get("operations", {}) if previous else {}

    regressions: List[Dict[str, Any]] = []
    drift: List[Dict[str, Any]] = []
    improvements: List[Dict[str, Any]] = []
    stable: List[Dict[str, Any]] = []
    new_ops: List[Dict[str, Any]] = []
    removed_ops: List[Dict[str, Any]] = []

    seen_ops = set(current_ops.keys()) | set(previous_ops.keys())
    for name in sorted(seen_ops):
        curr = current_ops.get(name)
        prev = previous_ops.get(name)
        curr_p95 = (curr or {}).get("p95_ms") if curr else None
        prev_p95 = (prev or {}).get("p95_ms") if prev else None

        if curr is None:
            removed_ops.append({"operation": name, "previous_p95_ms": prev_p95})
            continue
        if prev is None:
            new_ops.append({"operation": name, "current_p95_ms": curr_p95})
            continue

        delta_ms = None
        if curr_p95 is not None and prev_p95 is not None:
            delta_ms = curr_p95 - prev_p95
        delta_pct = _percent_delta(prev_p95, curr_p95)
        entry = DiffEntry(name, prev_p95, curr_p95, delta_ms, delta_pct).to_dict()

        if delta_ms is None:
            stable.append(entry)
            continue
        if abs(delta_ms) < 1e-6:
            stable.append(entry)
            continue

        if delta_ms > 0:
            regression = False
            if delta_pct is None:
                regression = delta_ms >= regression_ms
            else:
                regression = delta_ms >= regression_ms and delta_pct >= regression_pct
            entry["regression"] = regression
            if regression:
                regressions.append(entry)
            else:
                drift.append(entry)
        else:
            improvements.append(entry)

    return {
        "generated_at": now,
        "current_report": current.get("generatedAt"),
        "previous_report": previous.get("generatedAt") if previous else None,
        "sections": {
            "current": current.get("sections"),
            "previous": previous.get("sections") if previous else None,
        },
        "regressions": regressions,
        "drift": drift,
        "improvements": improvements,
        "stable": stable,
        "new_operations": new_ops,
        "removed_operations": removed_ops,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare docs benchmark results with history")
    parser.add_argument("--report", type=Path, required=True, help="Current benchmark JSON report")
    parser.add_argument(
        "--history-dir",
        type=Path,
        default=Path("reports/perf/history"),
        help="Directory storing historical results",
    )
    parser.add_argument(
        "--history-file",
        type=str,
        default="docs_benchmark_history.jsonl",
        help="History file name relative to history directory",
    )
    parser.add_argument(
        "--diff",
        type=Path,
        default=None,
        help="Optional path to write diff JSON (defaults to history dir diff.json)",
    )
    parser.add_argument(
        "--max-regression-pct",
        type=float,
        default=10.0,
        help="Allowed percentage regression for p95",
    )
    parser.add_argument(
        "--max-regression-ms",
        type=float,
        default=2000.0,
        help="Allowed absolute regression in milliseconds",
    )
    parser.add_argument(
        "--update-history",
        action="store_true",
        help="Persist the current report into history after comparison",
    )
    parser.add_argument(
        "--keep",
        type=int,
        default=30,
        help="Maximum number of history entries to retain when updating",
    )
    args = parser.parse_args()

    report = load_report(args.report)
    history_path = args.history_dir / args.history_file
    entries = load_history(history_path)
    previous_entry = entries[-1] if entries else None
    previous_report = previous_entry.get("report") if previous_entry else None

    diff = build_diff(
        report,
        previous_report,
        regression_pct=args.max_regression_pct,
        regression_ms=args.max_regression_ms,
    )

    if args.diff is None:
        diff_path = args.history_dir / "diff.json"
    else:
        diff_path = args.diff
    diff_path.parent.mkdir(parents=True, exist_ok=True)
    diff_path.write_text(json.dumps(diff, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(diff, ensure_ascii=False, indent=2))

    project_root = Path.cwd()
    if diff["regressions"]:
        _append_timeline_event(project_root, "perf.regression", {
            "category": "quality",
            "regressions": diff["regressions"],
            "thresholds": {
                "max_regression_pct": args.max_regression_pct,
                "max_regression_ms": args.max_regression_ms,
            },
            "history": str(history_path),
        })
        _write_perf_followup(project_root, diff)
    else:
        _write_perf_followup(project_root, diff)

    if args.update_history:
        new_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "report": report,
        }
        entries.append(new_entry)
        if args.keep > 0:
            entries = entries[-args.keep :]
        save_history(history_path, entries)

    return 1 if diff["regressions"] else 0


def _append_timeline_event(project_root: Path, event: str, payload: Dict[str, Any]) -> None:
    journal_dir = project_root / "journal"
    journal_dir.mkdir(parents=True, exist_ok=True)
    journal_path = journal_dir / "task_events.jsonl"
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "payload": payload,
    }
    with journal_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False))
        handle.write("\n")


def _write_perf_followup(project_root: Path, diff: Dict[str, Any]) -> None:
    report_dir = project_root / "reports" / "automation"
    report_dir.mkdir(parents=True, exist_ok=True)
    followup_path = report_dir / "perf_followup.json"
    regressions = diff.get("regressions", [])
    status = "regression" if regressions else "resolved"
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "regressions": regressions,
        "new_operations": diff.get("new_operations", []),
        "removed_operations": diff.get("removed_operations", []),
        "recommended_action": "agentcall mission exec --issue perf_regression" if regressions else None,
    }
    followup_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    task_id = _sync_perf_followup_task(project_root, payload)
    if task_id:
        tasks_dir = project_root / "reports" / "tasks"
        tasks_dir.mkdir(parents=True, exist_ok=True)
        task_path = tasks_dir / f"{task_id}.json"
        task_payload = payload | {"id": task_id}
        task_path.write_text(json.dumps(task_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _state_directory_for(project_root: Path) -> Path:
    override = os.environ.get("AGENTCONTROL_STATE_DIR")
    if override:
        base = Path(override).expanduser()
        if any(part.startswith(".test_place") for part in base.parts):
            digest = hashlib.sha256(str(project_root.resolve()).encode("utf-8", "surrogatepass")).hexdigest()
            return base / digest
        return base
    return project_root / ".agentcontrol" / "state"


def _sync_perf_followup_task(project_root: Path, followup: Dict[str, Any]) -> str | None:
    state_dir = _state_directory_for(project_root)
    state_dir.mkdir(parents=True, exist_ok=True)
    tasks_path = state_dir / "perf_tasks.json"
    tasks: list[dict[str, Any]] = []
    if tasks_path.exists():
        try:
            existing = json.loads(tasks_path.read_text(encoding="utf-8"))
            if isinstance(existing, list):
                tasks = existing
        except json.JSONDecodeError:
            tasks = []

    now = datetime.now(timezone.utc).isoformat()
    has_open = any(task.get("status") == "open" for task in tasks)

    created_task_id: str | None = None

    if followup.get("status") == "regression":
        if not has_open:
            task_id = f"PERF-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"
            task = {
                "id": task_id,
                "status": "open",
                "created_at": now,
                "recommended_action": followup.get("recommended_action"),
            }
            tasks.append(task)
            _append_timeline_event(
                project_root,
                "task.followup.created",
                {"category": "perf", "task_id": task_id, "recommended_action": followup.get("recommended_action")},
            )
            created_task_id = task_id
    else:
        updated = False
        for task in tasks:
            if task.get("status") == "open":
                task["status"] = "resolved"
                task["resolved_at"] = now
                updated = True
        if updated:
            _append_timeline_event(project_root, "task.followup.resolved", {"category": "perf"})

    tasks_path.write_text(json.dumps(tasks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return created_task_id


if __name__ == "__main__":
    raise SystemExit(main())
