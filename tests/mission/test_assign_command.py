from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentcontrol import __version__
from agentcontrol.cli import main as cli_main
from agentcontrol.domain.project import ProjectCapsule, ProjectId, project_settings_hash
from agentcontrol.settings import RuntimeSettings


@pytest.fixture()
def runtime_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RuntimeSettings:
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


def _prepare_project(root: Path) -> None:
    project_id = ProjectId.for_new_project(root)
    capsule = ProjectCapsule(
        project_id=project_id,
        template_version="0.5.2",
        channel="stable",
        template_name="default",
        settings_hash=project_settings_hash("0.5.2", "stable", "default"),
        metadata={"created_with": __version__},
    )
    capsule.store()
    config_dir = root / ".agentcontrol" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_dir.joinpath("mission_assign.yaml").write_text(
        """
agents:
  - id: alpha
    name: Alpha Agent
    max_active: 1
""",
        encoding="utf-8",
    )
    board_dir = root / "data"
    board_dir.mkdir(parents=True, exist_ok=True)
    board_dir.joinpath("tasks.board.json").write_text(
        json.dumps(
            {
                "version": "0.1.0",
                "updated_at": "2025-10-07T00:00:00Z",
                "tasks": [
                    {"id": "T1", "title": "Do work", "status": "open"}
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


@pytest.mark.usefixtures("runtime_settings")
def test_assign_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    _prepare_project(project_root)
    exit_code = cli_main.main([
        "mission",
        "assign",
        str(project_root),
        "--task",
        "T1",
        "--agent",
        "alpha",
        "--json",
    ])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["assignment"]["task_id"] == "T1"

    exit_code = cli_main.main([
        "mission",
        "assign",
        str(project_root),
        "--list",
        "--json",
    ])
    assert exit_code == 0
    listing = json.loads(capsys.readouterr().out)
    assert listing["assignments"]
