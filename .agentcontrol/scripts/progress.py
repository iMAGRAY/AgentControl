#!/usr/bin/env python3
"""Recalculate progress for program, epics, and big tasks."""
from __future__ import annotations

import argparse
import sys
import textwrap
from copy import deepcopy
from pathlib import Path
from typing import Dict, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))
PROJECT_ROOT = ROOT.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

import yaml

from scripts.lib.progress_utils import (
    compute_phase_progress,
    status_from_progress,
    status_score,
    utc_now_iso,
    weighted_numeric_average,
    weighted_status_average,
)
MANIFEST_PATH = ROOT / "architecture" / "manifest.yaml"
TODO_PATH = ROOT / "todo.machine.md"


def load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        raise SystemExit(f"File not found: {MANIFEST_PATH}")
    with MANIFEST_PATH.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_todo_sections() -> tuple[str, dict, list[dict], list[dict]]:
    if not TODO_PATH.exists():
        raise SystemExit(f"File not found: {TODO_PATH}")
    text = TODO_PATH.read_text(encoding="utf-8")

    def extract(section: str) -> tuple[dict | list[dict], tuple[int, int]]:
        marker = f"## {section}\n```yaml\n"
        start = text.find(marker)
        if start == -1:
            raise SystemExit(f"Section '{section}' not found in todo.machine.md")
        block_start = start + len(marker)
        end_marker = "\n```"
        block_end = text.find(end_marker, block_start)
        if block_end == -1:
            raise SystemExit(f"Section '{section}' is malformed")
        body = text[block_start:block_end]
        data = yaml.safe_load(body)
        return data, (start, block_end + len(end_marker))

    program, program_span = extract("Program")
    epics, epics_span = extract("Epics")
    big_tasks, big_span = extract("Big Tasks")

    return text, program, epics, big_tasks


def format_yaml(obj: object) -> str:
    return yaml.dump(obj, sort_keys=False, allow_unicode=True, width=1000).strip()


def replace_block(text: str, section: str, new_yaml: str) -> str:
    marker = f"## {section}\n```yaml\n"
    start = text.find(marker)
    if start == -1:
        raise SystemExit(f"Section '{section}' not found during replacement")
    block_start = start + len(marker)
    end_marker = "\n```"
    block_end = text.find(end_marker, block_start)
    if block_end == -1:
        raise SystemExit(f"Section '{section}' is malformed")
    return text[:block_start] + new_yaml + end_marker + text[block_end + len(end_marker):]


def calculate_progress(manifest: dict) -> Tuple[int, Dict[str, int], Dict[str, int], Dict[str, int]]:
    tasks = manifest.get("tasks", [])
    big_tasks = manifest.get("big_tasks", [])
    epics = manifest.get("epics", [])

    # Big task progress
    big_progress: Dict[str, int] = {}
    for big in big_tasks:
        related_tasks = [task for task in tasks if task.get("big_task") == big["id"]]
        if related_tasks:
            big_progress[big["id"]] = weighted_status_average(related_tasks, "status", "size_points")
        else:
            big_progress[big["id"]] = int(round(status_score(big.get("status", "planned")) * 100))

    # Epic progress
    epic_progress: Dict[str, int] = {}
    for epic in epics:
        related_big = [big for big in big_tasks if big.get("parent_epic") == epic["id"]]
        if related_big:
            epic_progress[epic["id"]] = weighted_numeric_average(
                (
                    {
                        "value": big_progress[big["id"]],
                        "size_points": big.get("size_points", 1),
                    }
                    for big in related_big
                ),
                "value",
                "size_points",
            )
        else:
            epic_progress[epic["id"]] = int(round(status_score(epic.get("status", "planned")) * 100))

    # Program progress
    if epics:
        program_progress = weighted_numeric_average(
            (
                {
                    "value": epic_progress[epic["id"]],
                    "size_points": epic.get("size_points", 1),
                }
                for epic in epics
            ),
            "value",
            "size_points",
        )
    else:
        program_progress = 0

    phase_progress = compute_phase_progress(tasks, manifest.get("program", {}).get("milestones", []), program_progress)
    return program_progress, epic_progress, big_progress, phase_progress


