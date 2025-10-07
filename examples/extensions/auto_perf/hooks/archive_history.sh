#!/usr/bin/env bash
set -Eeuo pipefail

ARCHIVE_DIR="${1:-reports/perf/history/archive}"
mkdir -p "$ARCHIVE_DIR"
find reports/perf/history -maxdepth 1 -name '*.jsonl' -exec cp {} "$ARCHIVE_DIR" \;
