#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
LC_ALL=C.UTF-8

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib/common.sh"

sdk::load_commands

REPORT_DIR="$SDK_ROOT/reports"
mkdir -p "$REPORT_DIR"
PERF_REPORT_DIR="$SDK_ROOT/reports/perf"
mkdir -p "$PERF_REPORT_DIR"
VERIFY_JSON="$REPORT_DIR/verify.json"
STEP_LOG="$REPORT_DIR/verify_steps.jsonl"
: >"$STEP_LOG"
PERF_REPORT_PATH="$PERF_REPORT_DIR/docs_benchmark.json"
PERF_THRESHOLD_MS="${PERF_THRESHOLD_MS:-60000}"
PERF_HISTORY_DIR="$PERF_REPORT_DIR/history"
mkdir -p "$PERF_HISTORY_DIR"

declare -a VERIFY_STEPS
OVERALL_EXIT=0

record_step() {
  local name="$1" status="$2" exit_code="$3" log_path="$4" severity="$5" duration="$6" timeout="$7" timed_out="$8"
  VERIFY_STEPS+=("$name|$status|$exit_code|$log_path|$severity|$duration|$timeout|$timed_out")

  if [[ -n "${STEP_LOG:-}" ]]; then
    python3 - "$name" "$status" "$exit_code" "$severity" "$duration" "$timeout" "$timed_out" "$log_path" "$STEP_LOG" <<'PY'
import json
import pathlib
import sys

name, status, exit_code, severity, duration, timeout, timed_out, log_path, step_log = sys.argv[1:10]
payload = {
    "step": name,
    "status": status,
    "exit_code": int(exit_code),
    "severity": severity,
    "duration_sec": float(duration),
    "timeout_sec": float(timeout),
    "timed_out": timed_out == "1",
    "log": log_path,
}
path = pathlib.Path(step_log)
path.parent.mkdir(parents=True, exist_ok=True)
with path.open("a", encoding="utf-8") as fh:
    fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
PY
  fi

  if [[ $status == "fail" && $severity == "critical" ]]; then
    OVERALL_EXIT=1
  fi
}

run_step() {
  local name="$1" severity="$2" cmd="$3"
  local log_file
  log_file="$(mktemp)"
  sdk::log "RUN" "$name"
  local start_ts
  start_ts=$(python3 - <<'PY'
import time
print(time.time())
PY
)
  set +e
  eval "$cmd" >"$log_file" 2>&1
  local exit_code=$?
  set -e
  local duration
  duration=$(START_TS="$start_ts" python3 - <<'PY'
import os, time
print(f"{time.time()-float(os.environ['START_TS']):.6f}")
PY
  )
  local timeout_sec="${VERIFY_STEP_TIMEOUT:-90}"
  local timed_out=0
  if STEP_DURATION="$duration" STEP_TIMEOUT="$timeout_sec" python3 - <<'PY'
import os
timeout = float(os.environ.get('STEP_TIMEOUT', '0') or 0)
duration = float(os.environ.get('STEP_DURATION', '0'))
if timeout > 0 and duration > timeout:
    raise SystemExit(1)
raise SystemExit(0)
PY
  then
    timed_out=0
  else
    timed_out=1
  fi
  if [[ $timed_out -eq 1 ]]; then
    sdk::log "ERR" "$name: exceeded timeout ${timeout_sec}s"
    exit_code=124
    severity="critical"
  fi
  if [[ $exit_code -eq 0 ]]; then
    sdk::log "INF" "$name: success (${duration}s)"
    record_step "$name" "ok" "$exit_code" "$log_file" "$severity" "$duration" "$timeout_sec" "$timed_out"
  else
    sdk::log "WRN" "$name: exit $exit_code (${duration}s)"
    record_step "$name" "fail" "$exit_code" "$log_file" "$severity" "$duration" "$timeout_sec" "$timed_out"
  fi
}

collect_log_tail() {
  local file="$1"
  if [[ -f "$file" ]]; then
    tail -n 120 "$file"
  else
    printf ""
  fi
}

run_step "sync-architecture" "critical" "\"$SDK_ROOT/scripts/sync-architecture.sh\""
run_step "architecture-integrity" "critical" "\"$SDK_ROOT/scripts/check-architecture-integrity.py\""
run_step "sync-roadmap" "warning" "\"$SDK_ROOT/scripts/sync-roadmap.sh\""

