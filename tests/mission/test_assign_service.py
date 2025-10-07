from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentcontrol.app.mission.assigner import MissionAssignmentError, MissionAssignmentService


@pytest.fixture()
def project_root(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
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
                    {"id": "T1", "title": "Do work", "status": "open"},
                    {"id": "T2", "title": "Done work", "status": "done"},
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return root


def test_assign_and_update(project_root: Path) -> None:
    service = MissionAssignmentService(project_root)
    payload = service.assign("T1", "alpha")
    assert payload["assignment"]["task_id"] == "T1"

    with pytest.raises(MissionAssignmentError):
        service.assign("T1", "alpha")

    updated = service.update_status("T1", "done", agent_id="alpha")
    assert updated["status"] == "done"


def test_assign_reject_done_task(project_root: Path) -> None:
    service = MissionAssignmentService(project_root)
    with pytest.raises(MissionAssignmentError):
        service.assign("T2", "alpha")


def test_assign_unknown_agent(project_root: Path) -> None:
    service = MissionAssignmentService(project_root)
    with pytest.raises(MissionAssignmentError):
        service.assign("T1", "beta")
