#!/usr/bin/env bash
# Common utilities for the AgentControl Universal Agent SDK.

SDK_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly SDK_ROOT

sdk::log() {
  local level="$1"; shift
  printf ' [%s] %s\n' "$level" "$*"
}

sdk::die() {
  sdk::log "ERR" "$*"
  exit 1
}

sdk::load_commands() {
  local file="$SDK_ROOT/config/commands.sh"
  if [[ -f "$file" ]]; then
    # shellcheck disable=SC1090
    source "$file"
  else
    SDK_DEV_COMMANDS=()
    SDK_VERIFY_COMMANDS=()
    SDK_FIX_COMMANDS=()
    SDK_SHIP_COMMANDS=()
    SDK_REVIEW_LINTERS=()
    SDK_TEST_COMMAND=""
    SDK_COVERAGE_FILE=""
    return
  fi

  if ! declare -p SDK_DEV_COMMANDS >/dev/null 2>&1; then SDK_DEV_COMMANDS=(); fi
  if ! declare -p SDK_VERIFY_COMMANDS >/dev/null 2>&1; then SDK_VERIFY_COMMANDS=(); fi
  if ! declare -p SDK_FIX_COMMANDS >/dev/null 2>&1; then SDK_FIX_COMMANDS=(); fi
  if ! declare -p SDK_SHIP_COMMANDS >/dev/null 2>&1; then SDK_SHIP_COMMANDS=(); fi
  if ! declare -p SDK_REVIEW_LINTERS >/dev/null 2>&1; then SDK_REVIEW_LINTERS=(); fi
  if [[ -z "${SDK_TEST_COMMAND:-}" ]]; then SDK_TEST_COMMAND=""; fi
  if [[ -z "${SDK_COVERAGE_FILE:-}" ]]; then SDK_COVERAGE_FILE=""; fi

  sdk::strip_placeholder_array SDK_DEV_COMMANDS
  sdk::strip_placeholder_array SDK_VERIFY_COMMANDS
  sdk::strip_placeholder_array SDK_FIX_COMMANDS
  sdk::strip_placeholder_array SDK_SHIP_COMMANDS
  sdk::strip_placeholder_array SDK_REVIEW_LINTERS
  sdk::strip_placeholder_scalar SDK_TEST_COMMAND
  sdk::strip_placeholder_scalar SDK_COVERAGE_FILE

  sdk::auto_detect_commands
  sdk::load_automation_hooks
}

sdk::strip_placeholder_array() {
  local -n arr_ref="$1"
  if [[ ${#arr_ref[@]} -eq 1 ]]; then
    case "${arr_ref[0]}" in
      "echo"*"configure"* ) arr_ref=() ;;
    esac
  fi
}

sdk::strip_placeholder_scalar() {
  local var_name="$1"
  local value="${!var_name:-}"
  if [[ "$value" == echo*configure* ]]; then
    printf -v "$var_name" '%s' ""
  fi
}

sdk::auto_detect_commands() {
  local snippet
  snippet=$(python3 -m scripts.lib.auto_detect "$SDK_ROOT" 2>/dev/null || true)
  if [[ -n "$snippet" ]]; then
    eval "$snippet"
  fi
}

sdk::ensure_array_value() {
  local array_name="$1"
  local value="$2"
  local -n ref="$array_name"
  local item
  for item in "${ref[@]}"; do
    if [[ "$item" == "$value" ]]; then
      return 0
    fi
  done
  ref+=("$value")
}

sdk::load_automation_hooks() {
  local automation_file="$SDK_ROOT/config/automation.sh"
  if [[ -f "$automation_file" ]]; then
    # shellcheck disable=SC1090
    source "$automation_file"
  fi
}

sdk::print_quickref() {
  local agents_file="$SDK_ROOT/AGENTS.md"
  if [[ -f "$agents_file" ]]; then
    sdk::log "INF" "AGENTS.md quick reference (first 40 lines):"
    sed -n '1,40p' "$agents_file"
  else
    sdk::log "WRN" "AGENTS.md is missing — create the project governance document."
  fi
}

sdk::run_command_group() {
  local title="$1"
  local array_name="$2"
  local -n commands_ref="$array_name"

  sdk::log "INF" "Running command group: $title"
  if [[ ${#commands_ref[@]} -eq 0 ]]; then
    sdk::log "INF" "No commands configured — skipping"
    return 0
  fi

  local i=0
  for cmd in "${commands_ref[@]}"; do
    i=$((i + 1))
    sdk::log "RUN" "($i/${#commands_ref[@]}) $cmd"
    eval "$cmd"
  done
}

sdk::command_exists() {
  command -v "$1" >/dev/null 2>&1
}

sdk::ensure_file() {
  local rel="$1"
  local path="$SDK_ROOT/$rel"
  if [[ ! -f "$path" ]]; then
    sdk::die "File $rel is required for the SDK."
  fi
  sdk::log "INF" "Detected $rel"
}

sdk::run_shellcheck_if_available() {
  if ! sdk::command_exists shellcheck; then
    sdk::log "WRN" "shellcheck is not installed — skipping"
    return 0
  fi

  shopt -s nullglob
  local files=("$SDK_ROOT"/scripts/*.sh "$SDK_ROOT"/scripts/lib/*.sh)
  shopt -u nullglob

  if [[ ${#files[@]} -eq 0 ]]; then
    sdk::log "INF" "Shellcheck: nothing to lint"
    return 0
  fi

  sdk::log "INF" "Shellcheck: ${#files[@]} files"
  shellcheck "${files[@]}"
}

sdk::root() {
  printf '%s\n' "$SDK_ROOT"
}
