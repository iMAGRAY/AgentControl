from __future__ import annotations

import json
import stat
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from scripts.agents import auth, logout


def make_executable(path: Path) -> None:
    mode = path.stat().st_mode
    path.chmod(mode | stat.S_IEXEC)


def test_agents_auth_copies_credentials(tmp_path, monkeypatch):
    cli = tmp_path / "sample_cli.sh"
    creds_src = tmp_path / "creds"
    cli.write_text(
        """#!/usr/bin/env bash
set -Eeuo pipefail
mkdir -p \"${AGENT_AUTH_DIR}\"
printf '{"token":"abc123"}\n' > \"${AGENT_AUTH_DIR}/token.json\"
""",
        encoding="utf-8",
    )
    make_executable(cli)
    config_path = tmp_path / "agents.json"
    config = {
        "agents": {
            "sample": {
                "auth_command": [str(cli)],
                "auth_env": {"AGENT_AUTH_DIR": str(creds_src)},
                "credentials_paths": [str(creds_src / "token.json")],
            }
        }
    }
    config_path.write_text(json.dumps(config), encoding="utf-8")
    state_dir = tmp_path / "state"
    monkeypatch.setenv(auth.CONFIG_ENV_KEY, str(config_path))
    monkeypatch.setenv(auth.STATE_ENV_KEY, str(state_dir))

    exit_code = auth.main()
    assert exit_code == 0

    state_file = state_dir / auth.STATE_FILENAME
    data = json.loads(state_file.read_text(encoding="utf-8"))
    entry = data["agents"]["sample"]
    assert entry["status"] == "ok"
    stored_paths = entry["stored_paths"]
    assert stored_paths, "ожидался хотя бы один сохранённый артефакт"
    stored_file = Path(stored_paths[0])
    assert stored_file.exists()
    assert stored_file.read_text(encoding="utf-8").strip() == '{"token":"abc123"}'


def test_agents_auth_handles_missing_command(tmp_path, monkeypatch):
    config_path = tmp_path / "agents.json"
    config = {
        "agents": {
            "ghost": {
                "auth_command": [str(tmp_path / "missing-cli")],
            }
        }
    }
    config_path.write_text(json.dumps(config), encoding="utf-8")
    monkeypatch.setenv(auth.CONFIG_ENV_KEY, str(config_path))
    monkeypatch.setenv(auth.STATE_ENV_KEY, str(tmp_path / "state"))

    exit_code = auth.main()
    assert exit_code == 0
    state_file = Path(tmp_path / "state" / auth.STATE_FILENAME)
    data = json.loads(state_file.read_text(encoding="utf-8"))
    entry = data["agents"]["ghost"]
    assert entry["status"] == "skipped"
    assert "stored_paths" in entry and entry["stored_paths"] == []


def test_agents_auth_auto_exit(monkeypatch, tmp_path):
    cli = tmp_path / "auto_cli.sh"
    token_src = tmp_path / "token.json"
    cli.write_text(
        """#!/usr/bin/env bash
set -Eeuo pipefail
printf 'Successfully logged in\n'
sleep 5
""",
        encoding="utf-8",
    )
    make_executable(cli)
    token_src.write_text("{}\n", encoding="utf-8")
    config_path = tmp_path / "agents.json"
    config = {
        "agents": {
            "auto": {
                "auth_command": [str(cli)],
                "auth_auto_exit": True,
                "auth_auto_exit_trigger": "Successfully logged in",
                "credentials_paths": [str(token_src)],
            }
        }
    }
    config_path.write_text(json.dumps(config), encoding="utf-8")
    state_dir = tmp_path / "state"
    monkeypatch.setenv(auth.CONFIG_ENV_KEY, str(config_path))
    monkeypatch.setenv(auth.STATE_ENV_KEY, str(state_dir))

    start = time.perf_counter()
    exit_code = auth.main()
    duration = time.perf_counter() - start
    assert exit_code == 0
    assert duration < 2
    state_file = state_dir / auth.STATE_FILENAME
    data = json.loads(state_file.read_text(encoding="utf-8"))
    entry = data["agents"]["auto"]
    assert entry["status"] == "ok"
    stored = entry["stored_paths"]
    assert stored
    copied_dir = state_dir / "auto"
    assert copied_dir.exists()
    assert any(copied_dir.iterdir())

