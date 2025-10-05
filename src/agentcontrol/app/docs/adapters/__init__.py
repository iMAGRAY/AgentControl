"""External documentation adapters for AgentControl."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Mapping, Optional

from agentcontrol.domain.docs.value_objects import SectionConfig


@dataclass
class AdapterAction:
    name: str
    path: Optional[Path]
    action: str


class ExternalAdapter:
    """Base interface for docs bridge external adapters."""

    def diff(self, project_root: Path, spec: SectionConfig, expected: Mapping[str, object] | None) -> List[Dict[str, object]]:
        raise NotImplementedError

    def apply(
        self,
        project_root: Path,
        spec: SectionConfig,
        expected: Mapping[str, object] | None,
        backup_root: Path,
    ) -> List[AdapterAction]:
        raise NotImplementedError

    def capture(self, project_root: Path, spec: SectionConfig) -> Dict[str, object]:
        raise NotImplementedError

    def rollback(self, project_root: Path, spec: SectionConfig, backup_root: Path) -> List[AdapterAction]:
        raise NotImplementedError
