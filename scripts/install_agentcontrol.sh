#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
LC_ALL=C.UTF-8

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TARGET="${AGENTCONTROL_HOME:-$HOME/.agentcontrol}"

VERSION=$(python3 - <<'PY'
import pathlib, re
root = pathlib.Path(__file__).resolve().parents[1]
init_text = (root / "src" / "agentcontrol" / "__init__.py").read_text()
match = re.search(r'__version__ = "([^"]+)"', init_text)
print(match.group(1) if match else "0.0.0")
PY
)

SOURCE_DIR="$ROOT/src/agentcontrol/templates/$VERSION"
if [[ ! -d "$SOURCE_DIR" ]]; then
  fallback=$(python3 - <<'PY'
import pathlib
root = pathlib.Path(__file__).resolve().parents[1]
dirpath = root / "src" / "agentcontrol" / "templates"
dirs = sorted([p.name for p in dirpath.iterdir() if p.is_dir()])
print(dirs[-1] if dirs else "")
PY
)
  if [[ -z "$fallback" ]]; then
    echo "[install] no templates found" >&2
    exit 1
  fi
  SOURCE_DIR="$ROOT/src/agentcontrol/templates/$fallback"
fi

DEST_DIR="$TARGET/templates/stable/$VERSION"
mkdir -p "$DEST_DIR"
rsync -a --delete "$SOURCE_DIR/" "$DEST_DIR/"

export DEST_DIR
python3 - <<'PY'
import hashlib
import os
from pathlib import Path

dest = Path(os.environ['DEST_DIR']).resolve()
for entry in dest.iterdir():
    if entry.is_dir():
        digest = hashlib.sha256()
        for path in sorted(entry.rglob('*')):
            if path.is_file() and path.name != 'template.sha256':
                digest.update(path.relative_to(entry).as_posix().encode('utf-8'))
                digest.update(path.read_bytes())
        (entry / 'template.sha256').write_text(digest.hexdigest() + '\n', encoding='utf-8')
print(f"Templates staged to {dest}")
PY
