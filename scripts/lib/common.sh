#!/usr/bin/env bash
# Общие утилиты SDK GPT-5 Codex.

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
  fi
}

sdk::print_quickref() {
  local agents_file="$SDK_ROOT/AGENTS.md"
  if [[ -f "$agents_file" ]]; then
    sdk::log "INF" "AGENTS.md quickref (первые 40 строк):"
    sed -n '1,40p' "$agents_file"
  else
    sdk::log "WRN" "AGENTS.md отсутствует — создайте документ управления проектом."
  fi
}

sdk::run_command_group() {
  local title="$1"
  local array_name="$2"
  local -n commands_ref="$array_name"

  sdk::log "INF" "Запуск набора команд: $title"
  if [[ ${#commands_ref[@]} -eq 0 ]]; then
    sdk::log "INF" "Команды не заданы — пропуск"
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
    sdk::die "Файл $rel обязателен для SDK."
  fi
  sdk::log "INF" "Обнаружен $rel"
}

sdk::run_shellcheck_if_available() {
  if ! sdk::command_exists shellcheck; then
    sdk::log "WRN" "shellcheck не установлен — шаг проверки пропущен"
    return 0
  fi

  shopt -s nullglob
  local files=("$SDK_ROOT"/scripts/*.sh "$SDK_ROOT"/scripts/lib/*.sh)
  shopt -u nullglob

  if [[ ${#files[@]} -eq 0 ]]; then
    sdk::log "INF" "Shellcheck: нечего проверять"
    return 0
  fi

  sdk::log "INF" "Shellcheck: ${#files[@]} файлов"
  shellcheck "${files[@]}"
}

sdk::root() {
  printf '%s\n' "$SDK_ROOT"
}
