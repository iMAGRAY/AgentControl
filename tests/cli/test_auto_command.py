from __future__ import annotations

from pathlib import Path
import json

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


def test_auto_docs_dry_run(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = cli_main.main(["auto", str(project), "docs"])
    assert exit_code == 0
    output = capsys.readouterr().out
    assert "automation plan (docs)" in output


def test_auto_docs_apply_without_issues(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = cli_main.main(["auto", str(project), "docs", "--apply"])
    assert exit_code == 0
    output = capsys.readouterr().out
    payload = json.loads(output)
    assert "generatedAt" in payload


def test_auto_tests_dry_run(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = cli_main.main(["auto", str(project), "tests"])
    assert exit_code == 0
    output = capsys.readouterr().out
    assert "automation plan (tests)" in output


def test_auto_release_dry_run(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = cli_main.main(["auto", str(project), "release"])
    assert exit_code == 0
    output = capsys.readouterr().out
    assert "automation plan (release)" in output
