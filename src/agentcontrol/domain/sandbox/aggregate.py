"""Aggregate coordinating sandbox lifecycle operations."""

from __future__ import annotations

import secrets
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Iterable

from .registry import SandboxRegistry
from .value_objects import SandboxDescriptor


MaterialiseFn = Callable[[Path], None]


@dataclass(frozen=True)
class SandboxContext:
    project_root: Path

    @property
    def sandbox_root(self) -> Path:
        return self.project_root / ".agentcontrol" / "sandbox"

    @property
    def registry_path(self) -> Path:
        return self.project_root / ".agentcontrol" / "state" / "sandbox" / "index.json"


class SandboxAggregate:
    """Implements invariants around sandbox provisioning."""

    def __init__(self, context: SandboxContext) -> None:
        self._context = context
        self._registry = SandboxRegistry(context.registry_path)
        self._context.sandbox_root.mkdir(parents=True, exist_ok=True)

    def create(self, template: str, materialise: MaterialiseFn, *, metadata: Dict[str, object] | None = None) -> SandboxDescriptor:
        sandbox_id = self._generate_id()
        target = self._context.sandbox_root / sandbox_id
        if target.exists():  # extremely unlikely collision; regenerate id
            sandbox_id = self._generate_id()
            target = self._context.sandbox_root / sandbox_id
        target.mkdir(parents=True, exist_ok=False)
        try:
            materialise(target)
        except Exception:
            if target.exists():
                shutil.rmtree(target)
            raise

        descriptor = SandboxDescriptor(
            sandbox_id=sandbox_id,
            path=target.resolve(),
            template=template,
            created_at=datetime.now(timezone.utc).isoformat(),
            metadata=dict(metadata or {}),
        )
        self._registry.save(descriptor)
        return descriptor

    def list(self) -> Iterable[SandboxDescriptor]:
        return self._registry.list()

    def remove(self, sandbox_id: str, *, delete_files: bool = True) -> SandboxDescriptor | None:
        descriptor = self._registry.remove(sandbox_id)
        if descriptor and delete_files:
            shutil.rmtree(descriptor.path, ignore_errors=True)
        return descriptor

    def purge_all(self, *, delete_files: bool = True) -> Iterable[SandboxDescriptor]:
        snapshots = list(self._registry.list())
        for descriptor in snapshots:
            self.remove(descriptor.sandbox_id, delete_files=delete_files)
        return snapshots

    def _generate_id(self) -> str:
        # 12 hex chars ~ 4.5e14 combinations, enough to avoid collisions.
        return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3)


__all__ = ["SandboxAggregate", "SandboxContext"]
