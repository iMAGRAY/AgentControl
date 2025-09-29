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

python3 - "$MODE" "$TODO_FILE" <<'PY'
import sys
import re
import json
import os
from datetime import date
from pathlib import Path

STATUS_PROGRESS = {
    "done": 1.0,
    "review": 0.9,
    "ready": 0.75,
    "in_progress": 0.5,
    "backlog": 0.0,
    "blocked": 0.0,
}
mode = sys.argv[1]
path = Path(sys.argv[2])
text = path.read_text(encoding='utf-8')


def extract_section(name: str) -> list[str]:
    pattern = rf"## {re.escape(name)}\n(.*?)(?=\n## |\Z)"
    match = re.search(pattern, text, re.S)
    if not match:
        raise SystemExit(f"Раздел '{name}' отсутствует в todo.machine.md")
    section = match.group(1)
    blocks = re.findall(r"```yaml\n(.*?)\n```", section, re.S)
    if not blocks:
        raise SystemExit(f"В разделе '{name}' нет YAML-блоков")
    return blocks


def parse_scalar(block: str, field: str, default=None, cast=str):
    pattern = rf"^{re.escape(field)}:\s*(.+)$"
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


def parse_phase_progress(block: str) -> dict[str, int]:
    match = re.search(r"phase_progress:\n((?:\s{2,}.+\n)+)", block)
    if not match:
        raise SystemExit("Отсутствует блок phase_progress в Program")
    lines = match.group(1).splitlines()
    data = {}
    for raw in lines:
        stripped = raw.strip()
        if not stripped:
            continue
        key, value = [part.strip() for part in stripped.split(':', 1)]
        data[key] = int(re.match(r"-?\d+", value).group(0))
    return data


def parse_milestones(block: str) -> list[dict[str, str]]:
    items = []
    for m in re.finditer(r"- \{ id: ([^,]+), title: \"([^\"]+)\", due: ([^,]+), status: ([^}]+) \}", block):
        items.append(
            {
                "id": m.group(1),
                "title": m.group(2),
                "due": m.group(3),
                "status": m.group(4).strip(),
            }
        )
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

warnings: list[str] = []

epics = [parse_epic(block) for block in epic_blocks]
big_tasks = [parse_big_task(block) for block in big_task_blocks]

SDK_ROOT = Path(os.environ.get("SDK_ROOT", str(path.parent)))
board_path = SDK_ROOT / "data" / "tasks.board.json"
if board_path.exists():
    try:
        board = json.loads(board_path.read_text(encoding="utf-8"))
        board_tasks = board.get("tasks", [])
    except Exception:
        board_tasks = []
else:
    board_tasks = []

for task in board_tasks:
    task.setdefault("epic", "default")
    task.setdefault("status", "backlog")
    task.setdefault("size_points", 5)

if not epics:
    raise SystemExit("Не заданы эпики для дорожной карты")
if not big_tasks:
    raise SystemExit("Не заданы Big Tasks для дорожной карты")

# Consistency checks
epic_points = sum(epic["size_points"] for epic in epics)
weighted_program = round(
    sum(epic["size_points"] * epic["progress_pct"] for epic in epics) / epic_points
    if epic_points
    else 0
)
if abs(weighted_program - program["progress_pct"]) > 1:
    raise SystemExit(
        "Несогласованный прогресс: program progress_pct не совпадает с взвешенным по эпику"
    )

for epic in epics:
    tasks = [task for task in big_tasks if task["parent_epic"] == epic["id"]]
    if not tasks:
        warnings.append(f"Для эпика {epic['id']} не найдены Big Tasks")
        continue
    points = sum(task["size_points"] for task in tasks)
    weighted = round(
        sum(task["size_points"] * task["progress_pct"] for task in tasks) / points if points else 0
    )
    if abs(weighted - epic["progress_pct"]) > 1:
        warnings.append(f"Несогласованный прогресс: epic {epic['id']} (manual {epic['progress_pct']}%, derived {weighted}%)")

phase_values = program["phase_progress"]
phase_avg = round(sum(phase_values.values()) / len(phase_values))
if abs(phase_avg - program["progress_pct"]) > 1:
    warnings.append(f"Среднее phase_progress ({phase_avg}%) расходится с program progress_pct ({program['progress_pct']}%)")

phase_order = ["MVP", "Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7"]
phase_map = {**{phase: 0 for phase in phase_order}, **phase_values}

