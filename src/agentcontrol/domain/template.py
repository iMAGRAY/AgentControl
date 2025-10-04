"""Domain model for template bundles stored on disk."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TemplateDescriptor:
    version: str
    channel: str
    template: str
    root_dir: Path
    checksum_file: Path

    def validate(self) -> None:
        if not self.root_dir.exists():
            raise FileNotFoundError(f"Template directory missing: {self.root_dir}")
        if not self.checksum_file.exists():
            raise FileNotFoundError(f"Checksum file missing: {self.checksum_file}")

    def checksum(self) -> str:
        return self.checksum_file.read_text("utf-8").strip()
