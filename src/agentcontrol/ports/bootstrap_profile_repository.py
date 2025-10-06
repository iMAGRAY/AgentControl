"""Port definition for persisting bootstrap profiles."""

from __future__ import annotations

from abc import ABC, abstractmethod

from agentcontrol.domain.bootstrap import BootstrapProfileSnapshot
from agentcontrol.domain.project import ProjectId


class BootstrapProfileRepository(ABC):
    """Abstraction over storage for bootstrap profile snapshots."""

    @abstractmethod
    def save(self, project_id: ProjectId, snapshot: BootstrapProfileSnapshot) -> None:
        """Persist the snapshot for the given project."""

    @abstractmethod
    def load(self, project_id: ProjectId) -> BootstrapProfileSnapshot | None:
        """Return the stored snapshot if present."""


__all__ = ["BootstrapProfileRepository"]
