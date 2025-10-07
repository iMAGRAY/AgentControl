#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
LC_ALL=C.UTF-8

command -v pipx >/dev/null 2>&1 || {
  echo "[BOOT] pipx not found — installing via python -m pip" >&2
  python3 -m pip install --user pipx
  python3 -m pipx ensurepath || true
  export PATH="$HOME/.local/bin:$PATH"
}

if command -v agentcall >/dev/null 2>&1; then
  echo "[BOOT] agentcall already installed"
else
  echo "[BOOT] Installing agentcontrol via pipx"
  pipx install agentcontrol --force
fi

agentcall doctor || echo "[BOOT] agentcall doctor finished with status $?, review output above"
