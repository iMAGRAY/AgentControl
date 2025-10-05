"""Persistence adapter for sandbox descriptors."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List

from .value_objects import SandboxDescriptor


class SandboxRegistry:
    """Stores sandbox descriptors under a project capsule."""

    def __init__(self, registry_path: Path) -> None:
        self._path = registry_path
        self._entries: Dict[str, SandboxDescriptor] = {}
        self._load()

    @property
    def path(self) -> Path:
        return self._path

    def list(self) -> List[SandboxDescriptor]:
        return list(self._entries.values())

    def get(self, sandbox_id: str) -> SandboxDescriptor | None:
        return self._entries.get(sandbox_id)

    def save(self, descriptor: SandboxDescriptor) -> None:
        self._entries[descriptor.sandbox_id] = descriptor
        self._persist()

    def remove(self, sandbox_id: str) -> SandboxDescriptor | None:
        descriptor = self._entries.pop(sandbox_id, None)
        if descriptor is not None:
            self._persist()
        return descriptor

    def _load(self) -> None:
        if not self._path.exists():
            self._path.parent.mkdir(parents=True, exist_ok=True)
            return
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        entries = raw.get("sandboxes", []) if isinstance(raw, dict) else []
        for item in entries:
            descriptor = SandboxDescriptor.from_dict(item)
            self._entries[descriptor.sandbox_id] = descriptor

    def _persist(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "sandboxes": [descriptor.to_dict() for descriptor in self._entries.values()],
        }
        self._path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


__all__ = ["SandboxRegistry"]
