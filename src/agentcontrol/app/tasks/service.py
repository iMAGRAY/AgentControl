"""Application service for synchronising the local task board."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

from agentcontrol.domain.project import ProjectId
from agentcontrol.domain.tasks import (
    TaskBoard,
    TaskBoardError,
    TaskSyncPlan,
    build_sync_plan,
)
from agentcontrol.adapters.tasks.file_provider import FileTaskProvider
from agentcontrol.ports.tasks.provider import TaskProvider, TaskProviderError


class TaskSyncError(RuntimeError):
    """Raised when synchronisation cannot be performed."""


@dataclass(frozen=True)
class TaskSyncResult:
    board_path: Path
    report_path: Path
    plan: TaskSyncPlan
    provider_config: Dict[str, Any]
    applied: bool
    report_payload: Dict[str, Any]

    def to_dict(self, *, project_root: Path | None = None) -> Dict[str, Any]:
        root = project_root or Path.cwd()
        payload = dict(self.report_payload)
        payload["board_path"] = payload.get("board_path", _relativize(self.board_path, root))
        payload["report_path"] = _relativize(self.report_path, root)
        payload["provider"] = self.provider_config
        payload.update(self.plan.to_dict())
        payload["applied"] = self.applied
        return payload


class TaskSyncService:
    def __init__(self, project_id: ProjectId) -> None:
        self._project_id = project_id
        self._root = project_id.root

    def sync(
        self,
        *,
        config_path: Path | None = None,
        apply: bool = False,
        output_path: Path | None = None,
    ) -> TaskSyncResult:
        provider_config = self._load_provider_config(config_path)
        provider = self._build_provider(provider_config)
        try:
            provider_tasks = list(provider.fetch())
        except TaskProviderError as exc:
            raise TaskSyncError(str(exc)) from exc

        board_path = self._root / "data" / "tasks.board.json"
        try:
            board = TaskBoard.load(board_path)
        except TaskBoardError as exc:
            raise TaskSyncError(str(exc)) from exc

        plan = build_sync_plan(board, provider_tasks)

        applied = False
        if apply and plan.actions:
            board.apply(plan)
            board.save()
            applied = True

        report_payload = self._build_report_payload(
            plan=plan,
            provider_config=provider_config,
            board_path=board_path,
            applied=applied,
        )

        report_path = output_path or (self._root / "reports" / "tasks_sync.json")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        return TaskSyncResult(
            board_path=board_path,
            report_path=report_path,
            plan=plan,
            provider_config=provider_config,
            applied=applied,
            report_payload=report_payload,
        )

    def _load_provider_config(self, config_path: Path | None) -> Dict[str, Any]:
        if config_path is None:
            config_path = self._root / "config" / "tasks.provider.json"
        if not config_path.exists():
            raise TaskSyncError(
                f"tasks.sync.config_not_found: provider config missing at {config_path}"
            )
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise TaskSyncError(f"tasks.sync.config_invalid: {exc}") from exc
        if not isinstance(config, dict):
            raise TaskSyncError("tasks.sync.config_invalid: root must be object")
        if "type" not in config:
            raise TaskSyncError("tasks.sync.config_invalid: missing type")
        if not isinstance(config["type"], str) or not config["type"]:
            raise TaskSyncError("tasks.sync.config_invalid: type must be string")
        options = config.get("options")
        if options is None:
            options = {}
        if not isinstance(options, dict):
            raise TaskSyncError("tasks.sync.config_invalid: options must be object")
        config["options"] = options
        return config

    def _build_provider(self, config: Dict[str, Any]) -> TaskProvider:
        provider_type = config["type"].lower()
        options = config.get("options", {})
        if provider_type == "file":
            raw_path = options.get("path")
            if not isinstance(raw_path, str) or not raw_path:
                raise TaskSyncError("tasks.sync.config_invalid: options.path required for file provider")
            return FileTaskProvider(self._root, Path(raw_path))
        raise TaskSyncError(f"tasks.sync.provider_not_supported: {provider_type}")

    def _build_report_payload(
        self,
        *,
        plan: TaskSyncPlan,
        provider_config: Dict[str, Any],
        board_path: Path,
        applied: bool,
    ) -> Dict[str, Any]:
        from datetime import datetime, timezone

        generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        payload: Dict[str, Any] = {
            "generated_at": generated_at,
            "project_root": str(self._root),
            "board_path": str(board_path.relative_to(self._root)),
            "provider": provider_config,
            "applied": applied,
        }
        payload.update(plan.to_dict())
        return payload


def _relativize(path: Path, base: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)
