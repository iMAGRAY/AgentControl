#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
LC_ALL=C.UTF-8

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib/common.sh"

VENV_PIP="$SDK_ROOT/.venv/bin/pip"
LOCK_FILE="$SDK_ROOT/requirements.lock"

if [[ ! -x "$VENV_PIP" ]]; then
  sdk::die "check-lock: отсутствует $VENV_PIP — выполните make setup"
fi

if [[ ! -f "$LOCK_FILE" ]]; then
  sdk::die "check-lock: отсутствует requirements.lock"
fi

TMP_FREEZE="$(mktemp)"
TMP_LOCK="$(mktemp)"
trap 'rm -f "$TMP_FREEZE" "$TMP_LOCK"' EXIT

"$VENV_PIP" freeze --exclude-editable --disable-pip-version-check | LC_ALL=C sort > "$TMP_FREEZE"
python3 - <<'PY' "$TMP_FREEZE"
import sys
from pathlib import Path

freeze_path = Path(sys.argv[1])
IGNORED = {"pip", "setuptools", "wheel", "pkg-resources", "distribute"}
entries = []
for raw in freeze_path.read_text(encoding="utf-8").splitlines():
    stripped = raw.strip()
    if not stripped or stripped.startswith("#"):
        continue
    if "==" in stripped:
        name, version = stripped.split("==", 1)
        base_name = name.strip()
        if base_name.lower() in IGNORED:
            continue
        norm_name = base_name.replace("_", "-").replace(".", "-").lower()
        entry = f"{norm_name}=={version.strip()}"
    elif " @ " in stripped:
        name, rest = stripped.split(" @ ", 1)
        base_name = name.strip()
        if base_name.lower() in IGNORED:
            continue
        norm_name = base_name.replace("_", "-").replace(".", "-").lower()
        entry = f"{norm_name} @ {rest.strip()}"
    else:
        base_name = stripped
        if base_name.lower() in IGNORED:
            continue
        entry = base_name.replace("_", "-").replace(".", "-").lower()
    entries.append(entry)
entries.sort()
freeze_path.write_text("\n".join(entries) + "\n", encoding="utf-8")
PY
python3 - <<'PY' "$LOCK_FILE" "$TMP_LOCK"
import sys
from pathlib import Path

lock_path = Path(sys.argv[1])
output_path = Path(sys.argv[2])
IGNORED = {"pip", "setuptools", "wheel", "pkg-resources", "distribute"}
entries = []
for raw in lock_path.read_text(encoding="utf-8").splitlines():
    stripped = raw.strip()
    if not stripped or stripped.startswith("#"):
        continue
    if "==" in stripped:
        name, version = stripped.split("==", 1)
        base_name = name.strip()
        if base_name.lower() in IGNORED:
            continue
        norm_name = base_name.replace("_", "-").replace(".", "-").lower()
        entry = f"{norm_name}=={version.strip()}"
    elif " @ " in stripped:
        name, rest = stripped.split(" @ ", 1)
        base_name = name.strip()
        if base_name.lower() in IGNORED:
            continue
        norm_name = base_name.replace("_", "-").replace(".", "-").lower()
        entry = f"{norm_name} @ {rest.strip()}"
    else:
        base_name = stripped
        if base_name.lower() in IGNORED:
            continue
        entry = base_name.replace("_", "-").replace(".", "-").lower()
    entries.append(entry)
entries.sort()
output_path.write_text("\n".join(entries) + "\n", encoding="utf-8")
PY

if ! cmp -s "$TMP_FREEZE" "$TMP_LOCK"; then
  sdk::log "ERR" "Зависимости не совпадают с requirements.lock"
  diff -u "$TMP_LOCK" "$TMP_FREEZE" || true
  sdk::die "Обновите lock-файл: scripts/update-lock.sh"
fi

sdk::log "INF" "Lock-файл проверен: зависимости совпадают"

SBOM_PATH="$SDK_ROOT/sbom/python.json"
if [[ -f "$SBOM_PATH" ]]; then
  if ! "$SDK_ROOT/.venv/bin/python" "$SCRIPT_DIR/generate-sbom.py" --check --output "$SBOM_PATH"; then
    sdk::die "SBOM не соответствует текущей среде — запустите scripts/update-lock.sh"
  fi
else
  sdk::log "WRN" "SBOM отсутствует (sbom/python.json)"
fi
