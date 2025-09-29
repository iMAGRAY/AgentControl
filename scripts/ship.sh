#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
LC_ALL=C.UTF-8

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib/common.sh"

sdk::load_commands

sdk::log "INF" "Запуск make verify перед ship"
"$SDK_ROOT/scripts/verify.sh"

sdk::run_command_group "ship" SDK_SHIP_COMMANDS