def update_manifest(manifest: dict, epic_progress: dict, big_progress: dict, program_progress: int, phase_progress: dict) -> bool:
    changed = False

    program = manifest.setdefault("program", {})
    progress_block = program.setdefault("progress", {})

    if progress_block.get("progress_pct") != program_progress:
        progress_block["progress_pct"] = program_progress
        changed = True
    if "health" not in progress_block:
        progress_block["health"] = "green"
        changed = True
    if progress_block.get("phase_progress") != phase_progress:
        progress_block["phase_progress"] = phase_progress
        changed = True

    for epic in manifest.get("epics", []):
        epic_id = epic["id"]
        metrics = epic.setdefault("metrics", {})
        new_value = epic_progress[epic_id]
        if metrics.get("progress_pct") != new_value:
            metrics["progress_pct"] = new_value
            changed = True
        new_status = status_from_progress(new_value)
        if epic.get("status") != new_status:
            epic["status"] = new_status
            changed = True

    for big in manifest.get("big_tasks", []):
        big_id = big["id"]
        metrics = big.setdefault("metrics", {})
        new_value = big_progress[big_id]
        if metrics.get("progress_pct") != new_value:
            metrics["progress_pct"] = new_value
            changed = True
        new_status = status_from_progress(new_value)
        if big.get("status") != new_status:
            big["status"] = new_status
            changed = True

    milestones = program.get("milestones", [])
    for milestone in milestones:
        title = milestone.get("title")
        phase_value = phase_progress.get(title, program_progress)
        new_status = status_from_progress(phase_value)
        if milestone.get("status") != new_status:
            milestone["status"] = new_status
            changed = True

    return changed


def persist_manifest(manifest: dict) -> None:
    with MANIFEST_PATH.open("w", encoding="utf-8") as fh:
        yaml.dump(manifest, fh, sort_keys=False, allow_unicode=True, width=1000)


def run(dry_run: bool = False) -> None:
    manifest = load_manifest()
    todo_text, program_block, epics_block, big_tasks_block = load_todo_sections()

    tasks = manifest.get("tasks", [])
    big_tasks = manifest.get("big_tasks", [])
    epics = manifest.get("epics", [])

    program_progress, epic_progress, big_progress, phase_progress = calculate_progress(manifest)
    milestones = manifest.get("program", {}).get("milestones", [])
    if milestones:
        title_map = {m.get("title"): m.get("title") for m in milestones if m.get("title")}
        phase_progress = {
            title: phase_progress.get(title, program_progress)
            for title in title_map
        }
    big_task_index = {big["id"]: big for big in big_tasks}
    epic_index = {epic["id"]: epic for epic in epics}

    # Update manifest
    manifest_changed = update_manifest(manifest, epic_progress, big_progress, program_progress, phase_progress)

    # Update todo.machine.md blocks
    if not isinstance(program_block, dict):
        raise SystemExit("Section Program must be a YAML mapping")
    program_block["progress_pct"] = program_progress
    program_block["phase_progress"] = phase_progress
    program_block["updated_at"] = manifest["program"]["meta"].get("updated_at", utc_now_iso())
    program_block["milestones"] = manifest["program"].get("milestones", [])

    if not isinstance(epics_block, list):
        raise SystemExit("Section Epics must be a YAML list")
    for epic in epics_block:
        epic_id = epic["id"]
        if epic_id not in epic_progress:
            raise SystemExit(f"Epic '{epic_id}' is missing from manifest.yaml")
        epic["progress_pct"] = epic_progress[epic_id]
        epic["status"] = epic_index.get(epic_id, {}).get("status", epic.get("status", "planned"))

    if not isinstance(big_tasks_block, list):
        raise SystemExit("Section Big Tasks must be a YAML list")
    for big in big_tasks_block:
        big_id = big["id"]
        if big_id not in big_progress:
            raise SystemExit(f"Big Task '{big_id}' is missing from manifest.yaml")
        big["progress_pct"] = big_progress[big_id]
        big["status"] = big_task_index.get(big_id, {}).get("status", big.get("status", "planned"))

    new_todo_text = todo_text
    new_todo_text = replace_block(new_todo_text, "Program", format_yaml(program_block))
    new_todo_text = replace_block(new_todo_text, "Epics", format_yaml(epics_block))
    new_todo_text = replace_block(new_todo_text, "Big Tasks", format_yaml(big_tasks_block))

    if dry_run:
        print("Program progress:", program_progress)
        for epic_id, value in epic_progress.items():
            print(f"Epic {epic_id}: {value}")
        for big_id, value in big_progress.items():
            print(f"Big Task {big_id}: {value}")
        return

    if new_todo_text != todo_text:
        TODO_PATH.write_text(new_todo_text, encoding="utf-8")
        print("Updated todo.machine.md")
    else:
        print("todo.machine.md already up to date")

    if manifest_changed:
        manifest["updated_at"] = utc_now_iso()
        program_meta = manifest.setdefault("program", {}).setdefault("meta", {})
        program_meta["updated_at"] = manifest["updated_at"]
        persist_manifest(manifest)
        print("Updated architecture/manifest.yaml")
    else:
        print("manifest.yaml unchanged")

    print(render_progress_tables(program_progress, epic_progress, big_progress, manifest))


