from __future__ import annotations

from pathlib import Path

import pytest

from agentcontrol import __version__
from agentcontrol.cli import main as cli_main
from agentcontrol.settings import RuntimeSettings


@pytest.fixture()
def runtime_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RuntimeSettings:
    """Configure isolated runtime settings for extension CLI tests."""
    runtime = tmp_path / "runtime"
    home = runtime / "home"
    template_dir = runtime / "templates"
    state_dir = runtime / "state"
    log_dir = runtime / "logs"
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
    cli_main._build_services()
    return settings


@pytest.fixture()
def project_root(runtime_settings: RuntimeSettings, tmp_path: Path) -> Path:
    """Bootstrap a fresh project capsule for extension scenarios."""
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    bootstrap, _ = cli_main._build_services()
    project_id = cli_main.ProjectId.for_new_project(project_root)
    bootstrap.bootstrap(project_id, "stable", template="default")
    return project_root
