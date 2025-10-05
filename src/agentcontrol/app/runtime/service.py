"""Runtime manifest builder and telemetry streaming helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable

import yaml

from agentcontrol import __version__
from agentcontrol.app.command_service import CommandRegistry
from agentcontrol.domain.project import ProjectId
from agentcontrol.settings import SETTINGS
from agentcontrol.utils.telemetry import iter_events


@dataclass(frozen=True)
class RuntimeManifest:
    data: Dict[str, Any]
    path: Path


class RuntimeService:
    """Generates runtime metadata and exposes telemetry streams."""

    def build_manifest(self, project_root: Path) -> RuntimeManifest:
        project_id = ProjectId.from_existing(project_root)
        descriptor_path = project_id.command_descriptor_path()
        registry = CommandRegistry.load_from_file(descriptor_path)
        commands = list(registry.list_commands())
        manifest = {
            "version": __version__,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "project": str(project_root.resolve()),
            "commands": commands,
            "telemetry": {
                "schema": "agentcontrol://schemas/telemetry.schema.json",
                "log": str((SETTINGS.log_dir / "telemetry.jsonl")),
            },
            "paths": {
                "docs_config": ".agentcontrol/config/docs.bridge.yaml",
                "mcp_dir": ".agentcontrol/config/mcp",
            },
        }
        runtime_path = project_root / ".agentcontrol" / "runtime.json"
        runtime_path.parent.mkdir(parents=True, exist_ok=True)
        runtime_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return RuntimeManifest(manifest, runtime_path)

    def iter_telemetry(self, settings: SETTINGS.__class__ = SETTINGS) -> Iterable[dict[str, Any]]:
        return iter_events(settings)


def load_runtime_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8") as fh:
        if path.suffix in {".yaml", ".yml"}:
            return yaml.safe_load(fh)
        return json.load(fh)
