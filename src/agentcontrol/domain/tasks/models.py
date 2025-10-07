"""Domain models and diff logic for task board synchronisation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _isoformat(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


class TaskBoardError(RuntimeError):
    """Raised when the task board cannot be parsed or persisted."""


class TaskRecordError(ValueError):
    """Raised when a task payload is invalid."""


@dataclass
class TaskRecord:
    """A single task entry on the board or provided by an external provider."""

    id: str
    data: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id:
            raise TaskRecordError("task id must be a non-empty string")
        if "title" not in self.data or not isinstance(self.data["title"], str):
            raise TaskRecordError("task title missing or invalid")
        if "status" not in self.data or not isinstance(self.data["status"], str):
            raise TaskRecordError("task status missing or invalid")

    @property
    def title(self) -> str:
        return str(self.data.get("title", ""))

    @property
    def status(self) -> str:
        return str(self.data.get("status", ""))

    def to_dict(self) -> Dict[str, Any]:
        payload = {"id": self.id}
        payload.update(self.data)
        return payload

    def diff(self, other: "TaskRecord") -> Dict[str, Dict[str, Any]]:
        """Compute field-level changes from self (local) to ``other`` (remote)."""

        changes: Dict[str, Dict[str, Any]] = {}
        for key, remote_value in other.data.items():
            if key == "id":  # safety guard though id is not part of data
                continue
            local_value = self.data.get(key)
            if local_value != remote_value:
                changes[key] = {"from": local_value, "to": remote_value}
        return changes

    def apply(self, changes: Mapping[str, Any]) -> None:
        for key, value in changes.items():
            self.data[key] = value

    def clone(self) -> "TaskRecord":
        return TaskRecord(self.id, json.loads(json.dumps(self.data)))


class TaskSyncOp(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    CLOSE = "close"


@dataclass(frozen=True)
class TaskAction:
    op: TaskSyncOp
    task: TaskRecord | None = None
    task_id: str | None = None
    changes: Dict[str, Dict[str, Any]] | None = None
    reason: str | None = None

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"op": self.op.value}
        if self.op == TaskSyncOp.CREATE and self.task is not None:
            payload["task"] = self.task.to_dict()
        if self.op == TaskSyncOp.UPDATE:
            payload["task_id"] = self.task_id
            payload["changes"] = self.changes or {}
        if self.op == TaskSyncOp.CLOSE:
            payload["task_id"] = self.task_id
            if self.reason:
                payload["reason"] = self.reason
        return payload


@dataclass
class TaskSyncPlan:
    actions: List[TaskAction]
    create_count: int
    update_count: int
    close_count: int
    unchanged_count: int

    def summary(self) -> Dict[str, int]:
        return {
            "total": self.create_count + self.update_count + self.close_count + self.unchanged_count,
            "create": self.create_count,
            "update": self.update_count,
            "close": self.close_count,
            "unchanged": self.unchanged_count,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "summary": self.summary(),
            "actions": [action.to_dict() for action in self.actions],
        }


@dataclass
class TaskBoard:
    path: Path
    version: str
    updated_at: str | None
    tasks: Dict[str, TaskRecord]
    order: List[str]
    extra: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "TaskBoard":
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise TaskBoardError(f"task board not found at {path}") from exc
        except json.JSONDecodeError as exc:
            raise TaskBoardError(f"task board invalid JSON: {exc}") from exc

        if not isinstance(raw, dict):
            raise TaskBoardError("task board root must be an object")

        version = str(raw.get("version", ""))
        if not version:
            raise TaskBoardError("task board missing version")

        updated_at = raw.get("updated_at")
        if updated_at is not None and not isinstance(updated_at, str):
            raise TaskBoardError("task board updated_at must be string")

        tasks_payload = raw.get("tasks")
        if not isinstance(tasks_payload, list):
            raise TaskBoardError("task board tasks must be a list")

        tasks: Dict[str, TaskRecord] = {}
        order: List[str] = []
        for entry in tasks_payload:
            if not isinstance(entry, dict):
                raise TaskBoardError("each task entry must be an object")
            if "id" not in entry:
                raise TaskBoardError("task entry missing id")
            task_id = str(entry["id"])
            data = {k: v for k, v in entry.items() if k != "id"}
            record = TaskRecord(task_id, data)
            tasks[task_id] = record
            order.append(task_id)

        extra = {k: v for k, v in raw.items() if k not in {"version", "updated_at", "tasks"}}
        return cls(path=path, version=version, updated_at=updated_at, tasks=tasks, order=order, extra=extra)

    def save(self) -> None:
        payload: Dict[str, Any] = {"version": self.version}
        payload.update(self.extra)
        payload["updated_at"] = self.updated_at
        payload["tasks"] = [self.tasks[task_id].to_dict() for task_id in self.order if task_id in self.tasks]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def iter_tasks(self) -> Iterable[TaskRecord]:
        for task_id in self.order:
            task = self.tasks.get(task_id)
            if task is not None:
                yield task

    def apply(self, plan: TaskSyncPlan) -> None:
        if not plan.actions:
            return
        now_iso = _isoformat(_utc_now())
        for action in plan.actions:
            if action.op == TaskSyncOp.CREATE and action.task is not None:
                self._apply_create(action.task)
            elif action.op == TaskSyncOp.UPDATE and action.task_id:
                self._apply_update(action.task_id, action.changes or {})
            elif action.op == TaskSyncOp.CLOSE and action.task_id:
                self._apply_close(action.task_id)
        self.updated_at = now_iso

    def _apply_create(self, task: TaskRecord) -> None:
        clone = task.clone()
        if clone.id in self.tasks:
            self._apply_update(clone.id, clone.data)
            return
        self.tasks[clone.id] = clone
        self.order.append(clone.id)

    def _apply_update(self, task_id: str, changes: Mapping[str, Any]) -> None:
        record = self.tasks.get(task_id)
        if record is None:
            return
        normalized: Dict[str, Any] = {}
        for key, value in changes.items():
            if isinstance(value, dict) and "to" in value:
                normalized[key] = value["to"]
            else:
                normalized[key] = value
        record.apply(normalized)

    def _apply_close(self, task_id: str) -> None:
        record = self.tasks.get(task_id)
        if record is None:
            return
        record.data["status"] = "done"
        record.data["completed_at"] = _isoformat(_utc_now())
        if task_id in self.order:
            self.order = [tid for tid in self.order if tid != task_id]
            self.order.append(task_id)


def build_sync_plan(board: TaskBoard, provider_tasks: Iterable[TaskRecord]) -> TaskSyncPlan:
    existing = board.tasks
    provider_index = {task.id: task for task in provider_tasks}
    actions: List[TaskAction] = []
    create_count = 0
    update_count = 0
    close_count = 0
    unchanged_count = 0

    for task_id, remote in provider_index.items():
        local = existing.get(task_id)
        if local is None:
            actions.append(TaskAction(op=TaskSyncOp.CREATE, task=remote))
            create_count += 1
            continue
        changes = local.diff(remote)
        if changes:
            actions.append(TaskAction(op=TaskSyncOp.UPDATE, task_id=task_id, changes=changes))
            update_count += 1
        else:
            unchanged_count += 1

    for task_id, local in existing.items():
        if task_id not in provider_index:
            actions.append(TaskAction(op=TaskSyncOp.CLOSE, task_id=task_id, reason="provider_removed"))
            close_count += 1

    return TaskSyncPlan(
        actions=actions,
        create_count=create_count,
        update_count=update_count,
        close_count=close_count,
        unchanged_count=unchanged_count,
    )
