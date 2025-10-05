from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentcontrol import __version__
from agentcontrol.cli import main as cli_main
from agentcontrol.settings import RuntimeSettings


@pytest.fixture()
def runtime_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RuntimeSettings:
    base = tmp_path / "runtime"
    home = base / "home"
    template_dir = base / "templates"
    state_dir = base / "state"
    log_dir = base / "logs"
    for directory in (home, template_dir, state_dir, log_dir):
        directory.mkdir(parents=True, exist_ok=True)
    settings = RuntimeSettings(
        home_dir=home,
        template_dir=template_dir,
        state_dir=state_dir,
        log_dir=log_dir,
        cli_version=__version__,
    )
    monkeypatch.setattr(cli_main, "SETTINGS", settings, raising=False)
    cli_main._build_services()
    return settings


@pytest.fixture()
def project(runtime_settings: RuntimeSettings, tmp_path: Path) -> Path:
    bootstrap, _ = cli_main._build_services()
    project_path = tmp_path / "workspace"
    project_path.mkdir(parents=True, exist_ok=True)
    cli_main._auto_bootstrap_project(bootstrap, project_path, "status")
    return project_path


def _load_events(settings: RuntimeSettings, command: str) -> list[dict[str, object]]:
    log_file = settings.log_dir / "telemetry.jsonl"
    if not log_file.exists():
        return []
    return [
        json.loads(line)
        for line in log_file.read_text(encoding="utf-8").splitlines()
        if line.strip() and json.loads(line).get("event") == f"mcp.{command}"
    ]


def test_mcp_add_list_remove(runtime_settings: RuntimeSettings, project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = cli_main.main(["mcp", str(project), "status", "--json"])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"servers": []}

    exit_code = cli_main.main([
        "mcp",
        str(project),
        "add",
        "--name",
        "demo",
        "--endpoint",
        "http://localhost:8080",
        "--json",
    ])
    assert exit_code == 0
    add_output = json.loads(capsys.readouterr().out)
    assert add_output["server"]["name"] == "demo"

    exit_code = cli_main.main(["mcp", str(project), "status", "--json"])
    assert exit_code == 0
    status_payload = json.loads(capsys.readouterr().out)
    assert len(status_payload["servers"]) == 1

    exit_code = cli_main.main(["mcp", str(project), "remove", "--name", "demo", "--json"])
    assert exit_code == 0
    remove_output = json.loads(capsys.readouterr().out)
    assert remove_output["status"] == "removed"

    exit_code = cli_main.main(["mcp", str(project), "status", "--json"])
    assert exit_code == 0
    final_payload = json.loads(capsys.readouterr().out)
    assert final_payload["servers"] == []

    events = _load_events(runtime_settings, "add")
    assert events[0].get("status") == "start"
    assert events[-1].get("status") == "success"


def test_mcp_add_requires_unique_name(runtime_settings: RuntimeSettings, project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = cli_main.main([
        "mcp",
        str(project),
        "add",
        "--name",
        "demo",
        "--endpoint",
        "http://localhost:8080",
    ])
    assert exit_code == 0
    capsys.readouterr()

    exit_code = cli_main.main([
        "mcp",
        str(project),
        "add",
        "--name",
        "demo",
        "--endpoint",
        "http://localhost:9000",
    ])
    assert exit_code == 1
    err = capsys.readouterr().err
    assert "already exists" in err

    exit_code = cli_main.main([
        "mcp",
        str(project),
        "add",
        "--name",
        "demo",
        "--endpoint",
        "http://localhost:9000",
        "--force",
    ])
    assert exit_code == 0
