#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'
LC_ALL=C.UTF-8

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SDK_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
TEST_ROOT="$SDK_ROOT/.test_place"
PROJECT_DIR="$TEST_ROOT/project"
VENV_DIR="$TEST_ROOT/.venv"
STATUS_REPORT="$SDK_ROOT/reports/test_place_status.json"

export AGENTCONTROL_HOME="$TEST_ROOT/home"
mkdir -p "$AGENTCONTROL_HOME"
export AGENTCONTROL_STATE_DIR="$TEST_ROOT/state"
mkdir -p "$AGENTCONTROL_STATE_DIR"

rm -rf "$TEST_ROOT"
mkdir -p "$PROJECT_DIR"

python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --upgrade pip >/dev/null
PIP_NO_WARN_SCRIPT_LOCATION=0 "$VENV_DIR/bin/pip" install --quiet "$SDK_ROOT" >/dev/null

pushd "$PROJECT_DIR" >/dev/null
"$VENV_DIR/bin/python" -m agentcontrol.cli.main quickstart --template default --no-verify . >/dev/null
"$VENV_DIR/bin/python" -m agentcontrol.cli.main extension --path . init sandbox_ext >/dev/null
"$VENV_DIR/bin/python" -m agentcontrol.cli.main extension --path . list --json >/dev/null
"$VENV_DIR/bin/python" -m agentcontrol.cli.main extension --path . lint --json >/dev/null
EXT_PUBLISH_JSON=$("$VENV_DIR/bin/python" -m agentcontrol.cli.main extension --path . publish --dry-run --json)
python3 - "$EXT_PUBLISH_JSON" <<'PY'
import json
import pathlib
import sys

payload = json.loads(sys.argv[1])
path = pathlib.Path(payload["path"]).expanduser()
if not path.exists():
    raise SystemExit(f"extension catalog not generated: {path}")
PY
"$VENV_DIR/bin/python" -m agentcontrol.cli.main info --json >"$STATUS_REPORT"
"$VENV_DIR/bin/python" -m agentcontrol.cli.main mission analytics --json >/dev/null
export PROJECT_DIR="$PROJECT_DIR"
python3 <<'PY_TASKS'
import base64, json, os, pathlib
project_dir = pathlib.Path(os.environ['PROJECT_DIR'])
board_path = project_dir / 'data' / 'tasks.board.json'
board_path.parent.mkdir(parents=True, exist_ok=True)
if not board_path.exists():
    board_payload = {
        'version': '0.1.0',
        'updated_at': '2025-10-01T00:00:00Z',
        'tasks': [
            {'id': 'TASK-1', 'title': 'Bootstrap docs', 'status': 'open'},
            {'id': 'TASK-2', 'title': 'Legacy cleanup', 'status': 'done'},
        ],
    }
    board_path.write_text(json.dumps(board_payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
provider_dir = project_dir / 'state' / 'provider'
provider_dir.mkdir(parents=True, exist_ok=True)
payload = {
    'tasks': [
        {'id': 'TASK-1', 'title': 'Bootstrap docs', 'status': 'done'},
        {'id': 'TASK-3', 'title': 'Telemetry wiring', 'status': 'open'},
    ]
}
key = 'demo-key'.encode('utf-8')
raw = json.dumps(payload, ensure_ascii=False, indent=2).encode('utf-8')
cipher = bytes(b ^ key[i % len(key)] for i, b in enumerate(raw))
(provider_dir / 'tasks_snapshot.enc').write_text(base64.b64encode(cipher).decode('utf-8'), encoding='utf-8')
config_dir = project_dir / 'config'
config_dir.mkdir(parents=True, exist_ok=True)
config_payload = {
    'type': 'file',
    'options': {
        'path': 'state/provider/tasks_snapshot.enc',
        'encryption': {'mode': 'xor', 'key': 'demo-key'},
    },
}
(config_dir / 'tasks.provider.json').write_text(json.dumps(config_payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
PY_TASKS
"$VENV_DIR/bin/python" -m agentcontrol.cli.main tasks sync . --apply >/dev/null
"$VENV_DIR/bin/python" -m agentcontrol.cli.main tasks sync . --json >/dev/null
test -f "reports/mission-activity.json"
popd >/dev/null

rm -rf "$TEST_ROOT"
