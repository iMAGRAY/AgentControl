#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'
	'
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CMD="$1"
shift || true
case "$CMD" in
  status|verify|fix|review|ship|doctor|agents|runtime|mission|docs|mcp)
    agentcall "$CMD" "$ROOT_DIR" "$@"
    ;;
  auto)
    sub="${1:-docs}"
    shift || true
    agentcall auto "$ROOT_DIR" "$sub" "$@"
    ;;
  *)
    agentcall "$CMD" "$@"
    ;;
esac
