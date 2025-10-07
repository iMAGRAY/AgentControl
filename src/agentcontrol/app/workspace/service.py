"""Services for workspace.yaml descriptors and aggregation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import yaml

from agentcontrol.app.mission.service import MissionService
from agentcontrol.domain.project import ProjectId, ProjectNotInitialisedError

WORKSPACE_FILENAME = "workspace.yaml"


class WorkspaceError(RuntimeError):
    """Raised when workspace descriptor is invalid."""


@dataclass(frozen=True)
class WorkspaceEntry:
    project_id: str
    name: str
    path: Path
    tags: List[str]
    description: Optional[str] = None

    def to_dict(self) -> Dict[str, object]:
        return {
            "id": self.project_id,
            "name": self.name,
            "path": str(self.path),
            "tags": self.tags,
            "description": self.description,
        }


class WorkspaceService:
    """Load workspace descriptors and aggregate mission summaries."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._descriptor_path = self._root / WORKSPACE_FILENAME

    def load_descriptor(self) -> List[WorkspaceEntry]:
        if not self._descriptor_path.exists():
            raise WorkspaceError(f"workspace descriptor not found: {self._descriptor_path}")
        try:
            payload = yaml.safe_load(self._descriptor_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:  # pragma: no cover - upstream message
            raise WorkspaceError(f"workspace descriptor invalid YAML: {exc}") from exc
        if not isinstance(payload, dict):
            raise WorkspaceError("workspace descriptor must be a mapping")
        version = payload.get("version")
        if version not in {1, "1", "1.0", "1.0.0"}:
            raise WorkspaceError("workspace version must be 1")
        raw_projects = payload.get("projects")
        if not isinstance(raw_projects, list) or not raw_projects:
            raise WorkspaceError("workspace requires non-empty 'projects' list")
        entries: List[WorkspaceEntry] = []
        seen: set[str] = set()
        for raw in raw_projects:
            entry = self._parse_entry(raw)
            if entry.project_id in seen:
                raise WorkspaceError(f"duplicate project id '{entry.project_id}' in workspace")
            seen.add(entry.project_id)
            entries.append(entry)
        return entries

    def summarise(self) -> Dict[str, object]:
        entries = self.load_descriptor()
        mission = MissionService()
        summaries: List[Dict[str, object]] = []
        for entry in entries:
            try:
                project_id = ProjectId.from_existing(entry.path)
            except ProjectNotInitialisedError:
                project_id = ProjectId.for_new_project(entry.path)
            twin = mission.build_twin(project_id.root)
            program = twin.get("program", {})
            program_info = program.get("program", {}) if isinstance(program, dict) else {}
            quality = twin.get("quality", {})
            verify_info = quality.get("verify", {}) if isinstance(quality, dict) else {}
            summaries.append(
                {
                    "id": entry.project_id,
                    "name": entry.name,
                    "path": str(entry.path),
                    "tags": entry.tags,
                    "description": entry.description,
                    "program": program_info,
                    "tasks": program.get("tasks", {}) if isinstance(program, dict) else {},
                    "verify": verify_info,
                    "generated_at": twin.get("generated_at"),
                }
            )
        return {
            "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "workspace": str(self._descriptor_path),
            "projects": summaries,
        }

    def _parse_entry(self, raw: object) -> WorkspaceEntry:
        if not isinstance(raw, dict):
            raise WorkspaceError("project entry must be a mapping")
        project_id = str(raw.get("id", "")).strip()
        if not project_id:
            raise WorkspaceError("project entry missing 'id'")
        name = str(raw.get("name", "")).strip() or project_id
        raw_path = raw.get("path", ".")
        if not isinstance(raw_path, str):
            raise WorkspaceError(f"project '{project_id}' path must be string")
        path = (self._root / Path(raw_path)).resolve()
        tags_field = raw.get("tags", [])
        if isinstance(tags_field, list):
            tags = [str(tag).strip() for tag in tags_field if str(tag).strip()]
        elif isinstance(tags_field, str):
            tags = [tag.strip() for tag in tags_field.split(",") if tag.strip()]
        else:
            tags = []
        description = raw.get("description")
        if description is not None:
            description = str(description)
        return WorkspaceEntry(project_id=project_id, name=name, path=path, tags=tags, description=description)


__all__ = ["WorkspaceService", "WorkspaceEntry", "WorkspaceError"]
