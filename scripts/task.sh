#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
LC_ALL=C.UTF-8

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib/common.sh"

BOARD_FILE="$SDK_ROOT/data/tasks.board.json"
STATE_FILE="$SDK_ROOT/state/task_state.json"
LEGACY_STATE_FILE="$SDK_ROOT/state/task_selection.json"
LOG_FILE="$SDK_ROOT/journal/task_events.jsonl"

if [[ ! -f "$BOARD_FILE" ]]; then
  sdk::die "data/tasks.board.json не найден — выполните make init или создайте доску задач"
fi

mkdir -p "$(dirname "$STATE_FILE")" "$(dirname "$LOG_FILE")"
if [[ -f "$LEGACY_STATE_FILE" && ! -f "$STATE_FILE" ]]; then
  sdk::log "INF" "Обновляю формат state/task_selection.json"
  python3 <<'PY'
import json
from pathlib import Path
root = Path(__file__).resolve().parents[1]
legacy = root / "state" / "task_selection.json"
state = root / "state" / "task_state.json"
assignments = {}
if legacy.exists():
    data = json.loads(legacy.read_text(encoding="utf-8"))
    for event in data.get("events", []) or data.get("selections", []):
        task = event.get("task")
        agent = event.get("agent")
        if task and agent:
            assignments[task] = agent
