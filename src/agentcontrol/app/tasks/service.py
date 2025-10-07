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
from agentcontrol.adapters.tasks.providers import build_provider_from_config
from agentcontrol.ports.tasks.provider import TaskProviderError


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
        provider: Dict[str, Any] | None = None,
        apply: bool = False,
        output_path: Path | None = None,
    ) -> TaskSyncResult:
        provider_config = self._resolve_provider_config(config_path, provider)
        try:
            build_result = build_provider_from_config(self._root, provider_config)
        except TaskProviderError as exc:
            raise TaskSyncError(str(exc)) from exc
        provider = build_result.provider
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
            provider_config=build_result.report_config,
            board_path=board_path,
            applied=applied,
        )

        report_path = output_path or (self._root / "reports" / "tasks_sync.json")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        self._write_mission_artifacts(report_payload, report_path)

        return TaskSyncResult(
            board_path=board_path,
            report_path=report_path,
            plan=plan,
            provider_config=build_result.report_config,
            applied=applied,
            report_payload=report_payload,
        )

    def _resolve_provider_config(
        self,
        config_path: Path | None,
        provider: Dict[str, Any] | None,
    ) -> Dict[str, Any]:
        if provider is not None and config_path is not None:
            raise TaskSyncError(
                "tasks.sync.config_conflict: specify either --config or --provider"
            )
        if provider is not None:
            return self._normalise_provider_config(provider)
        return self._load_provider_config(config_path)

    def _load_provider_config(self, config_path: Path | None) -> Dict[str, Any]:
        if config_path is None:
            config_path = self._root / "config" / "tasks.provider.json"
        if not config_path.exists():
            raise TaskSyncError(
                f"tasks.sync.config_not_found: provider config missing at {config_path}"
            )
        try:
            raw_config = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise TaskSyncError(f"tasks.sync.config_invalid: {exc}") from exc
        return self._normalise_provider_config(raw_config)

    def _normalise_provider_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(config, dict):
            raise TaskSyncError("tasks.sync.config_invalid: root must be object")
        data: Dict[str, Any] = dict(config)
        provider_type = data.get("type")
        if not isinstance(provider_type, str) or not provider_type.strip():
            raise TaskSyncError("tasks.sync.config_invalid: missing type")
        options = data.get("options")
        if options is None:
            options = {}
        if not isinstance(options, dict):
            raise TaskSyncError("tasks.sync.config_invalid: options must be object")
        data["type"] = provider_type.strip()
        data["options"] = dict(options)
        return data

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

    def _write_mission_artifacts(self, report_payload: Dict[str, Any], report_path: Path) -> None:
        mission_dir = self._root / "reports" / "tasks"
        mission_dir.mkdir(parents=True, exist_ok=True)

        summary = {
            "generated_at": report_payload.get("generated_at"),
            "provider": report_payload.get("provider", {}),
            "summary": report_payload.get("summary", {}),
            "applied": report_payload.get("applied", False),
            "report": str(report_path.relative_to(self._root)),
        }
        actions = report_payload.get("actions")
        if isinstance(actions, list):
            summary["actions"] = actions[:10]

        latest_path = mission_dir / "sync.json"
        latest_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        history_dir = mission_dir / "history"
        history_dir.mkdir(parents=True, exist_ok=True)
        timestamp = report_payload.get("generated_at", "unknown")
        slug = self._slugify_timestamp(timestamp)
        candidate = history_dir / f"{slug}.json"
        counter = 1
        while candidate.exists():
            candidate = history_dir / f"{slug}_{counter}.json"
            counter += 1
        candidate.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    @staticmethod
    def _slugify_timestamp(timestamp: str) -> str:
        if not timestamp:
            return "unknown"
        slug = timestamp.replace(":", "").replace("-", "").replace(" ", "_")
        return slug.replace("/", "_")


def _relativize(path: Path, base: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)
