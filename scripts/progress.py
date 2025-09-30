#!/usr/bin/env python3
"""Пересчёт прогресса программы/эпиков/Big Tasks."""
from __future__ import annotations

import argparse
import sys
import textwrap
from pathlib import Path
from typing import Dict

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

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
        raise SystemExit(f"Файл не найден: {MANIFEST_PATH}")
    with MANIFEST_PATH.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_todo_sections() -> tuple[str, dict, list[dict], list[dict]]:
    if not TODO_PATH.exists():
        raise SystemExit(f"Файл не найден: {TODO_PATH}")
    text = TODO_PATH.read_text(encoding="utf-8")

    def extract(section: str) -> tuple[dict | list[dict], tuple[int, int]]:
        marker = f"## {section}\n```yaml\n"
        start = text.find(marker)
        if start == -1:
            raise SystemExit(f"Секция '{section}' не найдена в todo.machine.md")
        block_start = start + len(marker)
        end_marker = "\n```"
        block_end = text.find(end_marker, block_start)
        if block_end == -1:
            raise SystemExit(f"Секция '{section}' оформлена некорректно")
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
        raise SystemExit(f"Секция '{section}' не найдена при перезаписи")
    block_start = start + len(marker)
    end_marker = "\n```"
    block_end = text.find(end_marker, block_start)
    if block_end == -1:
        raise SystemExit(f"Секция '{section}' оформлена некорректно")
    return text[:block_start] + new_yaml + end_marker + text[block_end + len(end_marker):]


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

    big_task_index = {big["id"]: big for big in big_tasks}
    epic_index = {epic["id"]: epic for epic in epics}

    # Big task progress
    big_progress: Dict[str, int] = {}
    for big in big_tasks:
        related_tasks = [task for task in tasks if task.get("big_task") == big["id"]]
        if related_tasks:
            big_progress[big["id"]] = weighted_status_average(related_tasks, "status", "size_points")
        else:
            big_progress[big["id"]] = int(round(status_score(big["status"]) * 100))

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
            epic_progress[epic["id"]] = int(round(status_score(epic["status"]) * 100))

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

    # Update manifest
    manifest_changed = update_manifest(manifest, epic_progress, big_progress, program_progress, phase_progress)

    # Update todo.machine.md blocks
    if not isinstance(program_block, dict):
        raise SystemExit("Секция Program должна быть YAML-объектом")
    program_block["progress_pct"] = program_progress
    program_block["phase_progress"] = phase_progress
    program_block["updated_at"] = manifest["program"]["meta"].get("updated_at", utc_now_iso())
    program_block["milestones"] = manifest["program"].get("milestones", [])

    if not isinstance(epics_block, list):
        raise SystemExit("Секция Epics должна быть YAML-списком")
    for epic in epics_block:
        epic_id = epic["id"]
        if epic_id not in epic_progress:
            raise SystemExit(f"Эпик '{epic_id}' отсутствует в manifest.yaml")
        epic["progress_pct"] = epic_progress[epic_id]
        epic["status"] = epic_index.get(epic_id, {}).get("status", epic.get("status", "planned"))

    if not isinstance(big_tasks_block, list):
        raise SystemExit("Секция Big Tasks должна быть YAML-списком")
    for big in big_tasks_block:
        big_id = big["id"]
        if big_id not in big_progress:
            raise SystemExit(f"Big Task '{big_id}' отсутствует в manifest.yaml")
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
        print("Обновлён todo.machine.md")
    else:
        print("todo.machine.md уже актуален")

    if manifest_changed:
        manifest["updated_at"] = utc_now_iso()
        program_meta = manifest.setdefault("program", {}).setdefault("meta", {})
        program_meta["updated_at"] = manifest["updated_at"]
        persist_manifest(manifest)
        print("Обновлён architecture/manifest.yaml")
    else:
        print("manifest.yaml без изменений")

    print(textwrap.dedent(
        f"""
        Итоговый прогресс:
          Программа: {program_progress}%
          Эпики: {', '.join(f'{epic_id}={value}%' for epic_id, value in epic_progress.items())}
          Big Tasks: {', '.join(f'{big_id}={value}%' for big_id, value in big_progress.items())}
        """
    ).strip())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Пересчитать прогресс программы и задач")
    parser.add_argument("--dry-run", action="store_true", help="Только показать вычисленные значения")
    args = parser.parse_args(argv)
    run(dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
