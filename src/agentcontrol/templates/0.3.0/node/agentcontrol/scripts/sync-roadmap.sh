#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
LC_ALL=C.UTF-8

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib/common.sh"

TODO_FILE="$SDK_ROOT/todo.machine.md"
if [[ ! -f "$TODO_FILE" ]]; then
  sdk::log "WRN" "todo.machine.md не найден — синхронизация пропущена"
  exit 0
fi

STATUS_JSON="$SDK_ROOT/reports/.sync-roadmap.json"
mkdir -p "$SDK_ROOT/reports"
if ! ROADMAP_SKIP_PROGRESS=1 "$SDK_ROOT/scripts/roadmap-status.sh" json > "$STATUS_JSON" 2>/dev/null; then
  sdk::log "WRN" "roadmap-status json недоступен — синхронизация пропущена"
  rm -f "$STATUS_JSON"
  exit 0
fi

python3 - "$TODO_FILE" "$STATUS_JSON" <<'PY'
import json
import re
import sys
from pathlib import Path

todo_path = Path(sys.argv[1])
status_path = Path(sys.argv[2])
text = todo_path.read_text(encoding="utf-8")
status = json.loads(status_path.read_text(encoding="utf-8"))

program = status.get("program", {})
epics = status.get("epics", [])
big_tasks = status.get("big_tasks", [])
phase_progress = status.get("phase_progress", {})

program_value = int(round(program.get("computed_progress_pct", program.get("progress_pct", 0))))

# Update Program block
def update_program(match):
    header, body, footer = match.groups()
    body = re.sub(r"progress_pct:\s*\d+", f"progress_pct: {program_value}", body)
    if phase_progress:
        lines = "\n".join(
            f"  {phase}: {int(round(phase_progress.get(phase, program_value)))}"
            for phase in phase_progress
        )
        body = re.sub(r"phase_progress:\n(?:\s{2}.+\n)+", f"phase_progress:\n{lines}\n", body)
    return header + body + footer

program_pattern = re.compile(r"(## Program\n```yaml\n)(.*?)(\n```)", re.S)
text = program_pattern.sub(update_program, text, count=1)

# Helper to update progress within blocks by id
def update_entity(block_name: str, entity_id: str, new_value: int) -> str:
    pattern = re.compile(rf"(## {block_name}\n```yaml\n)(.*?)(\n```)", re.S)

    def transformer(match):
        header, body, footer = match.groups()
        entity_pattern = re.compile(rf"(id: {re.escape(entity_id)}\n)(.*?)(?=\nid:|\Z)", re.S)

        def repl_entity(entity_match):
            start, entity_body = entity_match.groups()
            entity_body = re.sub(r"progress_pct:\s*\d+", f"progress_pct: {new_value}", entity_body)
            return start + entity_body

        new_body, count = entity_pattern.subn(repl_entity, body)
        return header + new_body + footer

    text_with_update, count = pattern.subn(transformer, text)
    return text_with_update if count else text

# Update epics
for epic in epics:
    value = int(round(epic.get("computed_progress_pct", epic.get("progress_pct", program_value))))
    text = update_entity("Epics", epic.get("id"), value)

# Update big tasks (fallback: parent epic)
for bt in big_tasks:
    computed = bt.get("computed_progress_pct")
    if computed is None:
        parent_id = bt.get("parent_epic")
        parent = next((e for e in epics if e.get("id") == parent_id), None)
        if parent:
            computed = parent.get("computed_progress_pct", parent.get("progress_pct", program_value))
        else:
            computed = program_value
    text = update_entity("Big Tasks", bt.get("id"), int(round(computed)))

if text != todo_path.read_text(encoding="utf-8"):
    todo_path.write_text(text, encoding="utf-8")
PY

rm -f "$STATUS_JSON"
