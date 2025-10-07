"""File-based task provider adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List

from agentcontrol.adapters.tasks.utils import read_snapshot
from agentcontrol.domain.tasks import TaskRecord, TaskRecordError
from agentcontrol.ports.tasks.provider import TaskProvider, TaskProviderError


class FileTaskProvider(TaskProvider):
    def __init__(self, project_root: Path, options: Dict[str, Any]) -> None:
        raw_path = options.get("path")
        if not raw_path:
            raise TaskProviderError("file provider requires 'path'")
        self._root = project_root
        self._path = str(raw_path)

        encryption_opts = options.get("encryption")
        if encryption_opts is not None and not isinstance(encryption_opts, dict):
            raise TaskProviderError("file provider encryption must be object")
        if encryption_opts:
            mode = encryption_opts.get("mode", "xor")
            if not isinstance(mode, str) or not mode:
                raise TaskProviderError("file provider encryption.mode must be string")
            self._encryption_mode = mode.lower()
            self._encryption_key = encryption_opts.get("key")
            self._encryption_key_env = encryption_opts.get("key_env")
        elif options.get("encrypted"):
            self._encryption_mode = "xor"
            self._encryption_key = options.get("key")
            self._encryption_key_env = options.get("key_env")
        else:
            self._encryption_mode = None
            self._encryption_key = None
            self._encryption_key_env = None

    def fetch(self) -> Iterable[TaskRecord]:
        payload = read_snapshot(
            self._resolve_path(self._path),
            mode=self._encryption_mode,
            key=self._encryption_key,
            key_env=self._encryption_key_env,
        )
        tasks_payload: List[dict[str, Any]]
        if isinstance(payload, dict):
            data = payload.get("tasks")
            if not isinstance(data, list):
                raise TaskProviderError("provider payload missing 'tasks' list")
            tasks_payload = data
        elif isinstance(payload, list):
            tasks_payload = payload
        else:
            raise TaskProviderError("provider payload must be an object or list")

        tasks: List[TaskRecord] = []
        for entry in tasks_payload:
            if not isinstance(entry, dict):
                raise TaskProviderError("each provider task must be an object")
            task_id = entry.get("id")
            if not task_id:
                raise TaskProviderError("provider task missing id")
            data = {k: v for k, v in entry.items() if k != "id"}
            try:
                tasks.append(TaskRecord(str(task_id), data))
            except TaskRecordError as exc:
                raise TaskProviderError(str(exc)) from exc
        return tasks

    def _resolve_path(self, raw: str) -> str:
        candidate = Path(raw)
        if candidate.is_absolute():
            return str(candidate)
        return str((self._root / candidate).resolve())
