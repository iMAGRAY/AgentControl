#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
LC_ALL=C.UTF-8

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib/common.sh"
export SDK_ROOT

sdk::log "INF" "Синхронизация прогресса"
"$SDK_ROOT/scripts/progress.py" || sdk::log "WRN" "progress завершился с предупреждением"
printf '\n'
sdk::log "INF" "Синхронизация roadmap"
"$SDK_ROOT/scripts/sync-roadmap.sh" >/dev/null || sdk::log "WRN" "sync-roadmap завершился с предупреждением"

sdk::log "INF" "Roadmap summary"
ROADMAP_SKIP_PROGRESS=1 "$SDK_ROOT/scripts/roadmap-status.sh" compact
printf '\n'

sdk::log "INF" "Task board summary"
"$SDK_ROOT/scripts/task.sh" summary

mkdir -p "$SDK_ROOT/reports"
ROADMAP_JSON="$(ROADMAP_SKIP_PROGRESS=1 "$SDK_ROOT/scripts/roadmap-status.sh" json)"
TASK_JSON="$("$SDK_ROOT/scripts/task.sh" summary --json)"
export ROADMAP_JSON TASK_JSON
python3 <<'PY'
import json
import os
from datetime import datetime, timezone
from pathlib import Path

roadmap = json.loads(os.environ.get("ROADMAP_JSON", "{}"))
tasks = json.loads(os.environ.get("TASK_JSON", "{}"))
report = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "roadmap": roadmap,
    "tasks": tasks,
}
path = Path(os.environ["SDK_ROOT"]) / "reports" / "status.json"
path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
unset ROADMAP_JSON TASK_JSON
