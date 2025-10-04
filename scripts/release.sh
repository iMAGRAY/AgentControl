#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
LC_ALL=C.UTF-8

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="$PROJECT_ROOT/dist"
if [[ -z "${PYTHON:-}" ]]; then
  if [[ -x "$PROJECT_ROOT/.venv/bin/python" ]]; then
    PYTHON="$PROJECT_ROOT/.venv/bin/python"
  else
    PYTHON="python3"
  fi
fi

if [[ "$PYTHON" == "python3" && ! -x "$PROJECT_ROOT/.venv/bin/python" ]]; then
  log "Creating local virtualenv for release"
  python3 -m venv "$PROJECT_ROOT/.venv"
  PYTHON="$PROJECT_ROOT/.venv/bin/python"
  "$PYTHON" -m pip install --upgrade pip >/dev/null
fi

export DIST_DIR

log() {
  printf '[REL] %s\n' "$1"
}

log "Ensuring build toolchain"
if ! $PYTHON -c "import build" >/dev/null 2>&1; then
  log "Installing build module via pip"
  $PYTHON -m pip install build >/dev/null
fi
if ! $PYTHON -c "import twine" >/dev/null 2>&1; then
  log "Installing twine"
  $PYTHON -m pip install twine >/dev/null
fi

log "Cleaning previous build artefacts"
rm -rf "$DIST_DIR" "$PROJECT_ROOT"/*.egg-info

log "Building wheel and sdist via python -m build"
$PYTHON -m build

VERSION=$(PYTHONPATH="$PROJECT_ROOT/src" $PYTHON - <<'PY'
from agentcontrol import __version__
print(__version__)
PY
)
log "Validating distribution"
$PYTHON -m twine check "$DIST_DIR"/*
$PYTHON -m pip install --force-reinstall --no-deps "$DIST_DIR"/*.whl >/dev/null

CHANGELOG="$PROJECT_ROOT/docs/changes.md"
if [[ ! -f "$CHANGELOG" ]]; then
  log "ERROR: docs/changes.md missing"
  exit 1
fi
if ! grep -q "## ${VERSION}" "$CHANGELOG"; then
  log "ERROR: docs/changes.md missing entry for version ${VERSION}"
  exit 1
fi

log "Calculating checksums"
SHA_FILE="$DIST_DIR/agentcontrol.sha256"
: > "$SHA_FILE"
for artifact in "$DIST_DIR"/*; do
  sha256sum "$artifact" >> "$SHA_FILE"
  log "sha256 $(basename "$artifact") => $(sha256sum "$artifact" | cut -d' ' -f1)"

done

log "Writing release manifest"
MANIFEST="$DIST_DIR/release-manifest.json"
cat > "$MANIFEST" <<JSON
{
  "package": "agentcontrol",
  "version": "${VERSION}",
  "artifacts": $(
    python3 - <<'PY'
import json
import os
from pathlib import Path

dist = Path(os.environ["DIST_DIR"])
entries = []
for artifact in sorted(dist.iterdir()):
    entries.append({
        "name": artifact.name,
        "size": artifact.stat().st_size,
    })
print(json.dumps(entries, indent=2))
PY
  ),
  "checksums": "$(basename "$SHA_FILE")"
}
JSON

log "Release artifacts prepared in $DIST_DIR"
