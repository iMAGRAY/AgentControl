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
    cli_main._build_services()
    return settings


def _prepare_project(root: Path) -> None:
    project_id = ProjectId.for_new_project(root)
    capsule = ProjectCapsule(
        project_id=project_id,
        template_version="0.5.1",
        channel="stable",
        template_name="default",
        settings_hash=project_settings_hash("0.5.1", "stable", "default"),
        metadata={"created_with": __version__},
    )
    capsule.store()

    board_dir = root / "data"
    board_dir.mkdir(parents=True, exist_ok=True)
    board_payload = {
        "version": "0.1.0",
        "updated_at": "2025-10-01T00:00:00Z",
        "tasks": [
            {
                "id": "T1",
                "title": "Existing feature",
                "status": "open",
            },
            {
                "id": "T3",
                "title": "Legacy cleanup",
                "status": "open",
            },
        ],
    }
    (board_dir / "tasks.board.json").write_text(json.dumps(board_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    provider_dir = root / "state" / "provider"
    provider_dir.mkdir(parents=True, exist_ok=True)
    provider_payload = {
        "tasks": [
            {
                "id": "T1",
                "title": "Existing feature",
                "status": "done",
            },
            {
                "id": "T2",
                "title": "New automation",
                "status": "open",
            },
        ]
    }
    snapshot_path = provider_dir / "tasks_snapshot.json"
    snapshot_path.write_text(json.dumps(provider_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    config_dir = root / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_payload = {
        "type": "file",
        "options": {"path": str(snapshot_path.relative_to(root))},
    }
    (config_dir / "tasks.provider.json").write_text(json.dumps(config_payload, ensure_ascii=False, indent=2), encoding="utf-8")


@pytest.mark.usefixtures("runtime_settings")
def test_tasks_sync_cli_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    _prepare_project(project_root)

    exit_code = cli_main.main(["tasks", "sync", str(project_root), "--json"])
    assert exit_code == 0

    output = capsys.readouterr().out
    payload = json.loads(output)
    assert payload["summary"] == {"total": 3, "create": 1, "update": 1, "close": 1, "unchanged": 0}
    assert payload["applied"] is False
    assert payload["board_path"].endswith("data/tasks.board.json")
    board_path = project_root / payload["board_path"]
    board_payload = json.loads(board_path.read_text(encoding="utf-8"))
    # Dry-run should not mutate board
    status_map = {task["id"]: task["status"] for task in board_payload["tasks"]}
    assert status_map["T1"] == "open"


@pytest.mark.usefixtures("runtime_settings")
def test_tasks_sync_cli_apply(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    _prepare_project(project_root)

    exit_code = cli_main.main(["tasks", "sync", str(project_root), "--apply"])
    assert exit_code == 0

    board_payload = json.loads((project_root / "data" / "tasks.board.json").read_text(encoding="utf-8"))
    status_map = {task["id"]: task["status"] for task in board_payload["tasks"]}
    assert status_map["T1"] == "done"
    assert status_map["T3"] == "done"
    assert any(task["id"] == "T2" for task in board_payload["tasks"])

    err = capsys.readouterr().err
    assert err == ""
