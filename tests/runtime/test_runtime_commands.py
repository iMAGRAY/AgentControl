from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentcontrol import __version__
from agentcontrol.cli import main as cli_main
from agentcontrol.runtime import load_manifest, stream_events
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


def test_runtime_status_generates_manifest(runtime_settings: RuntimeSettings, project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = cli_main.main(["runtime", str(project), "status", "--json"])
    assert exit_code == 0
    manifest = json.loads(capsys.readouterr().out)
    assert manifest["project"].endswith(str(project))
    runtime_file = project / ".agentcontrol" / "runtime.json"
    assert runtime_file.exists()
    loaded = load_manifest(project)
    assert loaded["commands"] == manifest["commands"]


def test_runtime_events_limit(runtime_settings: RuntimeSettings, project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cli_main.main(["docs", str(project), "diagnose", "--json"])
    capsys.readouterr()
    exit_code = cli_main.main(["runtime", str(project), "events", "--limit", "1"])
    assert exit_code == 0
    output = capsys.readouterr().out.strip().splitlines()
    assert len(output) == 1
    event = json.loads(output[0])
    assert "event" in event

    events = list(stream_events(runtime_settings.log_dir, follow=False))
    assert any(evt.get("event") == event["event"] for evt in events)