def render_progress_tables(program_progress: int, epic_progress: Dict[str, int], big_progress: Dict[str, int], manifest: dict) -> str:
    lines: list[str] = []

    def render_table(title: str, headers: list[str], rows: list[list[str]]) -> str:
        widths = [len(header) for header in headers]
        for row in rows:
            for idx, cell in enumerate(row):
                widths[idx] = max(widths[idx], len(cell))

        def build_border(left: str, mid: str, right: str, fill: str) -> str:
            segments = [fill * (w + 2) for w in widths]
            return left + mid.join(segments) + right

        def build_row(cells: list[str]) -> str:
            parts = [f" {cell.ljust(widths[idx])} " for idx, cell in enumerate(cells)]
            return "|" + "|".join(parts) + "|"

        table_lines = [title, build_border("+", "+", "+", "-"), build_row(headers), build_border("+", "+", "+", "=")]
        for row in rows:
            table_lines.append(build_row(row))
        table_lines.append(build_border("+", "+", "+", "-"))
        return "\n".join(table_lines)

    program_rows = [[
        manifest["program"]["meta"].get("name", "Program"),
        manifest["program"].get("progress", {}).get("health", "n/a"),
        f"{program_progress}%",
        manifest["program"]["meta"].get("updated_at", "n/a"),
    ]]
    lines.append(render_table("Program", ["Name", "Health", "Progress", "Updated"], program_rows))

    epic_rows: list[list[str]] = []
    for epic in manifest.get("epics", []):
        epic_rows.append([
            epic["id"],
            epic.get("title", ""),
            epic.get("status", "n/a"),
            f"{epic_progress.get(epic['id'], 0)}%",
            str(epic.get("size_points", 0)),
        ])
    if epic_rows:
        lines.append(render_table("Epics", ["ID", "Title", "Status", "Progress", "Size"], epic_rows))

    big_rows: list[list[str]] = []
    for big in manifest.get("big_tasks", []):
        big_rows.append([
            big["id"],
            big.get("title", ""),
            big.get("status", "n/a"),
            f"{big_progress.get(big['id'], 0)}%",
            big.get("parent_epic", ""),
            str(big.get("size_points", 0)),
        ])
    if big_rows:
        lines.append(
            render_table(
                "Big Tasks",
                ["ID", "Title", "Status", "Progress", "Epic", "Size"],
                big_rows,
            )
        )

    return "\n\n".join(lines)


def collect_progress_state() -> dict:
    manifest = load_manifest()
    program_progress, epic_progress, big_progress, phase_progress = calculate_progress(manifest)
    program = manifest.get("program", {})
    meta = deepcopy(program.get("meta", {}))
    progress_block = program.get("progress", {})
    milestones = deepcopy(program.get("milestones", []))
    for milestone in milestones:
        title = milestone.get("title")
        milestone["progress_pct"] = phase_progress.get(title, program_progress)
        milestone["status"] = status_from_progress(milestone["progress_pct"])

    epics_data = []
    for epic in manifest.get("epics", []):
        pct = epic_progress.get(epic["id"], 0)
        epics_data.append(
            {
                "id": epic["id"],
                "title": epic.get("title", ""),
                "status": status_from_progress(pct),
                "progress_pct": pct,
                "size_points": epic.get("size_points", 0),
                "priority": epic.get("priority", ""),
            }
        )

    big_data = []
    for big in manifest.get("big_tasks", []):
        pct = big_progress.get(big["id"], 0)
        big_data.append(
            {
                "id": big["id"],
                "title": big.get("title", ""),
                "status": status_from_progress(pct),
                "progress_pct": pct,
                "size_points": big.get("size_points", 0),
                "parent_epic": big.get("parent_epic", ""),
                "priority": big.get("priority", ""),
            }
        )

    return {
        "generated_at": utc_now_iso(),
        "program": {
            "name": meta.get("name"),
            "progress_pct": program_progress,
            "health": progress_block.get("health", "green"),
            "updated_at": meta.get("updated_at"),
        },
        "phase_progress": phase_progress,
        "milestones": milestones,
        "epics": epics_data,
        "big_tasks": big_data,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Recalculate program and task progress")
    parser.add_argument("--dry-run", action="store_true", help="Display computed values only")
    args = parser.parse_args(argv)
    run(dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