milestone_by_title = {m["title"]: m for m in program["milestones"]}

# Расчёт прогресса на основе task board
epic_totals_board: dict[str, float] = {}
epic_progress_board: dict[str, float] = {}
for task in board_tasks:
    epic_id = task.get("epic") or "default"
    try:
        size = float(task.get("size_points", 5) or 5)
    except Exception:
        size = 5.0
    ratio = STATUS_PROGRESS.get(task.get("status", "backlog"), 0.0)
    epic_totals_board[epic_id] = epic_totals_board.get(epic_id, 0.0) + size
    epic_progress_board[epic_id] = epic_progress_board.get(epic_id, 0.0) + size * ratio

board_total_points = sum(epic_totals_board.values())
computed_program_pct = round(100 * sum(epic_progress_board.values()) / board_total_points) if board_total_points else None
if computed_program_pct is not None:
    program["computed_progress_pct"] = int(computed_program_pct)
for epic in epics:
    total = epic_totals_board.get(epic["id"])
    if total:
        epic_progress = epic_progress_board.get(epic["id"], 0.0)
        epic["computed_progress_pct"] = int(round(100 * epic_progress / total))

active_epics = [e for e in epics if e["status"] in {"in_progress", "review"}]
upcoming = [m for m in program["milestones"] if m["status"] != "done"]
upcoming.sort(key=lambda m: m["due"])
next_milestone = upcoming[0] if upcoming else None

if mode == "json":
    output = {
        "generated_at": date.today().isoformat(),
        "program": program,
        "phase_progress": phase_map,
        "active_epics": [{"id": e["id"], "title": e["title"], "progress_pct": e.get("progress_pct"), "computed_progress_pct": e.get("computed_progress_pct"), "status": e["status"], "priority": e["priority"]} for e in active_epics],
        "next_milestone": next_milestone,
        "warnings": warnings,
    }
    if program.get("computed_progress_pct") is not None:
        output["program"]["manual_progress_pct"] = program.get("progress_pct")
    print(json.dumps(output, ensure_ascii=False))
    sys.exit(0)

if mode == "compact":
    today = date.today().isoformat()
    phases = " | ".join(f"{phase}:{phase_map.get(phase, 0)}%" for phase in phase_order)
    focus = ", ".join(f"{item['id']}:{item['progress_pct']}%" for item in active_epics) or "none"
    next_line = (
        f"Next milestone: {next_milestone['title']} due {next_milestone['due']} ({next_milestone['status']})"
        if next_milestone
        else "Next milestone: n/a"
    )
    effective_pct = program.get('computed_progress_pct', program['progress_pct'])
    print(
        f"Roadmap — {today} — {program['name']} — {effective_pct}% complete (health {program['health']})"
    )
    if program.get('computed_progress_pct') is not None and program.get('computed_progress_pct') != program.get('progress_pct'):
        print(f"Manual progress: {program['progress_pct']}%")
    print(f"Phases: {phases}")
    print(f"Focus epics: {focus}")
    print(next_line)
    sys.exit(0)

print(f"Roadmap Status — {date.today().isoformat()}")
print(
    f"Program: {program['name']} — {program['progress_pct']}% complete (health: {program['health']})"
)
if program.get('computed_progress_pct') is not None:
    print(
        f"Computed progress: {program['computed_progress_pct']}% (manual {program['progress_pct']}%)"
    )
if warnings:
    print("Warnings:")
    for msg in warnings:
        print(f"- {msg}")
    print()
print("Phase Timeline:")
for phase in phase_order:
    milestone = milestone_by_title.get(phase)
    due = milestone["due"] if milestone else "n/a"
    status = milestone["status"] if milestone else "not_planned"
    pct = phase_map.get(phase, 0)
    print(f"- {phase}: {pct}% — status {status} — due {due}")
print()

print("Epics:")
for epic in epics:
    computed = epic.get('computed_progress_pct', epic['progress_pct'])
    manual = epic['progress_pct']
    extra = f" (derived {computed}% vs manual {manual}%)" if computed != manual else ""
    print(
        f"- {epic['id']} — {epic['title']} — {computed}% (status {epic['status']}, priority {epic['priority']}, size {epic['size_points']}){extra}"
    )
    for task in [t for t in big_tasks if t['parent_epic'] == epic['id']]:
        print(
            f"    * {task['id']} — {task['title']} — {task['progress_pct']}% (status {task['status']}, size {task['size_points']})"
        )
PY
