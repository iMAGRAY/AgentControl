#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
LC_ALL=C.UTF-8

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib/common.sh"
VENV_DIR="$SDK_ROOT/.venv"
VENV_BIN="$VENV_DIR/bin"
SETUP_STATE_DIR="$SDK_ROOT/.sdk/setup"
mkdir -p "$SETUP_STATE_DIR"

sdk::log "INF" "Starting full dependency installation"

detect_pkg_manager() {
  if command -v apt-get >/dev/null 2>&1; then
    printf 'apt\n'
  elif command -v dnf >/dev/null 2>&1; then
    printf 'dnf\n'
  elif command -v pacman >/dev/null 2>&1; then
    printf 'pacman\n'
  elif command -v brew >/dev/null 2>&1; then
    printf 'brew\n'
  else
    printf ''
  fi
}

install_system_packages() {
  local manager packages=()
  manager="$(detect_pkg_manager)"
  if [[ -z "$manager" ]]; then
    sdk::log "WRN" "Unable to determine package manager. Skipping system package installation."
    return 0
  fi

  case "$manager" in
    apt)
      packages=(shellcheck python3-venv python3-pip golang-go)
      ;;
    dnf)
      packages=(ShellCheck python3-virtualenv python3-pip golang)
      ;;
    pacman)
      packages=(shellcheck python-virtualenv python-pip go)
      ;;
    brew)
      packages=(shellcheck go python)
      ;;
  esac

  if [[ ${#packages[@]} -eq 0 ]]; then
    sdk::log "WRN" "No packages to install for $manager"
    return 0
  fi

  local fingerprint hash_input
  hash_input=$(printf '%s\n' "$manager" "${packages[@]}")
  if command -v sha256sum >/dev/null 2>&1; then
    fingerprint=$(printf '%s' "$hash_input" | sha256sum | awk '{print $1}')
  elif command -v shasum >/dev/null 2>&1; then
    fingerprint=$(printf '%s' "$hash_input" | shasum -a 256 | awk '{print $1}')
  elif command -v md5sum >/dev/null 2>&1; then
    fingerprint=$(printf '%s' "$hash_input" | md5sum | awk '{print $1}')
  else
    fingerprint=$(printf '%s' "$hash_input" | cksum | awk '{print $1}')
  fi
  local sentinel="$SETUP_STATE_DIR/system-${manager}-${fingerprint}"
  if [[ -f "$sentinel" ]]; then
    sdk::log "INF" "System packages already installed (cache hit)."
    return 0
  fi

  local sudo_cmd=()
  if [[ $EUID -ne 0 ]]; then
    if command -v sudo >/dev/null 2>&1; then
      sudo_cmd=(sudo)
    else
      sdk::log "WRN" "sudo not available — skipping system package installation. Install manually: ${packages[*]}"
      return 0
    fi
  fi

  local pkg_list
  pkg_list=$(printf '%s ' "${packages[@]}")
  sdk::log "INF" "Installing system packages: ${pkg_list% }"
  case "$manager" in
    apt)
      "${sudo_cmd[@]}" apt-get update
      DEBIAN_FRONTEND=noninteractive "${sudo_cmd[@]}" apt-get install -y "${packages[@]}"
      ;;
    dnf)
      "${sudo_cmd[@]}" dnf install -y "${packages[@]}"
      ;;
    pacman)
      "${sudo_cmd[@]}" pacman -Sy --needed --noconfirm "${packages[@]}"
      ;;
    brew)
      brew install "${packages[@]}"
      ;;
  esac

  printf 'installed %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$sentinel"
}

bootstrap_venv() {
  local python_bin
  if [[ -x "$VENV_DIR/bin/python" ]]; then
    python_bin="$VENV_DIR/bin/python"
  else
    python_bin="$(command -v python3 || true)"
    if [[ -z "$python_bin" ]]; then
      sdk::die "python3 not found"
    fi
    sdk::log "INF" "Creating virtual environment in $VENV_DIR"
    if "$python_bin" -m venv --help 2>&1 | grep -q -- '--upgrade-deps'; then
      "$python_bin" -m venv --upgrade-deps "$VENV_DIR"
    else
      "$python_bin" -m venv "$VENV_DIR"
    fi
  fi

  sdk::log "INF" "Upgrading pip and dependencies"
  "$VENV_DIR/bin/pip" install --upgrade pip==24.2
  "$VENV_DIR/bin/pip" install --upgrade -r "$SDK_ROOT/requirements.txt"
}

install_reviewdog() {
  if ! command -v go >/dev/null 2>&1; then
    sdk::log "WRN" "go not found — skipping reviewdog installation"
    return 0
  fi
  if [[ -x "$VENV_BIN/reviewdog" ]]; then
    sdk::log "INF" "reviewdog already installed (cache hit)."
    return 0
  fi
  mkdir -p "$VENV_BIN"
  sdk::log "INF" "Installing reviewdog into $VENV_BIN"
  GOBIN="$VENV_BIN" GO111MODULE=on go install github.com/reviewdog/reviewdog/cmd/reviewdog@v0.15.0
}

install_system_packages
bootstrap_venv
install_reviewdog

if [[ ${SKIP_AGENT_INSTALL:-0} -ne 1 ]]; then
  sdk::log "INF" "Installing agent CLIs"
  if ! "$SDK_ROOT/scripts/agents/install.sh"; then
    sdk::log "WRN" "Agent CLI installation completed with warnings"
  fi
fi

sdk::log "INF" "Installation complete. Run 'agentcall doctor' to verify."
