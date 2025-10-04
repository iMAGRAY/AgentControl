#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
LC_ALL=C.UTF-8

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib/common.sh"

sdk::log "INF" "Initialising SDK workspace"

CONFIG_FILE="$SDK_ROOT/config/commands.sh"
BOARD_FILE="$SDK_ROOT/data/tasks.board.json"
STATE_FILE="$SDK_ROOT/state/task_state.json"
LEGACY_STATE_FILE="$SDK_ROOT/state/task_selection.json"
JOURNAL_FILE="$SDK_ROOT/journal/task_events.jsonl"
TODO_FILE="$SDK_ROOT/todo.machine.md"
REPORTS_DIR="$SDK_ROOT/reports"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

mkdir -p "$SDK_ROOT/config" "$SDK_ROOT/data" "$SDK_ROOT/state" "$SDK_ROOT/journal" "$REPORTS_DIR"

if [[ ! -f "$CONFIG_FILE" ]]; then
  sdk::log "INF" "Creating config/commands.sh"
  cat <<'CFG' >"$CONFIG_FILE"
# Define command sets for your stack.
# Examples:
# SDK_DEV_COMMANDS=("npm install" "npm run dev")
# SDK_VERIFY_COMMANDS=("npm run lint" "npm test")
# SDK_FIX_COMMANDS=("npm run lint -- --fix")
# SDK_SHIP_COMMANDS=("npm run build" "npm publish")
# SDK_REVIEW_LINTERS=("reviewdog -conf=.reviewdog.yml")
# SDK_TEST_COMMAND="pytest --maxfail=1 --disable-warnings --cov"
# SDK_COVERAGE_FILE="coverage.xml"

SDK_DEV_COMMANDS=("echo 'configure SDK_DEV_COMMANDS in config/commands.sh'")
SDK_VERIFY_COMMANDS=("echo 'configure SDK_VERIFY_COMMANDS in config/commands.sh'")
SDK_FIX_COMMANDS=("echo 'configure SDK_FIX_COMMANDS in config/commands.sh'")
SDK_SHIP_COMMANDS=("echo 'configure SDK_SHIP_COMMANDS in config/commands.sh'")
SDK_REVIEW_LINTERS=()
SDK_TEST_COMMAND=""
SDK_COVERAGE_FILE=""
CFG
else
  sdk::log "INF" "config/commands.sh already exists — skipping"
fi

if [[ ! -f "$BOARD_FILE" ]]; then
  sdk::log "INF" "Creating data/tasks.board.json"
  cat <<BOARD >"$BOARD_FILE"
{
  "version": "v1",
  "updated_at": "$NOW",
  "tasks": [
    {
      "id": "T-001",
      "title": "Foundation setup",
      "epic": "default",
      "status": "backlog",
      "priority": "P0",
      "size_points": 8,
      "owner": "unassigned",
      "success_criteria": [
        "Environment passes agentcall verify.",
        "Documentation refreshed after init."
      ],
      "failure_criteria": [
        "Status command fails or produces an empty report."
      ],
      "blockers": [],
      "dependencies": [],
      "conflicts": [],
      "comments": []
    }
  ]
}
BOARD
else
  sdk::log "INF" "tasks.board.json already exists — skipping"
fi

if [[ -f "$LEGACY_STATE_FILE" && ! -f "$STATE_FILE" ]]; then
  sdk::log "INF" "Converting legacy state/task_selection.json"
  python3 - "$SDK_ROOT" <<'PY'
import json, sys
from pathlib import Path
root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
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
  sdk::log "INF" "Creating state/task_state.json"
  cat <<'STATE' >"$STATE_FILE"
{
  "assignments": {}
}
STATE
fi

if [[ ! -f "$JOURNAL_FILE" ]]; then
  sdk::log "INF" "Creating journal/task_events.jsonl"
  : > "$JOURNAL_FILE"
fi

if [[ ! -f "$TODO_FILE" ]]; then
  sdk::log "INF" "Creating baseline todo.machine.md"
  # shellcheck disable=SC2215,SC2006,SC2086,SC1130,SC1083
  cat <<TODO >"$TODO_FILE"
## Program
```yaml
program: v1
updated_at: $NOW
program_id: default-program
name: AgentControl Universal Agent SDK Project
objectives:
  - Run init and baseline checks.
  - Configure agentcall status and the task board.
  - Define next epic.
kpis: { uptime_pct: 99.9, tti_ms: 1500, error_rate_pct: 0.3 }
progress_pct: 0
health: green
phase_progress:
  MVP: 0
  Q1: 0
  Q2: 0
  Q3: 0
  Q4: 0
  Q5: 0
  Q6: 0
  Q7: 0
milestones:
  - { id: m_mvp, title: "MVP", due: 2025-12-01T00:00:00Z, status: planned }
policies:
  task_min_points: 5
```

## Epics
```yaml
id: default-epic
title: "Define first deliverable"
type: epic
status: planned
priority: P1
size_points: 8
scope_paths:
  - scripts/**
  - data/**
  - docs/**
spec: |
  Intent: define and implement first delivery.
  Given: empty project.
  When: agent populates plans and tasks.
  Then: roadmap and task board synchronized.
budgets: { latency_ms: 0, memory_mb: 0, bundle_kb: 0 }
risks: []
dependencies: []
big_tasks_planned:
  - task-bootstrap
progress_pct: 0
health: green
tests_required:
  - agentcall verify
verify_commands:
  - agentcall verify
docs_updates:
  - README.md
artifacts:
  - scripts/
audit:
  created_at: $NOW
  created_by: gpt-5-codex
```

## Big Tasks
```yaml
id: task-bootstrap
title: "Populate plan and tasks"
type: planning
status: planned
priority: P1
size_points: 5
parent_epic: default-epic
scope_paths:
  - todo.machine.md
  - data/tasks.board.json
spec: |
  When: agent runs agentcall init.
  Then: roadmap and task board populated and ready for work.
budgets: { latency_ms: 0, memory_mb: 0, bundle_kb: 0 }
risks: []
dependencies: []
progress_pct: 0
health: green
acceptance:
  - agentcall status outputs meaningful data.
  - task board contains at least one task.
tests_required:
  - agentcall status
verify_commands:
  - agentcall status
docs_updates:
  - README.md
artifacts:
  - data/tasks.board.json
```
TODO
fi

sdk::log "INF" "Generating status report"
if "$SDK_ROOT/scripts/status.sh" >/dev/null; then
  sdk::log "INF" "reports/status.json updated"
else
  sdk::log "WRN" "Failed to generate status.json during init phase"
fi

sdk::log "INF" "Initialization complete"
