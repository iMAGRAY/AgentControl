#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
LC_ALL=C.UTF-8

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BIN_DIR="$ROOT/scripts/bin"
LOG_DIR="$ROOT/reports/agents"
mkdir -p "$BIN_DIR" "$LOG_DIR"

log() {
  printf ' [INF] %s\n' "$1"
}

warn() {
  printf ' [WRN] %s\n' "$1" >&2
}

ensure_node() {
  if ! command -v node >/dev/null 2>&1; then
    warn "node не найден в PATH — codex CLI требует Node.js"
    return 1
  fi
  return 0
}

setup_codex() {
  local src_dir="$ROOT/vendor/codex/codex-cli"
  local script="$src_dir/bin/codex.js"
  if [[ ! -f "$script" ]]; then
    warn "codex CLI не найден в vendor/codex — обновите субмодуль"
    return 1
  fi
  if ensure_node; then
    pushd "$src_dir" >/dev/null
    if [[ -f package.json ]]; then
      if [[ ! -d node_modules ]]; then
        log "Устанавливаю зависимости codex-cli"
        npm install --prefer-offline --no-audit >/dev/null 2>&1 || warn "npm install codex-cli завершился с предупреждениями"
      fi
    fi
    popd >/dev/null
    cat <<'WRAP' > "$BIN_DIR/codex"
#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NODE_CMD="node"
SCRIPT="$ROOT_DIR/vendor/codex/codex-cli/bin/codex.js"
if [[ ! -f "$SCRIPT" ]]; then
  echo "codex CLI script не найден (ожидался $SCRIPT)" >&2
  exit 1
fi
exec "$NODE_CMD" "$SCRIPT" "$@"
WRAP
    chmod +x "$BIN_DIR/codex"
    log "codex CLI настроен: scripts/bin/codex"
    return 0
  fi
  return 1
}

setup_claude() {
  # Предпочитаем системный бинарь claude, иначе предоставляем заглушку.
  local target="$BIN_DIR/claude"
  if command -v claude >/dev/null 2>&1; then
    cat <<'WRAP' > "$target"
#!/usr/bin/env bash
exec claude "$@"
WRAP
    chmod +x "$target"
    log "claude CLI найден в системе и проксирован через scripts/bin/claude"
    return 0
  fi
  # Заглушка: отвечает эхо-сообщением, чтобы пайплайн не падал.
  cat <<'STUB' > "$target"
#!/usr/bin/env bash
set -Eeuo pipefail
PROMPT_FILE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --prompt|--input|-f)
      shift
      PROMPT_FILE="$1"
      ;;
    --prompt-file)
      shift
      PROMPT_FILE="$1"
      ;;
  esac
  shift || break
done
if [[ -n "$PROMPT_FILE" && -f "$PROMPT_FILE" ]]; then
  echo "[claude-stub] Ответ на основании файла $PROMPT_FILE"
  head -n 20 "$PROMPT_FILE" | sed 's/^/> /'
else
  echo "[claude-stub] CLI не найден. Установите официальный Anthropic Claude CLI и добавьте в PATH."
fi
STUB
  chmod +x "$target"
  warn "claude CLI не найден — создана заглушка scripts/bin/claude"
  return 0
}

setup_codex || warn "codex CLI не настроен"
setup_claude || warn "claude CLI не настроен"

SANDBOX_BIN="$BIN_DIR/sandbox_exec"
if [[ ! -f "$SANDBOX_BIN" ]]; then
  cat <<'SANDBOX' > "$SANDBOX_BIN"
#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
# Простая обёртка: если доступен bubblewrap, используем его для изоляции,
# иначе запускаем команду напрямую.
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
  log "sandbox_exec настроен"
fi

printf '%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$LOG_DIR/install.timestamp"
log "Установка CLI агентов завершена"
