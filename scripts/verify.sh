#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
LC_ALL=C.UTF-8

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib/common.sh"

sdk::load_commands

sdk::log "INF" "Синхронизация roadmap"
"$SDK_ROOT/scripts/sync-roadmap.sh" >/dev/null || sdk::log "WRN" "sync-roadmap завершился с предупреждением"

sdk::log "INF" "Базовые проверки структуры"
sdk::ensure_file "AGENTS.md"
sdk::ensure_file "todo.machine.md"
sdk::ensure_file ".editorconfig"
sdk::ensure_file ".codexignore"
sdk::ensure_file "data/tasks.board.json"

if ! grep -q '^## Program' "$SDK_ROOT/todo.machine.md"; then
  sdk::die "todo.machine.md должен содержать раздел '## Program'"
fi
if ! grep -q '^## Epics' "$SDK_ROOT/todo.machine.md"; then
  sdk::die "todo.machine.md должен содержать раздел '## Epics'"
fi
if ! grep -q '^## Big Tasks' "$SDK_ROOT/todo.machine.md"; then
  sdk::die "todo.machine.md должен содержать раздел '## Big Tasks'"
fi

sdk::run_shellcheck_if_available

sdk::log "INF" "Валидация дорожной карты"
"$SDK_ROOT/scripts/roadmap-status.sh" compact >/dev/null

sdk::log "INF" "Валидация доски задач"
"$SDK_ROOT/scripts/task.sh" validate >/dev/null

sdk::run_command_group "verify" SDK_VERIFY_COMMANDS
