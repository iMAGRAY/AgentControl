"""Filesystem repository for MCP server configurations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, List

import yaml

from .value_objects import MCPServerConfig


class MCPConfigRepository:
    """Persists MCP server configs under a project's capsule."""

    def __init__(self, project_root: Path) -> None:
        self._root = project_root.resolve()

    @property
    def base_dir(self) -> Path:
        return self._root / ".agentcontrol" / "config" / "mcp"

    def list(self) -> List[MCPServerConfig]:
        directory = self.base_dir
        if not directory.exists():
            return []
        configs: List[MCPServerConfig] = []
        for path in sorted(directory.glob("*.yaml")):
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            configs.append(MCPServerConfig.from_dict(data))
        return configs

    def save(self, config: MCPServerConfig, *, overwrite: bool = False) -> Path:
        directory = self.base_dir
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / config.filename()
        if target.exists() and not overwrite:
            raise ValueError(f"MCP server '{config.name}' already exists; use --force to overwrite")
        payload = config.to_dict()
        target.write_text(yaml.safe_dump(payload, sort_keys=True, allow_unicode=True), encoding="utf-8")
        return target

    def remove(self, name: str) -> bool:
        target = self.base_dir / f"{name}.yaml"
        if not target.exists():
            return False
        target.unlink()
        return True

    def export(self) -> str:
        """Return a JSON dump of all registered servers."""

        payload = [item.to_dict() for item in self.list()]
        return json.dumps(payload, ensure_ascii=False, indent=2)
