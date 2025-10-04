"""Filesystem-backed template repository."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from agentcontrol.domain.template import TemplateDescriptor
from agentcontrol.ports.template_repo import TemplateNotFoundError, TemplateRepository


class FSTemplateRepository(TemplateRepository):
    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def ensure_available(self, version: str, channel: str, template: str) -> TemplateDescriptor:
        channel_dir = self._base_dir / channel
        version_dir = channel_dir / version
        if not version_dir.exists():
            candidates = sorted([p for p in channel_dir.iterdir() if p.is_dir()]) if channel_dir.exists() else []
            if not candidates:
                raise TemplateNotFoundError(f"No templates installed for channel {channel}")
            version_dir = candidates[-1]
            version = version_dir.name

        root = version_dir / template
        if not root.exists():
            candidates = sorted((p for p in channel_dir.iterdir() if p.is_dir())) if channel_dir.exists() else []
            for candidate in reversed(candidates):
                alt_root = candidate / template
                alt_checksum = alt_root / "template.sha256"
                if alt_root.exists() and alt_checksum.exists():
                    version_dir = candidate
                    version = candidate.name
                    root = alt_root
                    checksum = alt_checksum
                    break
            else:
                checksum = root / "template.sha256"
        else:
            checksum = root / "template.sha256"
        if not root.exists() or not checksum.exists():
            raise TemplateNotFoundError(
                f"Template {template} {version} ({channel}) not found under {root}"
            )
        return TemplateDescriptor(
            version=version,
            channel=channel,
            template=template,
            root_dir=root,
            checksum_file=checksum,
        )

    def install_from_directory(self, source: Path) -> TemplateDescriptor:
        raise NotImplementedError("Installing templates dynamically is not yet supported.")

    def list_versions(self) -> Iterable[str]:
        if not self._base_dir.exists():
            return []
        versions: set[str] = set()
        for channel_dir in self._base_dir.iterdir():
            if not channel_dir.is_dir():
                continue
            for version_dir in channel_dir.iterdir():
                if version_dir.is_dir():
                    versions.add(version_dir.name)
        return sorted(versions)
