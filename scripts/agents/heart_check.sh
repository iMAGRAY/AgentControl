#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
LC_ALL=C.UTF-8

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HEART_MANIFEST="$ROOT/context/heart/manifest.json"
HEART_CMD="$ROOT/scripts/agents/heart.sh"
MAX_AGE_SEC=${HEART_MAX_AGE_SEC:-86400}

if [[ ! -f "$HEART_MANIFEST" ]]; then
  echo "[Heart] manifest not found — running heart sync" >&2
  "$HEART_CMD" sync
  exit 0
fi

NOW=$(date -u +%s)
STAMP=$(python3 - <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
path = Path(sys.argv[1])
data = json.loads(path.read_text(encoding='utf-8'))
value = data.get('generated_at')
if not value:
    print(0)
    raise SystemExit
try:
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
except Exception:
    print(0)
    raise SystemExit
print(int(dt.replace(tzinfo=timezone.utc).timestamp()))
PY
"$HEART_MANIFEST")
if [[ "$STAMP" -eq 0 ]]; then
  echo "[Heart] manifest timestamp unreadable — running sync" >&2
  "$HEART_CMD" sync
  exit 0
fi
AGE=$(( NOW - STAMP ))
if (( AGE > MAX_AGE_SEC )); then
  echo "[Heart] manifest older than $MAX_AGE_SEC seconds ($AGE) — running sync" >&2
  "$HEART_CMD" sync
fi

exit 0
