"""Value objects describing MCP server configuration."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict

_NAME_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9_-]{0,63})$", re.IGNORECASE)


@dataclass(frozen=True)
class MCPServerConfig:
    """Immutable configuration for a registered MCP server."""

    name: str
    endpoint: str
    description: str | None = None
    metadata: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _NAME_PATTERN.match(self.name):
            raise ValueError(
                "MCP server name must be alphanumeric with optional hyphen/underscore and <=64 chars",
            )
        if not self.endpoint.strip():
            raise ValueError("MCP server endpoint must be a non-empty string")
        normalised = {str(k): str(v) for k, v in self.metadata.items()}
        object.__setattr__(self, "metadata", normalised)

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "name": self.name,
            "endpoint": self.endpoint,
        }
        if self.description:
            payload["description"] = self.description
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MCPServerConfig":
        return cls(
            name=str(data["name"]),
            endpoint=str(data["endpoint"]),
            description=data.get("description"),
            metadata={k: str(v) for k, v in (data.get("metadata") or {}).items()},
        )

    def filename(self) -> str:
        return f"{self.name}.yaml"
