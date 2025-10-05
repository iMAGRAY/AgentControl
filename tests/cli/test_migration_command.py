from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

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
def legacy_project(runtime_settings: RuntimeSettings, tmp_path: Path) -> Path:
    project_path = tmp_path / "legacy"
    legacy_docs = project_path / "agentcontrol" / "docs"
    legacy_docs.mkdir(parents=True, exist_ok=True)
    (legacy_docs / "README.md").write_text("Legacy docs", encoding="utf-8")
    config_dir = project_path / "agentcontrol" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "docs.bridge.yaml").write_text("version: 1\nroot: agentcontrol/docs\nsections: {}\n", encoding="utf-8")
    descriptor = project_path / "agentcontrol" / "agentcontrol.project.json"
    descriptor.parent.mkdir(parents=True, exist_ok=True)
    descriptor.write_text(json.dumps({"template_version": "0.3.2", "channel": "stable", "template": "default", "settings_hash": "123", "checksum": "abc"}), encoding="utf-8")
    return project_path


def test_migrate_dry_run(legacy_project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = cli_main.main(["migrate", str(legacy_project)])
    assert exit_code == 0
    stdout = capsys.readouterr().out
    assert "migration plan" in stdout


def test_migrate_apply(legacy_project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = cli_main.main(["migrate", str(legacy_project), "--apply", "--json"])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["result"]["status"] == "ok"
    docs_path = legacy_project / "docs" / "README.md"
    assert docs_path.exists()
    config_path = legacy_project / ".agentcontrol" / "config" / "docs.bridge.yaml"
    assert config_path.exists()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert config["root"] == "docs"
