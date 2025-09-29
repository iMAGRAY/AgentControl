#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
LC_ALL=C.UTF-8

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib/common.sh"

MODE="${1:-full}"
case "$MODE" in
  full|compact|json)
    shift || true
    ;;
  *)
    MODE="full"
    ;;
esac

TODO_FILE="$SDK_ROOT/todo.machine.md"
if [[ ! -f "$TODO_FILE" ]]; then
  sdk::die "todo.machine.md не найден — дорожная карта недоступна"
fi

python3 - "$MODE" "$TODO_FILE" "$SDK_ROOT" <<'PY'
import json
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Dict, List

mode = sys.argv[1]
todo_path = Path(sys.argv[2])
sdk_root = Path(sys.argv[3])

STATUS_PROGRESS = {
    "done": 1.0,
    "review": 0.9,
    "ready": 0.75,
    "in_progress": 0.5,
    "backlog": 0.0,
    "blocked": 0.0,
}

text = todo_path.read_text(encoding="utf-8")


def extract_section(name: str) -> List[str]:
    pattern = rf"## {re.escape(name)}\n```yaml\n(.*?)\n```"
    blocks = re.findall(pattern, text, re.S)
    if not blocks:
        raise SystemExit(f"Раздел '{name}' отсутствует в todo.machine.md")
    return blocks


def parse_scalar(block: str, field: str, cast=str, default=None):
    pattern = rf"^\s*(?:-\s*)?{re.escape(field)}:\s*(.+)$"
    match = re.search(pattern, block, re.M)
    if not match:
        if default is not None:
            return default
        raise SystemExit(f"Поле '{field}' отсутствует в блоке:\n{block}")
    value = match.group(1).strip()
    if value.startswith('"') and value.endswith('"'):
        value = value[1:-1]
    if cast is int:
        return int(re.match(r"-?\d+", value).group(0))
    return value


def parse_phase_progress(block: str) -> Dict[str, int]:
    match = re.search(r"phase_progress:\n((?:\s{2,}.+\n)+)", block)
    if not match:
        raise SystemExit("Отсутствует блок phase_progress в Program")
    data = {}
    for line in match.group(1).splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        key, value = [part.strip() for part in stripped.split(":", 1)]
        data[key] = int(re.match(r"-?\d+", value).group(0))
    return data


def parse_milestones(block: str) -> List[dict]:
    items = []
    inline_matches = list(re.finditer(r"- \{ id: ([^,]+), title: \"([^\"]+)\", due: ([^,]+), status: ([^}]+) \}", block))
    if inline_matches:
        for m in inline_matches:
            items.append({
                "id": m.group(1),
                "title": m.group(2),
                "due": m.group(3),
                "status": m.group(4).strip(),
            })
        return items

    section_match = re.search(r"milestones:\n((?:\s*- .+\n(?:\s{1,}.+\n)*)+)", block)
    if not section_match:
        raise SystemExit("Не удалось разобрать milestones для Program")
    current = {}
    for raw_line in section_match.group(1).splitlines():
        line = raw_line.rstrip()
        if not line:
            continue
        if line.lstrip().startswith("-"):
            if current:
                items.append(current)
            current = {}
            content = line.lstrip()[1:].strip()
            if content and ":" in content:
                key, value = [part.strip() for part in content.split(":", 1)]
                current[key] = value.strip().strip('"').strip("'")
        else:
            if ":" in line:
                key, value = [part.strip() for part in line.split(":", 1)]
                current[key] = value.strip().strip('"').strip("'")
    if current:
        items.append(current)
    if not items:
        raise SystemExit("Не удалось разобрать milestones для Program")
    return items


def parse_epic(block: str) -> dict:
    return {
        "id": parse_scalar(block, "id"),
        "title": parse_scalar(block, "title"),
        "status": parse_scalar(block, "status"),
        "priority": parse_scalar(block, "priority"),
        "size_points": parse_scalar(block, "size_points", cast=int),
        "progress_pct": parse_scalar(block, "progress_pct", cast=int),
        "health": parse_scalar(block, "health"),
    }


