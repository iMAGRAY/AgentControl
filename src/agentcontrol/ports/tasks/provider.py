"""Ports for task provider integrations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable

from agentcontrol.domain.tasks import TaskRecord


class TaskProvider(ABC):
    """Abstract provider that returns tasks from an external system."""

    @abstractmethod
    def fetch(self) -> Iterable[TaskRecord]:
        """Retrieve tasks for synchronisation."""


class TaskProviderError(RuntimeError):
    """Raised when a provider fails to supply a valid payload."""
