#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
LC_ALL=C.UTF-8

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib/common.sh"
export SDK_ROOT

sdk::log "INF" "Synchronising progress"
"$SDK_ROOT/scripts/progress.py" || sdk::log "WRN" "progress finished with warnings"
printf '\n'
sdk::log "INF" "Synchronising roadmap"
"$SDK_ROOT/scripts/sync-roadmap.sh" >/dev/null || sdk::log "WRN" "sync-roadmap finished with warnings"

sdk::log "INF" "Roadmap summary"
ROADMAP_SKIP_PROGRESS=1 "$SDK_ROOT/scripts/roadmap-status.sh" compact
printf '\n'

sdk::log "INF" "Task board summary"
"$SDK_ROOT/scripts/task.sh" summary

sdk::log "INF" "Auto-update telemetry summary"
AUTO_UPDATE_JSON="$(PYTHONPATH="$SDK_ROOT/src" python3 <<'PY'
import json
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

def load_events(path: Path) -> list[dict]:
    if not path.exists():
        return []
    events = deque(maxlen=500)
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if payload.get("event") == "auto-update":
                events.append(payload)
    return list(events)

log_path = Path.home() / ".agentcontrol" / "logs" / "telemetry.jsonl"
events = load_events(log_path)
counts: dict[str, int] = {}
last_event: dict | None = None
last_fallback: dict | None = None
for payload in events:
    status = payload.get("payload", {}).get("status", "unknown")
    counts[status] = counts.get(status, 0) + 1
    last_event = payload
    if status.startswith("fallback_"):
        last_fallback = payload

summary = {
    "window_events": len(events),
    "counts": counts,
    "last_event": last_event,
    "last_fallback": last_fallback,
    "generated_at": datetime.now(timezone.utc).isoformat(),
}
print(json.dumps(summary, ensure_ascii=False))
PY
)"
export AUTO_UPDATE_JSON

python3 <<'PY'
import json
import os

data = json.loads(os.environ.get("AUTO_UPDATE_JSON", "{}"))
count = data.get("window_events", 0)
if count == 0:
    print("  No recent auto-update telemetry events (window=500).")
else:
    counts = data.get("counts", {})
    parts = [f"{k}={v}" for k, v in sorted(counts.items())]
    print(f"  window_events={count}; " + ", ".join(parts))
    fallback = data.get("last_fallback")
    if fallback:
        payload = fallback.get("payload", {})
        ts = fallback.get("ts")
        cache_path = payload.get("cache_path", "n/a")
        print(f"  last_fallback@{ts}: status={payload.get('status')} cache={cache_path}")
    last_event = data.get("last_event")
    if last_event and last_event is not fallback:
        payload = last_event.get("payload", {})
        print(
            "  last_event@{ts}: status={status} command={cmd}".format(
                ts=last_event.get("ts"),
                status=payload.get("status"),
                cmd=payload.get("command"),
            )
        )
PY

mkdir -p "$SDK_ROOT/reports"
ROADMAP_JSON="$(ROADMAP_SKIP_PROGRESS=1 "$SDK_ROOT/scripts/roadmap-status.sh" json)"
TASK_JSON="$("$SDK_ROOT/scripts/task.sh" summary --json)"
export ROADMAP_JSON TASK_JSON AUTO_UPDATE_JSON
python3 <<'PY'
import json
import os
from datetime import datetime, timezone
from pathlib import Path

roadmap = json.loads(os.environ.get("ROADMAP_JSON", "{}"))
tasks = json.loads(os.environ.get("TASK_JSON", "{}"))
auto_update = json.loads(os.environ.get("AUTO_UPDATE_JSON", "{}"))
report = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "roadmap": roadmap,
    "tasks": tasks,
    "auto_update": auto_update,
}
path = Path(os.environ["SDK_ROOT"]) / "reports" / "status.json"
path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

context_dir = Path(os.environ["SDK_ROOT"]) / "context"
context_dir.mkdir(parents=True, exist_ok=True)
summary_path = context_dir / "auto-update-summary.json"
summary_payload = {
    "generated_at": report["generated_at"],
    "counts": auto_update.get("counts", {}),
    "last_event": auto_update.get("last_event"),
    "last_fallback": auto_update.get("last_fallback"),
}
summary_path.write_text(json.dumps(summary_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
unset ROADMAP_JSON TASK_JSON AUTO_UPDATE_JSON
