#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
LC_ALL=C.UTF-8

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MANIFEST="$ROOT/architecture/manifest.yaml"
EDIT_MANIFEST="$ROOT/architecture/manifest.edit.yaml"

usage() {
  cat <<USAGE
Usage: agentcall run arch-edit | agentcall run arch-apply | scripts/arch.sh <edit|apply>
USAGE
}

command="${1:-}" || true
case "$command" in
  edit)
    if [[ -f "$EDIT_MANIFEST" ]]; then
      echo "File manifest.edit.yaml already exists: $EDIT_MANIFEST" >&2
    else
      cp "$MANIFEST" "$EDIT_MANIFEST"
      echo "Copied manifest.yaml → manifest.edit.yaml. Edit manifest.edit.yaml then run agentcall run arch-apply." >&2
    fi
    ;;
  apply)
    if [[ ! -f "$EDIT_MANIFEST" ]]; then
      echo "architecture/manifest.edit.yaml not found. Run agentcall run arch-edit." >&2
      exit 1
    fi
    python3 - <<'PY'
import datetime as dt
from pathlib import Path
import yaml

root = Path(__file__).resolve().parents[1]
manifest_path = root / "architecture" / "manifest.yaml"
edit_path = root / "architecture" / "manifest.edit.yaml"
with edit_path.open("r", encoding="utf-8") as fh:
    data = yaml.safe_load(fh)
if not isinstance(data, dict):
    raise SystemExit("manifest.edit.yaml must contain a YAML mapping")
now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
data["updated_at"] = now
if "program" in data and "meta" in data["program"]:
    data["program"]["meta"]["updated_at"] = now
with manifest_path.open("w", encoding="utf-8") as fh:
    yaml.safe_dump(data, fh, sort_keys=False, allow_unicode=True)
edit_path.unlink()
PY
    "$SCRIPT_DIR/sync-architecture.sh"
    ;;
  "")
    usage
    exit 1
    ;;
  *)
    usage
    exit 1
    ;;
esac
