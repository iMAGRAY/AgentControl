from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentcontrol import __version__
from agentcontrol.cli import main as cli_main
from agentcontrol.settings import RuntimeSettings
from agentcontrol.utils.telemetry import record_event


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
    monkeypatch.setattr(cli_main, "maybe_auto_update", lambda *args, **kwargs: None, raising=False)
    cli_main._build_services()  # bootstrap packaged templates into temp runtime
    return settings


def test_pipeline_commands_registered() -> None:
    parser = cli_main.build_parser()
    expected = {"setup", "dev", "verify", "fix", "review", "ship", "status", "progress", "roadmap", "agents"}
    for command in expected:
        namespace = parser.parse_args([command])
        assert getattr(namespace, "command_name", None) == command


def test_telemetry_report_recent(runtime_settings: RuntimeSettings, capsys: pytest.CaptureFixture[str]) -> None:
    record_event(runtime_settings, "alpha", {"status": "ok"})
    record_event(runtime_settings, "beta", {"status": "warn"})

    exit_code = cli_main.main(["telemetry", "report", "--recent", "1"])
    assert exit_code == 0

    captured = capsys.readouterr().out.strip()
    summary = json.loads(captured)
    assert summary["total"] == 1
    assert summary["by_event"] == {"beta": 1}
