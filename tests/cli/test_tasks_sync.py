from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentcontrol.cli import main as cli_main
from agentcontrol.cli.main import _build_services


def _setup_project(tmp_path: Path) -> Path:
    bootstrap, _ = _build_services()
    project_root = tmp_path / "project"
    project_root.mkdir()
    cli_main._auto_bootstrap_project(bootstrap, project_root, "tasks")
    data_dir = project_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    board_path = data_dir / "tasks.board.json"
    board_path.write_text(
        json.dumps(
            {
                "version": "0.1.0",
                "updated_at": "2025-10-01T00:00:00Z",
                "tasks": [
                    {
                        "id": "TASK-1",
                        "title": "Existing",
                        "status": "open",
                        "priority": "P1",
                    },
                    {
                        "id": "TASK-2",
                        "title": "Stale",
                        "status": "open",
                        "priority": "P2",
                    },
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return project_root


def _write_remote(tmp_path: Path) -> Path:
    remote_path = tmp_path / "remote.json"
    remote_path.write_text(
        json.dumps(
            {
                "tasks": [
                    {
                        "id": "TASK-1",
                        "title": "Existing",
                        "status": "in_progress",
                        "priority": "P1",
                    },
                    {
                        "id": "TASK-3",
                        "title": "New Task",
                        "status": "open",
                        "priority": "P0",
                    },
                ]
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return remote_path


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    return _setup_project(tmp_path)


def test_tasks_sync_dry_run(project: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    remote = _write_remote(tmp_path)
    exit_code = cli_main.main(
        [
            "tasks",
            "sync",
            str(project),
            "--provider",
            "file",
            "--input",
            str(remote),
            "--dry-run",
            "--json",
        ]
    )
    assert exit_code == 0
    output = capsys.readouterr().out
    report = json.loads(output)
    assert report["dry_run"]
    assert len(report["operations"]) == 3
    kinds = {op["type"] for op in report["operations"]}
    assert kinds == {"create", "update", "close"}
    board = json.loads((project / "data" / "tasks.board.json").read_text(encoding="utf-8"))
    assert board["tasks"][0]["status"] == "open"


def test_tasks_sync_apply(project: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    remote = _write_remote(tmp_path)
    exit_code = cli_main.main(
        [
            "tasks",
            "sync",
            str(project),
            "--provider",
            "file",
            "--input",
            str(remote),
        ]
    )
    assert exit_code == 0
    board_path = project / "data" / "tasks.board.json"
    board = json.loads(board_path.read_text(encoding="utf-8"))
    tasks = {task["id"]: task for task in board["tasks"]}
    assert tasks["TASK-1"]["status"] == "in_progress"
    assert tasks["TASK-3"]["status"] == "open"
    assert tasks["TASK-2"]["status"] == "done"
    report_path = project / "reports" / "tasks" / "sync.json"
    assert report_path.exists()
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert not payload["dry_run"]
    assert len(payload["operations"]) == 3