state.parent.mkdir(parents=True, exist_ok=True)
state.write_text(json.dumps({"assignments": assignments}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
legacy.unlink(missing_ok=True)
PY
fi

if [[ ! -f "$STATE_FILE" ]]; then
  printf '{"assignments": {}}\n' >"$STATE_FILE"
fi

if [[ ! -f "$LOG_FILE" ]]; then
  : > "$LOG_FILE"
fi

COMMAND="${1:-list}"
shift || true

python3 - "$COMMAND" "$BOARD_FILE" "$STATE_FILE" "$LOG_FILE" "$@" <<'PY'
import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ALIAS = {
    "take": "grab",
    "drop": "release",
    "done": "complete",
    "ls": "list"
}

STATUS_ORDER = [
    "in_progress",
    "review",
    "ready",
    "backlog",
    "blocked",
    "done",
]
STATUS_TITLES = {
    "in_progress": "In Progress",
    "review": "Review",
    "ready": "Ready",
    "backlog": "Backlog",
    "blocked": "Blocked",
    "done": "Done",
}
PRIORITY_RANK = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
STATUS_PROGRESS = {
    "done": 1.0,
    "review": 0.9,
    "ready": 0.75,
    "in_progress": 0.5,
    "backlog": 0.0,
    "blocked": 0.0,
}
DEFAULT_OWNER = "unassigned"

COMMAND = sys.argv[1]
COMMAND = ALIAS.get(COMMAND.lower(), COMMAND.lower())
BOARD_PATH = Path(sys.argv[2])
STATE_PATH = Path(sys.argv[3])
LOG_PATH = Path(sys.argv[4])
RAW_ARGS = sys.argv[5:]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path, default: Any) -> Any:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default
    return default


def save_json_atomic(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def append_log(event: dict) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")


board = load_json(BOARD_PATH, {"tasks": []})
state = load_json(STATE_PATH, {"assignments": {}})
if "events" in state:
    # legacy structure
    assignments: dict[str, str] = {}
    for event in state.get("events", []):
        task = event.get("task")
        agent = event.get("agent")
        if task and agent:
            assignments[task] = agent
    state = {"assignments": assignments}
    save_json_atomic(STATE_PATH, state)

assignments: dict[str, str] = state.setdefault("assignments", {})


def touch_board() -> None:
    board["updated_at"] = now_iso()


def mapping() -> dict[str, dict]:
    return {task.get("id"): task for task in board.get("tasks", [])}


def normalize_task(task: dict) -> None:
    task.setdefault("priority", "P2")
    task.setdefault("size_points", 5)
    task.setdefault("status", "backlog")
    task.setdefault("owner", DEFAULT_OWNER)
    task.setdefault("big_task", None)
    task.setdefault("success_criteria", [])
    task.setdefault("failure_criteria", [])
    task.setdefault("blockers", [])
    task.setdefault("dependencies", [])
    task.setdefault("conflicts", [])
    task.setdefault("comments", [])


for task in board.get("tasks", []):
    normalize_task(task)


def priority_rank(task: dict) -> int:
    return PRIORITY_RANK.get(task.get("priority", "P3"), 99)


def status_rank(task: dict) -> int:
    try:
        return STATUS_ORDER.index(task.get("status", "backlog"))
    except ValueError:
        return 99


def dependency_status(task: dict, tasks_map: dict[str, dict]) -> str:
    deps = task.get("dependencies", [])
    if not deps:
        return ""
    rendered = []
    for dep_id in deps:
        dep = tasks_map.get(dep_id)
        if not dep:
            rendered.append(f"{dep_id}(missing)")
            continue
        rendered.append(f"{dep_id}({dep.get('status', 'unknown')})")
    return "Depends: " + ", ".join(rendered)


def blockers_status(task: dict) -> str:
    blockers = task.get("blockers", [])
    if blockers:
        return "Blockers: " + ", ".join(blockers)
    return ""


def conflicts_status(task: dict) -> str:
    conflicts = task.get("conflicts", [])
    if conflicts:
        return "Conflicts: " + ", ".join(conflicts)
    return ""


def success_lines(task: dict) -> list[str]:
    return ["Success> " + crit for crit in task.get("success_criteria", [])]


def failure_lines(task: dict) -> list[str]:
    return ["Failure> " + crit for crit in task.get("failure_criteria", [])]


def last_comment(task: dict) -> str:
    comments = task.get("comments", [])
    if not comments:
        return ""
    last = comments[-1]
    return f"Last comment: [{last['timestamp']}] {last['author']}: {last['message']}"


def task_progress(task: dict) -> float:
    return STATUS_PROGRESS.get(task.get("status", "backlog"), 0.0)


def ensure_task(task_id: str) -> dict:
    tasks_map = mapping()
    task = tasks_map.get(task_id)
    if not task:
        raise SystemExit(f"Задача {task_id} не найдена")
    return task


def ensure_agent(value: str | None) -> str:
    agent = value or os.environ.get("AGENT") or "gpt-5-codex"
    return agent


def ensure_task_arg(value: str | None) -> str:
    task_id = value or os.environ.get("TASK")
    if not task_id:
        raise SystemExit("Укажите TASK=<id> или аргумент --task")
    return task_id


def pick_note(value: str | None, default: str) -> str:
    return value or os.environ.get("NOTE") or default


def parse_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(',') if item.strip()]


def append_event(action: str, *, task: str, agent: str, note: str, previous_owner: str | None = None) -> None:
    event = {
        "action": action,
        "task": task,
        "agent": agent,
        "note": note,
        "timestamp": now_iso(),
    }
    if previous_owner is not None:
        event["previous_owner"] = previous_owner
    append_log(event)


def read_history(limit: int) -> list[dict]:
    if not LOG_PATH.exists():
        return []
    lines = LOG_PATH.read_text(encoding="utf-8", errors="ignore").splitlines()
    tail = lines[-limit:]
    events = []
    for line in tail:
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def compute_summary() -> dict:
    tasks = board.get("tasks", [])
    counts = Counter(task.get("status", "unknown") for task in tasks)
    summary = {
        "generated_at": now_iso(),
        "board_version": board.get("version", "n/a"),
        "updated_at": board.get("updated_at"),
        "counts": {status: counts.get(status, 0) for status in STATUS_ORDER},
        "events": read_history(10),
        "assignments": assignments.copy(),
    }
    tasks_map = mapping()
    candidates = [
        t for t in tasks
        if t.get("status") in {"ready", "backlog"}
        and assignments.get(t.get("id"), DEFAULT_OWNER) == DEFAULT_OWNER
    ]
    ordered = sorted(candidates, key=lambda t: (priority_rank(t), status_rank(t), tasks.index(t)))
    for t in ordered:
        deps = [dep for dep in t.get("dependencies", []) if tasks_map.get(dep, {}).get("status") not in {"done", "review"}]
        conflicts = [conf for conf in t.get("conflicts", []) if tasks_map.get(conf, {}).get("status") in {"in_progress", "review"}]
        if deps or conflicts:
            continue
        summary["next_task"] = {
            "id": t.get("id"),
            "title": t.get("title"),
            "priority": t.get("priority"),
        }
        break
    return summary


def list_tasks(compact: bool) -> None:
    summary = compute_summary()
    counts_line = " | ".join(
        f"{STATUS_TITLES.get(status, status)}={summary['counts'].get(status, 0)}"
        for status in STATUS_ORDER
    )
    print(f"Task Board — {summary['generated_at']}")
    print(f"Board version: {summary['board_version']} (updated_at {summary['updated_at']})")
    print("Summary: " + counts_line)
    print()

    groups: dict[str, list[dict]] = {}
    for task in board.get("tasks", []):
        groups.setdefault(task.get("status", "backlog"), []).append(task)

    tasks_map = mapping()

    for status in STATUS_ORDER:
        items = groups.get(status, [])
        if not items:
            continue
        title = STATUS_TITLES.get(status, status)
        print(f"{title} ({len(items)}):")
        for task in sorted(items, key=lambda t: (priority_rank(t), t.get("id"))):
            owner = assignments.get(task.get("id"), task.get("owner", DEFAULT_OWNER))
            line = f"  - {task['id']} [{task.get('priority','P3')}] owner={owner}"
            if status in {"in_progress", "blocked", "review"}:
                line += " *focus"
            print(line)
            if compact:
                continue
            for extra in (
                dependency_status(task, tasks_map),
                blockers_status(task),
                conflicts_status(task),
            ):
                if extra:
                    print(f"      {extra}")
            for extra_line in success_lines(task):
                print(f"      {extra_line}")
            for extra_line in failure_lines(task):
                print(f"      {extra_line}")
            last = last_comment(task)
            if last:
                print(f"      {last}")
        print()

    if compact:
        return
    events = summary.get("events", [])[-5:]
    if events:
        print("Recent events:")
        for event in events:
            print(
                f"- {event.get('timestamp', '?')} — {event.get('agent', '?')} -> {event.get('task', '?')} "
                f"[{event.get('action', 'assign')}] {event.get('note', '')}"
            )


def print_conflicts() -> None:
    print("Task Conflicts Map:")
    for task in board.get("tasks", []):
        conflicts = task.get("conflicts", [])
        target = ", ".join(conflicts) if conflicts else "none"
        print(f"- {task['id']} -> {target}")


def validate_board() -> None:
    ids = [t.get("id") for t in board.get("tasks", [])]
    if len(ids) != len(set(ids)):
        raise SystemExit("Обнаружены дублирующиеся идентификаторы задач")
    tasks_map = mapping()
    for task in board.get("tasks", []):
        task_id = task.get("id")
        for dep in task.get("dependencies", []):
            if dep == task_id:
                raise SystemExit(f"Задача {task_id} зависит сама от себя")
            if dep not in tasks_map:
                raise SystemExit(f"Задача {task_id} зависит от отсутствующей задачи {dep}")
        for blocker in task.get("blockers", []):
            if blocker not in tasks_map:
                raise SystemExit(f"Задача {task_id} ссылается на отсутствующий blocker {blocker}")
        for conflict in task.get("conflicts", []):
            if conflict not in tasks_map:
                raise SystemExit(f"Задача {task_id} конфликтует с отсутствующей задачей {conflict}")
        if task.get("status") == "blocked" and not task.get("blockers"):
            raise SystemExit(f"Задача {task_id} помечена blocked без blockers")
    print("Task board validation passed")


def assign_task(task_id: str, agent: str, note: str, *, action: str, force: bool) -> None:
    task = ensure_task(task_id)
    tasks_map = mapping()
    if task.get("status") == "done" and not force:
        raise SystemExit(f"Задача {task_id} уже завершена; используйте FORCE=1")
    conflicts = []
    for conflict_id in task.get("conflicts", []):
        conflict = tasks_map.get(conflict_id)
        if conflict and conflict.get("status") in {"in_progress", "review"} and assignments.get(conflict_id) not in {None, DEFAULT_OWNER, agent}:
            conflicts.append(f"{conflict_id} ({assignments.get(conflict_id)})")
    if conflicts and not force:
        raise SystemExit(f"Конфликты: {', '.join(conflicts)} — укажите FORCE=1")
    for dep_id in task.get("dependencies", []):
        dep = tasks_map.get(dep_id)
        if not dep:
            raise SystemExit(f"Несуществующая зависимость {dep_id}")
        if dep.get("status") not in {"done", "review"} and assignments.get(dep_id) not in {agent} and not force:
            raise SystemExit(f"Зависимость {dep_id} ещё не готова (status {dep.get('status')})")
    previous_owner = assignments.get(task_id, task.get("owner", DEFAULT_OWNER))
    assignments[task_id] = agent
    task["owner"] = agent
    if task.get("status") in {"backlog", "ready", "blocked"}:
        task["status"] = "in_progress"
    touch_board()
    save_json_atomic(BOARD_PATH, board)
    save_json_atomic(STATE_PATH, {"assignments": assignments})
    append_event(action, task=task_id, agent=agent, note=note, previous_owner=previous_owner)
    print(f"Задача {task_id} назначена на {agent}. Предыдущий владелец: {previous_owner}")


def release_task(task_id: str, note: str) -> None:
    task = ensure_task(task_id)
    previous_owner = assignments.pop(task_id, task.get("owner", DEFAULT_OWNER))
    task["owner"] = DEFAULT_OWNER
    if task.get("status") == "in_progress":
        task["status"] = "ready"
    touch_board()
    save_json_atomic(BOARD_PATH, board)
    save_json_atomic(STATE_PATH, {"assignments": assignments})
    append_event("release", task=task_id, agent=previous_owner, note=note)
    print(f"Задача {task_id} освобождена (owner -> {DEFAULT_OWNER})")


def complete_task(task_id: str, agent: str, note: str) -> None:
    task = ensure_task(task_id)
    previous_owner = assignments.pop(task_id, task.get("owner", DEFAULT_OWNER))
    task["owner"] = agent
    task["status"] = "done"
    touch_board()
    save_json_atomic(BOARD_PATH, board)
    save_json_atomic(STATE_PATH, {"assignments": assignments})
    append_event("complete", task=task_id, agent=agent, note=note, previous_owner=previous_owner)
    print(f"Задача {task_id} отмечена как завершённая")


def comment_task(task_id: str, author: str, message: str) -> None:
    task = ensure_task(task_id)
    entry = {
        "author": author,
        "timestamp": now_iso(),
        "message": message,
    }
    task.setdefault("comments", []).append(entry)
    touch_board()
    save_json_atomic(BOARD_PATH, board)
    append_event("comment", task=task_id, agent=author, note=message)
    print(f"Комментарий добавлен к {task_id}")


def grab_task(agent: str, note: str, *, force: bool) -> None:
    tasks = board.get("tasks", [])
    tasks_map = mapping()
    candidates = [
        t for t in tasks
        if t.get("status") in {"ready", "backlog"}
        and assignments.get(t.get("id"), t.get("owner", DEFAULT_OWNER)) == DEFAULT_OWNER
    ]
    ordered = sorted(candidates, key=lambda t: (priority_rank(t), status_rank(t), tasks.index(t)))
    for task in ordered:
        deps_blocking = [dep for dep in task.get("dependencies", []) if tasks_map.get(dep, {}).get("status") not in {"done", "review"}]
        conflicts = [conf for conf in task.get("conflicts", []) if tasks_map.get(conf, {}).get("status") in {"in_progress", "review"}]
        if (deps_blocking or conflicts) and not force:
            continue
        assign_task(task.get("id"), agent, note, action="grab", force=force)
        return
    print("Нет доступных задач для захвата")


def add_task(args: argparse.Namespace) -> None:
    tasks = board.setdefault("tasks", [])
    next_id = args.id
    if not next_id:
        existing = [t.get("id") for t in tasks if t.get("id", "").startswith("T-")]
        max_num = 0
        for tid in existing:
            try:
                max_num = max(max_num, int(tid.split("-", 1)[1]))
            except Exception:
                continue
        next_id = f"T-{max_num + 1:03d}"
    if any(t.get("id") == next_id for t in tasks):
        raise SystemExit(f"Задача {next_id} уже существует")
    new_task = {
        "id": next_id,
        "title": args.title,
        "epic": args.epic,
        "status": args.status,
        "priority": args.priority,
        "size_points": args.size,
        "owner": DEFAULT_OWNER,
        "success_criteria": args.success,
        "failure_criteria": args.failure,
        "blockers": args.blockers,
        "dependencies": args.dependencies,
        "conflicts": args.conflicts,
        "big_task": args.big_task,
        "comments": [],
    }
    normalize_task(new_task)
    tasks.append(new_task)
    touch_board()
    save_json_atomic(BOARD_PATH, board)
    append_event("add", task=next_id, agent=args.agent, note=args.note)
    print(f"Добавлена задача {next_id}: {args.title}")


if COMMAND in {"list", "status"}:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args(RAW_ARGS)
    list_tasks(compact=args.compact)
elif COMMAND == "summary":
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(RAW_ARGS)
    summary = compute_summary()
    if args.json:
        print(json.dumps(summary, ensure_ascii=False))
    else:
        counts_line = " | ".join(
            f"{STATUS_TITLES.get(status, status)}={summary['counts'].get(status, 0)}"
            for status in STATUS_ORDER
        )
        print(f"Task Board — {summary['generated_at']}")
        print(f"Board version: {summary['board_version']} (updated_at {summary['updated_at']})")
        print("Summary: " + counts_line)
        if summary.get("next_task"):
            nt = summary["next_task"]
            print(f"Next task: {nt['id']} ({nt['priority']}) — {nt['title']}")
        events = summary.get("events", [])[-5:]
        if events:
            print("Recent events:")
            for event in events:
                print(
                    f"- {event.get('timestamp', '?')} — {event.get('agent', '?')} -> {event.get('task', '?')} "
                    f"[{event.get('action', 'assign')}] {event.get('note', '')}"
                )
elif COMMAND == "conflicts":
    print_conflicts()
elif COMMAND in {"assign", "select"}:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task")
    parser.add_argument("--agent")
    parser.add_argument("--note")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(RAW_ARGS)
    task_id = ensure_task_arg(args.task)
    agent = ensure_agent(args.agent)
    note = pick_note(args.note, "manual assign")
    assign_task(task_id, agent, note, action="assign", force=args.force or bool(os.environ.get("FORCE")))
elif COMMAND == "grab":
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent")
    parser.add_argument("--note")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(RAW_ARGS)
    agent = ensure_agent(args.agent)
    note = pick_note(args.note, "auto-grab")
    force = args.force or os.environ.get("FORCE", "0").lower() in {"1", "true", "yes", "on"}
    grab_task(agent, note, force=force)
elif COMMAND == "release":
    parser = argparse.ArgumentParser()
    parser.add_argument("--task")
    parser.add_argument("--note")
    args = parser.parse_args(RAW_ARGS)
    task_id = ensure_task_arg(args.task)
    note = pick_note(args.note, "release")
    release_task(task_id, note)
elif COMMAND == "complete":
    parser = argparse.ArgumentParser()
    parser.add_argument("--task")
    parser.add_argument("--agent")
    parser.add_argument("--note")
    args = parser.parse_args(RAW_ARGS)
    task_id = ensure_task_arg(args.task)
    agent = ensure_agent(args.agent)
    note = pick_note(args.note, "complete")
    complete_task(task_id, agent, note)
elif COMMAND == "comment":
    parser = argparse.ArgumentParser()
    parser.add_argument("--task")
    parser.add_argument("--author")
    parser.add_argument("--message")
    args = parser.parse_args(RAW_ARGS)
    task_id = ensure_task_arg(args.task)
    message = args.message or os.environ.get("MESSAGE")
    if not message:
        raise SystemExit("Укажите MESSAGE=... или аргумент --message")
    author = args.author or os.environ.get("AUTHOR") or "gpt-5-codex"
    comment_task(task_id, author, message)
elif COMMAND == "validate":
    validate_board()
elif COMMAND == "history":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=int(os.environ.get("LIMIT", "10")))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(RAW_ARGS)
    events = read_history(max(1, args.limit))
    json_requested = args.json or os.environ.get("JSON", "0").lower() in {"1", "true", "yes", "on"}
    if json_requested:
        print(json.dumps(events, ensure_ascii=False))
    else:
        if not events:
            print("History is empty")
        for event in events:
            print(
                f"- {event.get('timestamp', '?')} — {event.get('agent', '?')} -> {event.get('task', '?')} "
                f"[{event.get('action', 'assign')}] {event.get('note', '')}"
            )

