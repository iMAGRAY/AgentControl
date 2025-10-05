from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentcontrol import __version__
from agentcontrol.cli import main as cli_main
from agentcontrol.settings import RuntimeSettings


@pytest.fixture()
def runtime_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RuntimeSettings:
    base = tmp_path / "sandbox-runtime"
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


def test_sandbox_start_list_and_purge(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = cli_main.main(["sandbox", str(project), "start", "--json", "--meta", "purpose=test"])
    assert exit_code == 0
    output = capsys.readouterr().out
    payload = json.loads(output)
    sandbox_id = payload["sandbox_id"]
    sandbox_path = Path(payload["path"])
    assert sandbox_path.exists()

    exit_code = cli_main.main(["sandbox", str(project), "list", "--json"])
    assert exit_code == 0
    list_payload = json.loads(capsys.readouterr().out)
    assert any(entry["sandbox_id"] == sandbox_id for entry in list_payload["sandboxes"])

    exit_code = cli_main.main(["sandbox", str(project), "purge", "--id", sandbox_id, "--json"])
    assert exit_code == 0
    purge_payload = json.loads(capsys.readouterr().out)
    assert any(entry["sandbox_id"] == sandbox_id for entry in purge_payload["removed"])
    assert not sandbox_path.exists()
