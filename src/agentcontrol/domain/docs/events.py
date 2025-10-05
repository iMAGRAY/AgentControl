"""Domain events emitted by the documentation bridge aggregate."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class DocsBridgeIssue:
    """Represents a diagnosed inconsistency in documentation synchronisation."""

    severity: str
    code: str
    message: str
    section: Optional[str] = None
    remediation: Optional[str] = None


@dataclass(frozen=True)
class ManagedRegionChange:
    """Captures a managed region update."""

    section: str
    marker: str
    changed: bool
    path: str