run_step "ensure:AGENTS.md" "critical" "( sdk::ensure_file 'AGENTS.md' )"
run_step "ensure:todo.machine.md" "critical" "( sdk::ensure_file 'todo.machine.md' )"
run_step "ensure:.editorconfig" "critical" "( sdk::ensure_file '.editorconfig' )"
run_step "ensure:.codexignore" "critical" "( sdk::ensure_file '.codexignore' )"
run_step "ensure:data/tasks.board.json" "critical" "( sdk::ensure_file 'data/tasks.board.json' )"

run_step "check:todo_sections" "critical" "grep -q '^## Program' \"$SDK_ROOT/todo.machine.md\" && grep -q '^## Epics' \"$SDK_ROOT/todo.machine.md\" && grep -q '^## Big Tasks' \"$SDK_ROOT/todo.machine.md\""
run_step "make-alignment" "critical" "\"$SDK_ROOT/scripts/check-make-alignment.py\""
run_step "legacy-pipelines" "critical" "\"$SDK_ROOT/scripts/check-legacy-pipelines.py\""

run_step "shellcheck" "warning" "sdk::run_shellcheck_if_available"
run_step "roadmap-status" "warning" "\"$SDK_ROOT/scripts/roadmap-status.sh\" compact"
run_step "task-validate" "warning" "\"$SDK_ROOT/scripts/task.sh\" validate"
run_step "template-integrity" "critical" "\"$SDK_ROOT/scripts/check-template-integrity.py\" --json"
run_step "extension-integrity" "critical" "\"$SDK_ROOT/scripts/check-extension-integrity.py\" --json"
run_step "agent-digest" "warning" "\"$SDK_ROOT/scripts/generate-agent-digest.py\""
run_step "test-place" "warning" "\"$SDK_ROOT/scripts/test-place.sh\""
run_step "mission-activity" "warning" "python3 - <<'PY'
import json
import pathlib
from datetime import datetime

