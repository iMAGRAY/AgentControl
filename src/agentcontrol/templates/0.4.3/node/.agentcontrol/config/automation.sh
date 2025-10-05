#!/usr/bin/env bash
# shellcheck shell=bash

# Automation hooks for AgentControl verify pipeline.
# Source this file to append project-wide commands that should run during
# `agentcall verify`. Commands are appended only once per shell session.

set -Eeuo pipefail

if ! declare -p SDK_VERIFY_COMMANDS >/dev/null 2>&1; then
  SDK_VERIFY_COMMANDS=()
fi

AUTOMATION_REPORTS_DIR="${AUTOMATION_REPORTS_DIR:-$SDK_ROOT/reports/automation}"
mkdir -p "$AUTOMATION_REPORTS_DIR"

sdk::ensure_array_value SDK_VERIFY_COMMANDS \
  "agentcall docs diff --json > \"${AUTOMATION_REPORTS_DIR}/docs-diff.json\""

sdk::ensure_array_value SDK_VERIFY_COMMANDS \
  "agentcall mission summary --json --timeline-limit 20 > \"${AUTOMATION_REPORTS_DIR}/mission-summary.json\""

sdk::ensure_array_value SDK_VERIFY_COMMANDS \
  "agentcall mcp status --json > \"${AUTOMATION_REPORTS_DIR}/mcp-status.json\" || true"
