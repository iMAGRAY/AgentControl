"""Application service orchestrating sandbox lifecycle operations."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable

from agentcontrol.adapters.fs_template_repo import FSTemplateRepository
from agentcontrol.domain.sandbox import SandboxAggregate, SandboxContext, SandboxDescriptor
from agentcontrol.domain.template import TemplateDescriptor
from agentcontrol.settings import RuntimeSettings


class SandboxServiceError(RuntimeError):
    """Raised when sandbox operations cannot proceed."""


@dataclass
class SandboxService:
    """High-level operations for developer sandboxes."""

    template_repo: FSTemplateRepository
    settings: RuntimeSettings

    def start(
        self,
        project_root: Path,
        *,
        template: str | None = None,
        metadata: Dict[str, object] | None = None,
        minimal: bool = False,
    ) -> SandboxDescriptor:
        project_root = project_root.resolve()
        aggregate = SandboxAggregate(SandboxContext(project_root))
        template_name = template or "sandbox"
        descriptor = self._load_template(template_name)

        def materialise(target: Path) -> None:
            self._copy_template(descriptor, target)
            if minimal:
                self._strip_sample_assets(target)

        return aggregate.create(template_name, materialise, metadata=metadata)

    def list(self, project_root: Path) -> Iterable[SandboxDescriptor]:
        aggregate = SandboxAggregate(SandboxContext(project_root.resolve()))
        return aggregate.list()

    def purge(self, project_root: Path, sandbox_id: str | None = None) -> Iterable[SandboxDescriptor]:
        aggregate = SandboxAggregate(SandboxContext(project_root.resolve()))
        if sandbox_id is None:
            return list(aggregate.purge_all())
        descriptor = aggregate.remove(sandbox_id)
        return [descriptor] if descriptor else []

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _load_template(self, template_name: str) -> TemplateDescriptor:
        try:
            return self.template_repo.ensure_available(self.settings.cli_version, "stable", template_name)
        except Exception as exc:  # pragma: no cover - defensive, template repo tested separately
            raise SandboxServiceError(f"Template '{template_name}' unavailable: {exc}") from exc

    def _copy_template(self, template: TemplateDescriptor, destination: Path) -> None:
        if destination.exists() and any(destination.iterdir()):
            raise SandboxServiceError(f"Sandbox directory {destination} already populated")
        shutil.copytree(template.root_dir, destination, dirs_exist_ok=True)

    def _strip_sample_assets(self, root: Path) -> None:
        # Remove large sample directories to provide a lean sandbox when requested.
        docs_samples = root / "docs" / "samples"
        if docs_samples.exists():
            shutil.rmtree(docs_samples, ignore_errors=True)
        sample_repos = root / "examples"
        if sample_repos.exists():
            shutil.rmtree(sample_repos, ignore_errors=True)


__all__ = ["SandboxService", "SandboxServiceError"]
