"""Collects capability metadata for `agentcall info`."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

from agentcontrol import __version__
from agentcontrol.app.docs.operations import available_external_adapters
from agentcontrol.app.mission.service import MissionService


@dataclass
class InfoPayload:
    data: Dict[str, Any]


class InfoService:
    """Aggregates runtime and capability data."""

    def collect(self, project_path: Path | None = None) -> InfoPayload:
        adapters = available_external_adapters()
        mission_summary = self._mission_snapshot(project_path) if project_path else None
        payload: Dict[str, Any] = {
            "version": __version__,
            "features": {
                "docs": {
                    "commands": ["diagnose", "info", "list", "diff", "repair", "adopt", "rollback"],
                    "externalAdapters": adapters,
                },
                "mission": {
                    "commands": ["summary", "ui"],
                },
                "telemetry": {
                    "schema": "agentcontrol://schemas/telemetry.schema.json",
                    "levels": ["info", "warn", "error"],
                },
            },
        }
        if mission_summary is not None:
            payload["mission"] = mission_summary
        return InfoPayload(payload)

    def _mission_snapshot(self, project_path: Path) -> Dict[str, Any]:
        service = MissionService()
        result = service.persist_twin(project_path)
        return {
            "twinPath": str(result.path),
            "program": result.twin.get("program", {}),
            "docsBridge": result.twin.get("docsBridge", {}),
        }
