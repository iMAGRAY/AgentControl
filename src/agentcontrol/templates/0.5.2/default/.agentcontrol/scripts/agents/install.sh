#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
LC_ALL=C.UTF-8

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BIN_DIR="$ROOT/scripts/bin"
LOG_DIR="$ROOT/reports/agents"
CODEX_SRC="$ROOT/vendor/codex/codex-rs"
CLAUDE_DIST="$BIN_DIR/claude-dist"
mkdir -p "$BIN_DIR" "$LOG_DIR"

log() {
  printf ' [INF] %s\n' "$1"
}

warn() {
  printf ' [WRN] %s\n' "$1" >&2
}

ensure_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    warn "command required '$1'"
    return 1
  fi
  return 0
}

setup_codex() {
  if [[ ! -d "$CODEX_SRC" ]]; then
    warn "codex-rs not found in vendor/codex — run git submodule update"
    return 1
  fi
  ensure_cmd cargo || return 1
  local build_log
  build_log="$(mktemp -t codex-build.XXXXXX.log)"
  log "Building Codex CLI (cargo build --release -p codex-cli)"
  if ! cargo build --manifest-path "$CODEX_SRC/Cargo.toml" --release --locked -p codex-cli >"$build_log" 2>&1; then
    warn "cargo build failed; log: $build_log"
    return 1
  fi
  local built_bin="$CODEX_SRC/target/release/codex"
  if [[ ! -f "$built_bin" ]]; then
    warn "codex binary not found after build"
    return 1
  fi
  install -m 0755 "$built_bin" "$BIN_DIR/codex.bin"
  cat <<'WRAP' > "$BIN_DIR/codex"
#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BIN="$ROOT_DIR/scripts/bin/codex.bin"
CODEX_HOME_DEFAULT="$ROOT_DIR/state/agents/codex-home"
if [[ ! -x "$BIN" ]]; then
  echo "codex CLI not installed — run agentcall agents install" >&2
  exit 1
fi
if [[ -z "${CODEX_HOME:-}" ]]; then
  CODEX_HOME="$CODEX_HOME_DEFAULT"
fi
mkdir -p "$CODEX_HOME"
export CODEX_HOME
exec "$BIN" "$@"
WRAP
  chmod +x "$BIN_DIR/codex"
  log "codex CLI built and installed: scripts/bin/codex"
  return 0
}

setup_claude() {
  local target="$BIN_DIR/claude"

  ensure_cmd node || return 1
  ensure_cmd npm || return 1

  rm -rf "$CLAUDE_DIST"
  mkdir -p "$CLAUDE_DIST"
  local install_log
  install_log="$(mktemp -t claude-install.XXXXXX.log)"
  log "Installing @anthropic-ai/claude-code into sandbox"
  if ! npm install --prefix "$CLAUDE_DIST" --no-save --no-package-lock @anthropic-ai/claude-code >"$install_log" 2>&1; then
    warn "npm install claude-code failed; log: $install_log"
    if command -v claude >/dev/null 2>&1; then
      warn "falling back to system claude"
      cat <<'WRAP' > "$target"
#!/usr/bin/env bash
exec claude "$@"
WRAP
      chmod +x "$target"
      return 0
    fi
    return 1
  fi
  local entry="$CLAUDE_DIST/node_modules/@anthropic-ai/claude-code/cli.js"
  if [[ ! -f "$entry" ]]; then
    warn "npm installation finished without cli.js"
    if command -v claude >/dev/null 2>&1; then
      warn "falling back to system claude"
      cat <<'WRAP' > "$target"
#!/usr/bin/env bash
exec claude "$@"
WRAP
      chmod +x "$target"
      return 0
    fi
    return 1
  fi
  cat <<'WRAP' > "$target"
#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DIST_DIR="$ROOT_DIR/scripts/bin/claude-dist"
ENTRY="$DIST_DIR/node_modules/@anthropic-ai/claude-code/cli.js"
CONFIG_DIR_DEFAULT="$ROOT_DIR/state/agents/claude-config"
if [[ ! -f "$ENTRY" ]]; then
  echo "claude CLI not installed — run agentcall agents install" >&2
  exit 1
fi
if [[ -z "${CLAUDE_CONFIG_DIR:-}" ]]; then
  CLAUDE_CONFIG_DIR="$CONFIG_DIR_DEFAULT"
fi
mkdir -p "$CLAUDE_CONFIG_DIR"
export CLAUDE_CONFIG_DIR
exec node "$ENTRY" "$@"
WRAP
  chmod +x "$target"
  log "claude CLI installed locally: scripts/bin/claude"
  return 0
}

setup_codex || warn "codex CLI not configured"
setup_claude || warn "claude CLI not configured"

SANDBOX_BIN="$BIN_DIR/sandbox_exec"
if [[ ! -f "$SANDBOX_BIN" ]]; then
  cat <<'SANDBOX' > "$SANDBOX_BIN"
#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
# Simple wrapper: if bubblewrap is available, use it for isolation,
# otherwise run the command directly.
if command -v bwrap >/dev/null 2>&1; then
  WORK_DIR="${SANDBOX_WORK:-/tmp/sandbox-work}"
  mkdir -p "$WORK_DIR"
  exec bwrap \
    --dev-bind / / \
    --proc /proc \
    --tmpfs /tmp \
    --dir /tmp/work \
    --chdir "$PWD" \
    "$@"
else
  exec "$@"
fi
SANDBOX
  chmod +x "$SANDBOX_BIN"
  log "sandbox_exec configured"
fi

printf '%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$LOG_DIR/install.timestamp"
log "Agent CLI installation completed"
