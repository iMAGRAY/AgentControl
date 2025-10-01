from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from scripts.agents import status, logs, workflow  # noqa: E402


def make_executable(path: Path, content: str = "#!/usr/bin/env bash\nexit 0\n") -> None:
    path.write_text(content, encoding="utf-8")
    mode = path.stat().st_mode
    path.chmod(mode | stat.S_IEXEC)


def test_collect_status_detects_cli_and_credentials(tmp_path, monkeypatch):
    config_path = tmp_path / "agents.json"
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    cli_path = tmp_path / "codex"
    make_executable(cli_path)
    config = {
        "log_dir": str(log_dir),
        "agents": {
            "codex": {
                "command": [str(cli_path), "chat"],
            }
        }
    }
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")

    state_dir = tmp_path / "state"
    state_dir.mkdir()
    token = tmp_path / "token.json"
    token.write_text("{}", encoding="utf-8")
    state = {
        "agents": {
            "codex": {
                "status": "ok",
                "stored_paths": [str(token)],
            }
        }
    }
    (state_dir / "auth_status.json").write_text(json.dumps(state), encoding="utf-8")

    log_file = log_dir / "20250101T000000Z-codex-assign.log"
    log_file.write_text("{}", encoding="utf-8")

    monkeypatch.setenv("AGENTS_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("AGENTS_AUTH_STATE_DIR", str(state_dir))

    rows = status.collect_status()
    assert len(rows) == 1
    entry = rows[0]
    assert entry.cli_exists is True
    assert entry.credentials_ok is True


def test_discover_logs_filters_by_agent(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "20250101T000000Z-codex-assign.log").write_text("A", encoding="utf-8")
    (log_dir / "20250101T000100Z-claude-analysis.log").write_text("B", encoding="utf-8")

    entries = logs.discover_logs(log_dir, agent="codex")
    assert len(entries) == 1
    assert entries[0].agent == "codex"
    assert entries[0].command == "assign"


def test_workflow_pipeline_invokes_assign_and_review(tmp_path, monkeypatch):
    config_path = tmp_path / "agents.json"
    config = {
        "agents": {
            "codex": {"command": ["codex"]},
            "claude": {"command": ["claude"]},
        },
        "workflows": {
            "default": {
                "assign_agent": "codex",
                "review_agent": "claude",
                "assign_role": "Builder",
                "review_role": "Reviewer",
            }
        }
    }
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    monkeypatch.setenv("AGENTS_CONFIG_PATH", str(config_path))

    calls = []

    class FakeResult:
        def __init__(self):
            self.returncode = 0
            self.stdout = "ok"
            self.stderr = ""

    def fake_run_agent(command, agent, task, role):
        calls.append((command, agent, task, role))
        return FakeResult()

    monkeypatch.setattr(workflow, "run_agent", fake_run_agent)

    wf = workflow.pick_workflow(config, "default")
    rc = workflow.pipeline("TASK-1", wf, dry_run=False)
    assert rc == 0
    assert calls == [
        ("assign", "codex", "TASK-1", "Builder"),
        ("analysis", "claude", "TASK-1", "Reviewer"),
    ]
