from __future__ import annotations

import os
from pathlib import Path

import pytest

from agentcontrol import __version__
from agentcontrol.app.bootstrap_service import BootstrapService
from agentcontrol.cli import main as cli_main
from agentcontrol.domain.project import ProjectCapsule, ProjectId
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
    # rebuild services once to ensure packaged templates are synced under the new settings
    cli_main._build_services()
    return settings


def _make_bootstrap(settings: RuntimeSettings) -> BootstrapService:
    bootstrap, _ = cli_main._build_services()
    return bootstrap


def test_auto_bootstrap_creates_capsule(tmp_path: Path, runtime_settings: RuntimeSettings) -> None:
    bootstrap = _make_bootstrap(runtime_settings)
    project_path = tmp_path / "workspace"
    project_path.mkdir()

    project_id = cli_main._auto_bootstrap_project(bootstrap, project_path, "status")
    assert project_id is not None

    descriptor = project_path / ".agentcontrol" / "agentcontrol.project.json"
    assert descriptor.exists()
    assert not (project_path / "agentcall.yaml").exists()

    capsule = ProjectCapsule.load(project_id)
    assert capsule.project_id == project_id
    assert project_id.command_descriptor_path() == project_path / ".agentcontrol" / "agentcall.yaml"


def test_auto_bootstrap_respects_disable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, runtime_settings: RuntimeSettings) -> None:
    bootstrap = _make_bootstrap(runtime_settings)
    monkeypatch.setenv("AGENTCONTROL_NO_AUTO_INIT", "1")

    project_path = tmp_path / "workspace"
    project_path.mkdir()

    result = cli_main._auto_bootstrap_project(bootstrap, project_path, "status")
    assert result is None
    assert not (project_path / ".agentcontrol").exists()


def test_auto_bootstrap_skips_sdk_repository(tmp_path: Path, runtime_settings: RuntimeSettings) -> None:
    bootstrap = _make_bootstrap(runtime_settings)
    project_path = tmp_path / "agentcontrol-sdk"
    (project_path / "src" / "agentcontrol" / "templates").mkdir(parents=True)
    (project_path / "pyproject.toml").write_text("[project]\nname = \"agentcontrol\"\n", encoding="utf-8")

    result = cli_main._auto_bootstrap_project(bootstrap, project_path, "status")
    assert result is None
    assert not (project_path / ".agentcontrol").exists()


def test_auto_bootstrap_skips_sdk_repository_subdir(tmp_path: Path, runtime_settings: RuntimeSettings) -> None:
    bootstrap = _make_bootstrap(runtime_settings)
    root = tmp_path / "agentcontrol-sdk"
    (root / "src" / "agentcontrol" / "templates").mkdir(parents=True)
    (root / "pyproject.toml").write_text("[project]\nname = \"agentcontrol\"\n", encoding="utf-8")

    project_path = root / "tests" / "cli"
    project_path.mkdir(parents=True)

    result = cli_main._auto_bootstrap_project(bootstrap, project_path, "status")
    assert result is None
    assert not (root / ".agentcontrol").exists()
    assert not (project_path / ".agentcontrol").exists()


def test_resolve_project_id_no_auto(tmp_path: Path, runtime_settings: RuntimeSettings, capsys: pytest.CaptureFixture[str]) -> None:
    bootstrap = _make_bootstrap(runtime_settings)
    project_path = tmp_path / "workspace"
    project_path.mkdir()

    result = cli_main._resolve_project_id(bootstrap, project_path, "upgrade", allow_auto=False)
    assert result is None
    captured = capsys.readouterr()
    assert "not an AgentControl project" in captured.err


def test_resolve_project_id_with_auto(tmp_path: Path, runtime_settings: RuntimeSettings) -> None:
    bootstrap = _make_bootstrap(runtime_settings)
    project_path = tmp_path / "workspace"
    project_path.mkdir()

    result = cli_main._resolve_project_id(bootstrap, project_path, "status", allow_auto=True)
    assert isinstance(result, ProjectId)
    assert (project_path / ".agentcontrol" / "agentcall.yaml").exists()