def test_agents_auth_skips_when_credentials_present(tmp_path, monkeypatch):
    cli = tmp_path / "sample_cli.sh"
    cli.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    make_executable(cli)
    token = tmp_path / "token.json"
    token.write_text('{"token":"xyz"}', encoding="utf-8")
    config_path = tmp_path / "agents.json"
    config = {
        "agents": {
            "sample": {
                "auth_command": [str(cli)],
            }
        }
    }
    config_path.write_text(json.dumps(config), encoding="utf-8")
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    state_file = state_dir / auth.STATE_FILENAME
    state_file.write_text(
        json.dumps(
            {
                "updated_at": None,
                "agents": {
                    "sample": {
                        "status": "ok",
                        "stored_paths": [str(token)],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(auth.CONFIG_ENV_KEY, str(config_path))
    monkeypatch.setenv(auth.STATE_ENV_KEY, str(state_dir))

    exit_code = auth.main()
    assert exit_code == 0
    # Состояние не меняется
    data = json.loads(state_file.read_text(encoding="utf-8"))
    assert data["agents"]["sample"]["status"] == "ok"


def test_agents_logout_clears_credentials(tmp_path, monkeypatch):
    token = tmp_path / "state" / "agents" / "sample" / "token.json"
    token.parent.mkdir(parents=True)
    token.write_text('{"token":"abc"}', encoding="utf-8")
    extra = tmp_path / "extra.json"
    extra.write_text('{"token":"abc"}', encoding="utf-8")
    config_path = tmp_path / "agents.json"
    config = {
        "agents": {
            "sample": {
                "auth_command": ["/bin/true"],
            }
        }
    }
    config_path.write_text(json.dumps(config), encoding="utf-8")
    state_dir = tmp_path / "state" / "agents"
    state_dir.mkdir(parents=True, exist_ok=True)
    state_file = state_dir / auth.STATE_FILENAME
    state_file.write_text(
        json.dumps(
            {
                "updated_at": None,
                "agents": {
                    "sample": {
                        "status": "ok",
                        "stored_paths": [str(extra)],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(auth.CONFIG_ENV_KEY, str(config_path))
    monkeypatch.setenv(auth.STATE_ENV_KEY, str(state_dir))

    exit_code = logout.main()
    assert exit_code == 0
    assert not token.exists()
    assert not extra.exists()
    data = json.loads(state_file.read_text(encoding="utf-8"))
    assert data["agents"]["sample"]["status"] == "logged_out"
def test_agents_auth_fallback_state_dir(tmp_path, monkeypatch):
    cli = tmp_path / "sample_cli.sh"
    creds_src = tmp_path / "creds"
    cli.write_text(
        """#!/usr/bin/env bash
set -Eeuo pipefail
mkdir -p \"${AGENT_AUTH_DIR}\"
printf '{"token":"xyz"}\n' > \"${AGENT_AUTH_DIR}/token.json\"
""",
        encoding="utf-8",
    )
    make_executable(cli)
    config_path = tmp_path / "agents.json"
    config = {
        "agents": {
            "sample": {
                "auth_command": [str(cli)],
                "auth_env": {"AGENT_AUTH_DIR": str(creds_src)},
                "credentials_paths": [str(creds_src / "token.json")],
            }
        }
    }
    config_path.write_text(json.dumps(config), encoding="utf-8")
    primary_state = tmp_path / "state"
    primary_state.mkdir()
    primary_state.chmod(0o555)
    fallback_state = tmp_path / "fallback-state"
    monkeypatch.setenv(auth.CONFIG_ENV_KEY, str(config_path))
    monkeypatch.setenv(auth.STATE_ENV_KEY, str(primary_state))
    monkeypatch.setenv(auth.STATE_FALLBACK_ENV_KEY, str(fallback_state))
    chosen: list[Path] = []
    original_resolve = auth.resolve_state_dir

    def tracking_resolve() -> Path:
        path = original_resolve()
        chosen.append(path)
        return path

    monkeypatch.setattr(auth, "resolve_state_dir", tracking_resolve)
    try:
        exit_code = auth.main()
    finally:
        primary_state.chmod(0o755)
    assert exit_code == 0
    assert chosen, "ожидалось, что resolve_state_dir будет вызван"
    state_dir = chosen[0]
    state_file = state_dir / auth.STATE_FILENAME
    assert state_file.exists(), f"не найден state-файл в {state_dir}"
    data = json.loads(state_file.read_text(encoding="utf-8"))
    entry = data["agents"]["sample"]
    assert entry["status"] == "ok"
    stored_paths = entry["stored_paths"]
    assert stored_paths
    stored_file = Path(stored_paths[0])
    assert stored_file.exists()
    assert stored_file.read_text(encoding="utf-8").strip() == '{"token":"xyz"}'
