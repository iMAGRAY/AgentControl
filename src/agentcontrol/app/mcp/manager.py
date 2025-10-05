"""Application service for managing MCP server registrations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List

from agentcontrol.domain.mcp import MCPConfigRepository, MCPServerConfig


@dataclass
class MCPManager:
    """Coordinates persistence and validation of MCP server configs."""

    repository: MCPConfigRepository

    def add(self, config: MCPServerConfig, *, overwrite: bool = False) -> Path:
        return self.repository.save(config, overwrite=overwrite)

    def remove(self, name: str) -> bool:
        return self.repository.remove(name)

    def list(self) -> List[MCPServerConfig]:
        return self.repository.list()

    @classmethod
    def for_project(cls, project_root: Path) -> "MCPManager":
        return cls(MCPConfigRepository(project_root))
