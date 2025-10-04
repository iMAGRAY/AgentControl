"""Port definitions for template storage."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterable

from agentcontrol.domain.template import TemplateDescriptor


class TemplateNotFoundError(RuntimeError):
    pass


class TemplateRepository(ABC):
    @abstractmethod
    def ensure_available(self, version: str, channel: str, template: str) -> TemplateDescriptor:
        """Return template descriptor for given version/channel/template."""

    @abstractmethod
    def install_from_directory(self, source: Path) -> TemplateDescriptor:
        """Install template bundle from source directory."""

    @abstractmethod
    def list_versions(self) -> Iterable[str]:
        """List available template versions."""
