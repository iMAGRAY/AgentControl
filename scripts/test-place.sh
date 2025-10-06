#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
LC_ALL=C.UTF-8

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SDK_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
TEST_ROOT="$SDK_ROOT/.test_place"
PROJECT_DIR="$TEST_ROOT/project"
VENV_DIR="$TEST_ROOT/.venv"
STATUS_REPORT="$SDK_ROOT/reports/test_place_status.json"

rm -rf "$TEST_ROOT"
mkdir -p "$PROJECT_DIR"

python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --upgrade pip >/dev/null
PIP_NO_WARN_SCRIPT_LOCATION=0 "$VENV_DIR/bin/pip" install --quiet "$SDK_ROOT" >/dev/null

pushd "$PROJECT_DIR" >/dev/null
"$VENV_DIR/bin/python" -m agentcontrol.cli.main init --template default . >/dev/null
"$VENV_DIR/bin/python" -m agentcontrol.cli.main info --json >"$STATUS_REPORT"
popd >/dev/null

rm -rf "$TEST_ROOT"