elif COMMAND == "add":
    parser = argparse.ArgumentParser()
    parser.add_argument("--title")
    parser.add_argument("--epic")
    parser.add_argument("--priority")
    parser.add_argument("--size", type=float)
    parser.add_argument("--status")
    parser.add_argument("--blockers")
    parser.add_argument("--dependencies")
    parser.add_argument("--conflicts")
    parser.add_argument("--success")
    parser.add_argument("--failure")
    parser.add_argument("--big-task")
    parser.add_argument("--id")
    parser.add_argument("--agent")
    parser.add_argument("--note")
    args = parser.parse_args(RAW_ARGS)
    title = args.title or os.environ.get("TITLE")
    if not title:
        raise SystemExit("Укажите --title или переменную TITLE для новой задачи")
    args.title = title
    args.epic = args.epic or os.environ.get("EPIC", "default")
    args.priority = args.priority or os.environ.get("PRIORITY", "P1")
    size_value = args.size if args.size is not None else os.environ.get("SIZE")
    if isinstance(size_value, str):
        try:
            size_value = float(size_value)
        except ValueError:
            raise SystemExit("SIZE должен быть числом")
    if size_value is None:
        size_value = 5
    args.size = int(round(size_value))
    args.status = args.status or os.environ.get("STATUS", "backlog")
    args.blockers = parse_csv(args.blockers or os.environ.get("BLOCKERS"))
    args.dependencies = parse_csv(args.dependencies or os.environ.get("DEPENDENCIES"))
    args.conflicts = parse_csv(args.conflicts or os.environ.get("CONFLICTS"))
    args.success = parse_csv(args.success or os.environ.get("SUCCESS"))
    args.failure = parse_csv(args.failure or os.environ.get("FAILURE"))
    args.big_task = args.big_task or os.environ.get("BIG_TASK")
    args.agent = ensure_agent(args.agent or os.environ.get("AGENT"))
    args.note = args.note or os.environ.get("NOTE") or "add task"
    add_task(args)

else:
    raise SystemExit(f"Неизвестная команда task: {COMMAND}")
PY
