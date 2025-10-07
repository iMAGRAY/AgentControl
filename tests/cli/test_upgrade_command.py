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
    monkeypatch.setattr(cli_main, "maybe_auto_update", lambda *args, **kwargs: None, raising=False)
    cli_main._build_services()  # ensure packaged templates staged into temp runtime
    return settings


def _create_legacy_project(tmp_path: Path) -> Path:
    project_root = tmp_path / "legacy"
    project_root.mkdir()
    bootstrap, _ = cli_main._build_services()
    project_id = cli_main.ProjectId.for_new_project(project_root)
    bootstrap.bootstrap(project_id, "stable", template="default")
    legacy_path = project_root / "agentcontrol"
    (project_root / ".agentcontrol").rename(legacy_path)
    return project_root


def test_upgrade_dry_run_reports_plan(runtime_settings: RuntimeSettings, capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    project_root = _create_legacy_project(tmp_path)

    exit_code = cli_main.main(["upgrade", str(project_root), "--dry-run"])
    assert exit_code == 0

    output = capsys.readouterr().out
    assert "Dry run" in output
    assert "agentcontrol.legacy-" in output
    assert not (project_root / ".agentcontrol").exists()
    assert (project_root / "agentcontrol").exists()


def test_upgrade_migrates_legacy_capsule(runtime_settings: RuntimeSettings, tmp_path: Path) -> None:
    project_root = _create_legacy_project(tmp_path)

    exit_code = cli_main.main(["upgrade", str(project_root)])
    assert exit_code == 0

    capsule_path = project_root / ".agentcontrol"
    assert capsule_path.exists()
    backups = sorted(project_root.glob("agentcontrol.legacy-*"))
    assert backups, "legacy backup should be kept for inspection"
    assert (capsule_path / "agentcontrol.project.json").exists()

    project_id = cli_main.ProjectId.from_existing(project_root)
    descriptor = project_id.descriptor_path()
    payload = json.loads(descriptor.read_text(encoding="utf-8"))
    assert payload["template"] == "default"


def test_upgrade_skip_legacy_migrate_fails(runtime_settings: RuntimeSettings, capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    project_root = _create_legacy_project(tmp_path)

    exit_code = cli_main.main(["upgrade", str(project_root), "--skip-legacy-migrate"])
    assert exit_code == 1
    stderr = capsys.readouterr().err
    assert "Project not initialised" in stderr