def parse_big_task(block: str) -> dict:
    return {
        "id": parse_scalar(block, "id"),
        "title": parse_scalar(block, "title"),
        "status": parse_scalar(block, "status"),
        "priority": parse_scalar(block, "priority"),
        "size_points": parse_scalar(block, "size_points", cast=int),
        "parent_epic": parse_scalar(block, "parent_epic"),
        "progress_pct": parse_scalar(block, "progress_pct", cast=int),
        "health": parse_scalar(block, "health"),
    }


program_block = extract_section("Program")[0]
epic_blocks = extract_section("Epics")
big_task_blocks = extract_section("Big Tasks")

program = {
    "name": parse_scalar(program_block, "name"),
    "progress_pct": parse_scalar(program_block, "progress_pct", cast=int),
    "health": parse_scalar(program_block, "health"),
    "phase_progress": parse_phase_progress(program_block),
    "milestones": parse_milestones(program_block),
}

epics = [parse_epic(block) for block in epic_blocks]
big_tasks = [parse_big_task(block) for block in big_task_blocks]

warnings: List[str] = []

board_path = sdk_root / "data" / "tasks.board.json"
board_tasks = []
if board_path.exists():
    try:
        board = json.loads(board_path.read_text(encoding="utf-8"))
        board_tasks = board.get("tasks", [])
    except Exception as exc:
        warnings.append(f"Не удалось прочитать tasks.board.json: {exc}")
else:
    warnings.append("tasks.board.json отсутствует")

for task in board_tasks:
    task.setdefault("epic", "default")
    task.setdefault("status", "backlog")
    task.setdefault("size_points", 5)
    task.setdefault("big_task", None)

if not epics:
    raise SystemExit("Не заданы эпики для дорожной карты")
if not big_tasks:
    raise SystemExit("Не заданы Big Tasks для дорожной карты")

# Aggregation из task board
epic_totals = defaultdict(float)
epic_progress = defaultdict(float)
big_totals = defaultdict(float)
big_progress = defaultdict(float)
for task in board_tasks:
    try:
        size = float(task.get("size_points", 5) or 5)
    except Exception:
        size = 5.0
    ratio = STATUS_PROGRESS.get(task.get("status", "backlog"), 0.0)
    epic_totals[task["epic"]] += size
    epic_progress[task["epic"]] += size * ratio
    bt = task.get("big_task")
    if bt:
        big_totals[bt] += size
        big_progress[bt] += size * ratio

board_total = sum(epic_totals.values())
if board_total:
    program["computed_progress_pct"] = int(round(100 * sum(epic_progress.values()) / board_total))

for epic in epics:
    total = epic_totals.get(epic["id"])
    if total:
        derived = int(round(100 * epic_progress[epic["id"]] / total))
        epic["computed_progress_pct"] = derived
    else:
        warnings.append(f"Для эпика {epic['id']} нет задач на доске")

for bt in big_tasks:
    total = big_totals.get(bt["id"])
    if total:
        bt["computed_progress_pct"] = int(round(100 * big_progress[bt["id"]] / total))
    else:
        warnings.append(f"Для Big Task {bt['id']} нет связанных задач")

if program.get("computed_progress_pct") is not None and abs(program["computed_progress_pct"] - program["progress_pct"]) > 1:
    warnings.append(
        f"Program progress_pct {program['progress_pct']}% расходится с вычисленным {program['computed_progress_pct']}%"
    )

for epic in epics:
    derived = epic.get("computed_progress_pct")
    if derived is not None and abs(derived - epic["progress_pct"]) > 1:
        warnings.append(f"Epic {epic['id']} manual {epic['progress_pct']}% vs derived {derived}%")

phase_order = ["MVP", "Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7"]
phase_progress = program["phase_progress"]
if phase_progress:
    phase_avg = round(sum(phase_progress.values()) / len(phase_progress))
    if program.get("computed_progress_pct") is not None and abs(phase_avg - program["computed_progress_pct"]) > 5:
        warnings.append(
            f"Среднее phase_progress {phase_avg}% не согласовано с вычисленным прогрессом {program['computed_progress_pct']}%"
        )

