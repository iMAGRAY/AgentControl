from __future__ import annotations

import json
from pathlib import Path

from agentcontrol.domain.tasks import TaskBoard, TaskRecord, TaskSyncOp, build_sync_plan


def _write_board(path: Path) -> None:
    payload = {
        "version": "0.1.0",
        "updated_at": "2025-10-01T00:00:00Z",
        "tasks": [
            {
                "id": "T1",
                "title": "Existing feature",
                "status": "open",
                "priority": "P1",
                "owner": "core",
            },
            {
                "id": "T2",
                "title": "Legacy cleanup",
                "status": "open",
                "priority": "P2",
                "owner": "core",
            },
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_build_sync_plan_and_apply(tmp_path: Path) -> None:
    board_path = tmp_path / "tasks.board.json"
    _write_board(board_path)
    board = TaskBoard.load(board_path)

    remote_tasks = [
        TaskRecord("T1", {"title": "Existing feature", "status": "done", "priority": "P1"}),
        TaskRecord("T3", {"title": "New automation", "status": "open", "priority": "P1"}),
    ]

    plan = build_sync_plan(board, remote_tasks)
    summary = plan.summary()
    assert summary == {"total": 3, "create": 1, "update": 1, "close": 1, "unchanged": 0}
    ops = {action.op for action in plan.actions}
    assert ops == {TaskSyncOp.CREATE, TaskSyncOp.UPDATE, TaskSyncOp.CLOSE}
    update_action = next(action for action in plan.actions if action.op == TaskSyncOp.UPDATE)
    assert update_action.changes is not None
    assert update_action.changes["status"]["to"] == "done"

    board.apply(plan)
    board.save()
    updated_board = TaskBoard.load(board_path)
    assert updated_board.tasks["T1"].status == "done"
    assert updated_board.tasks["T3"].title == "New automation"
    assert updated_board.tasks["T2"].status == "done"
    assert "completed_at" in updated_board.tasks["T2"].data
    assert updated_board.order[-1] == "T2"


def test_build_sync_plan_without_changes(tmp_path: Path) -> None:
    board_path = tmp_path / "tasks.board.json"
    _write_board(board_path)
    board = TaskBoard.load(board_path)
    remote_tasks = [
        TaskRecord("T1", {"title": "Existing feature", "status": "open", "priority": "P1"}),
        TaskRecord("T2", {"title": "Legacy cleanup", "status": "open", "priority": "P2"}),
    ]

    plan = build_sync_plan(board, remote_tasks)
    assert not plan.actions
    board.apply(plan)
    board.save()
    reloaded = TaskBoard.load(board_path)
    assert reloaded.updated_at == "2025-10-01T00:00:00Z"
