"""Value objects representing sandbox metadata."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


@dataclass(frozen=True)
class SandboxDescriptor:
    """Descriptor describing a provisioned sandbox workspace."""

    sandbox_id: str
    path: Path
    template: str
    created_at: str
    status: str = "ready"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sandbox_id": self.sandbox_id,
            "path": self.path.as_posix(),
            "template": self.template,
            "created_at": self.created_at,
            "status": self.status,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SandboxDescriptor":
        return cls(
            sandbox_id=data["sandbox_id"],
            path=Path(data["path"]).resolve(),
            template=data["template"],
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
            status=data.get("status", "ready"),
            metadata=dict(data.get("metadata", {})),
        )


__all__ = ["SandboxDescriptor"]