effective_phase = int(round(program.get("computed_progress_pct", program["progress_pct"])))
phase_map = {phase: effective_phase for phase in phase_order}
program["phase_progress"] = {phase: effective_phase for phase in phase_order}

milestones = program["milestones"]
upcoming = [m for m in milestones if m.get("status") != "done"]
upcoming.sort(key=lambda m: m["due"])
next_milestone = upcoming[0] if upcoming else None

if mode == "json":
    output = {
        "generated_at": date.today().isoformat(),
        "program": program,
        "phase_progress": phase_map,
        "epics": epics,
        "big_tasks": big_tasks,
        "next_milestone": next_milestone,
        "warnings": warnings,
    }
    if program.get("computed_progress_pct") is not None:
        output["program"]["manual_progress_pct"] = program.get("progress_pct")
    print(json.dumps(output, ensure_ascii=False))
    sys.exit(0)

focus_epics = [e for e in epics if e.get("status") in {"in_progress", "review"}]

if mode == "compact":
    today = date.today().isoformat()
    effective_pct = program.get("computed_progress_pct", program["progress_pct"])
    print(f"Roadmap — {today} — {program['name']} — {effective_pct}% complete (health {program['health']})")
    if program.get("computed_progress_pct") is not None and program.get("computed_progress_pct") != program.get("progress_pct"):
        print(f"Manual progress: {program['progress_pct']}%")
    if warnings:
        print("Warnings:")
        for msg in warnings:
            print(f"- {msg}")
    phases_line = " | ".join(f"{phase}:{phase_map.get(phase, 0)}%" for phase in phase_order)
    focus_line = ", ".join(f"{e['id']}:{e.get('computed_progress_pct', e['progress_pct'])}%" for e in focus_epics) or "none"
    if next_milestone:
        next_line = f"Next milestone: {next_milestone['title']} due {next_milestone['due']} ({next_milestone['status']})"
    else:
        next_line = "Next milestone: n/a"
    print(f"Phases: {phases_line}")
    print(f"Focus epics: {focus_line}")
    print(next_line)
    sys.exit(0)

print(f"Roadmap Status — {date.today().isoformat()}")
print(f"Program: {program['name']} — {program['progress_pct']}% complete (health: {program['health']})")
if program.get("computed_progress_pct") is not None:
    print(f"Computed progress: {program['computed_progress_pct']}% (manual {program['progress_pct']}%)")
if warnings:
    print("Warnings:")
    for msg in warnings:
        print(f"- {msg}")
    print()
print("Phase Timeline:")
for phase in phase_order:
    pct = phase_map.get(phase, 0)
    milestone = next((m for m in milestones if m["title"] == phase), None)
    status = milestone["status"] if milestone else "not_planned"
    due = milestone["due"] if milestone else "n/a"
    print(f"- {phase}: {pct}% — status {status} — due {due}")
print()
print("Epics:")
for epic in epics:
    computed = epic.get("computed_progress_pct", epic["progress_pct"])
    extra = ""
    if computed != epic["progress_pct"]:
        extra = f" (derived {computed}% vs manual {epic['progress_pct']}%)"
    print(
        f"- {epic['id']} — {epic['title']} — {computed}% (status {epic['status']}, priority {epic['priority']}, size {epic['size_points']}){extra}"
    )
    for task in big_tasks:
        if task["parent_epic"] != epic["id"]:
            continue
        t_progress = task.get("computed_progress_pct", task["progress_pct"])
        delta = ""
        if task.get("computed_progress_pct") is not None and task.get("computed_progress_pct") != task["progress_pct"]:
            delta = f" (derived {task['computed_progress_pct']}% vs manual {task['progress_pct']}%)"
        print(
            f"    * {task['id']} — {task['title']} — {t_progress}% (status {task['status']}, size {task['size_points']}){delta}"
        )
PY
