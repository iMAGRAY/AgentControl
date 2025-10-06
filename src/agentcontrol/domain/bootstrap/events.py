"""Domain events for bootstrap profile capture."""

from __future__ import annotations

from dataclasses import dataclass

from .value_objects import BootstrapProfileSnapshot


@dataclass(frozen=True)
class BootstrapProfileCaptured:
    """Emitted when a bootstrap wizard persists a profile snapshot."""

    snapshot: BootstrapProfileSnapshot


__all__ = ["BootstrapProfileCaptured"]