report_dir = pathlib.Path(\"$SDK_ROOT\") / \"reports\"
activity_path = report_dir / \"mission-activity.json\"
if not activity_path.exists():
    raise SystemExit(\"mission-activity.json missing\")
try:
    payload = json.loads(activity_path.read_text(encoding=\"utf-8\"))
except json.JSONDecodeError as exc:
    raise SystemExit(f\"mission-activity.json invalid JSON: {exc}\") from exc
for key in (\"generated_at\", \"activity\"):
    if key not in payload:
        raise SystemExit(f\"mission-activity.json missing '{key}'\")
try:
    datetime.fromisoformat(str(payload[\"generated_at\"]).replace(\"Z\", \"+00:00\"))
except ValueError as exc:
    raise SystemExit(\"mission-activity.json generated_at not ISO8601\") from exc
activity = payload[\"activity\"]
if not isinstance(activity, dict):
    raise SystemExit(\"mission-activity.activity must be an object\")
for field in (\"count\", \"sources\", \"actors\", \"tags\"):
    if field not in activity:
        raise SystemExit(f\"mission-activity.activity missing '{field}'\")
if not isinstance(activity.get(\"count\"), int):
    raise SystemExit(\"mission-activity.activity.count must be int\")
PY"

# quality guard (diff against base commit)
BASE_REF_DEFAULT="${VERIFY_BASE_REF:-origin/main}"
determine_base_commit() {
  local base_ref="$1"
  if git rev-parse --verify HEAD >/dev/null 2>&1; then
    if git rev-parse --verify "$base_ref" >/dev/null 2>&1; then
      git merge-base HEAD "$base_ref"
      return 0
    fi
    if git rev-parse --verify HEAD^ >/dev/null 2>&1; then
      git rev-parse HEAD^
      return 0
    fi
    git rev-parse HEAD
    return 0
  fi
  printf ""
}

BASE_COMMIT="${VERIFY_BASE_COMMIT:-$(determine_base_commit "$BASE_REF_DEFAULT")}" || true
QUALITY_JSON="$REPORT_DIR/verify_quality.json"
if [[ -n "$BASE_COMMIT" ]]; then
  run_step "quality_guard" "warning" "python3 -m scripts.lib.quality_guard --base \"$BASE_COMMIT\" --include-untracked --output \"$QUALITY_JSON\""

else
  sdk::log "WRN" "Failed to determine base commit for quality_guard"
fi

run_step "check-lock" "critical" "\"$SDK_ROOT/scripts/check-lock.sh\""
run_step "scan-sbom" "critical" "\"$SDK_ROOT/scripts/scan-sbom.sh\""

run_step "perf-docs" "warning" "\"$SDK_ROOT/scripts/perf/docs_benchmark.py\" --sections 1000 --trials 5 --report \"$PERF_REPORT_PATH\""
run_step "perf-docs-threshold" "critical" "\"$SDK_ROOT/scripts/perf/check_docs_perf.py\" --report \"$PERF_REPORT_PATH\" --threshold \"$PERF_THRESHOLD_MS\""
PERF_HISTORY_CMD="\"$SDK_ROOT/scripts/perf/compare_history.py\" --report \"$PERF_REPORT_PATH\" --history-dir \"$PERF_HISTORY_DIR\" --diff \"$PERF_HISTORY_DIR/diff.json\" --max-regression-pct \"${PERF_HISTORY_MAX_PCT:-10}\" --max-regression-ms \"${PERF_HISTORY_MAX_MS:-2000}\""
if [[ "${PERF_HISTORY_UPDATE:-0}" == "1" ]]; then
  PERF_HISTORY_CMD="$PERF_HISTORY_CMD --update-history --keep ${PERF_HISTORY_KEEP:-30}"
fi
run_step "perf-history" "warning" "$PERF_HISTORY_CMD"
run_step "hint-docs" "warning" "\"$SDK_ROOT/scripts/check_hint_docs.py\""
# custom verification commands (do not interrupt script)
if [[ ${#SDK_VERIFY_COMMANDS[@]} -eq 0 ]]; then
  sdk::log "INF" "SDK_VERIFY_COMMANDS empty — skipping"
else
  idx=0
  for cmd in "${SDK_VERIFY_COMMANDS[@]}"; do
    idx=$((idx + 1))
    run_step "verify_cmd[$idx]" "warning" "$cmd"
  done
fi

EXIT_ON_FAIL=${EXIT_ON_FAIL:-0}

declare -a steps_json
for entry in "${VERIFY_STEPS[@]}"; do
  IFS='|' read -r name status exit_code log_path severity duration timeout timed_out <<<"$entry"
  LOG_CONTENT="$(collect_log_tail "$log_path" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')"
  steps_json+=("{\"name\":\"$name\",\"status\":\"$status\",\"severity\":\"$severity\",\"exit_code\":$exit_code,\"duration_sec\":$duration,\"timeout_sec\":$timeout,\"timed_out\":$timed_out,\"log_tail\":$LOG_CONTENT}")
done

QUALITY_REPORT="{}"
if [[ -f "$QUALITY_JSON" ]]; then
  QUALITY_REPORT=$(python3 -c 'import json,sys; print(json.dumps(json.load(open(sys.argv[1],encoding="utf-8"))))' "$QUALITY_JSON" 2>/dev/null || printf '{}')
fi

VERIFY_OUTPUT=$(cat <<JSON
{
  "generated_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "base": "$BASE_COMMIT",
  "steps": [$(IFS=,; printf '%s' "${steps_json[*]}")],
  "quality": $QUALITY_REPORT,
  "exit_code": $OVERALL_EXIT
}
JSON
)

printf '%s\n' "$VERIFY_OUTPUT" >"$VERIFY_JSON"
sdk::log "INF" "Report saved: $VERIFY_JSON"

HAS_FINDINGS=0
if [[ -f "$QUALITY_JSON" ]]; then
  FINDINGS_COUNT=$(python3 -c 'import json,sys; data=json.load(open(sys.argv[1],encoding="utf-8")); print(len(data.get("findings",[])))' "$QUALITY_JSON" 2>/dev/null || printf 0)
  if [[ ${FINDINGS_COUNT:-0} -gt 0 ]]; then
    sdk::log "WRN" "quality_guard: detected $FINDINGS_COUNT potential issues"
    HAS_FINDINGS=1
  fi
fi

if [[ $EXIT_ON_FAIL == 1 ]]; then
  if [[ $OVERALL_EXIT -ne 0 || $HAS_FINDINGS -eq 1 ]]; then
    sdk::die "verify: critical issues detected — see $VERIFY_JSON"
  fi
else
  if [[ $OVERALL_EXIT -ne 0 ]]; then
    sdk::log "ERR" "Verification completed with errors"
    exit $OVERALL_EXIT
  fi
fi

if [[ $HAS_FINDINGS -eq 1 ]]; then
  sdk::log "WRN" "Verification completed with warnings"
  exit 0
fi

sdk::log "INF" "Verification completed without critical errors"
exit 0
