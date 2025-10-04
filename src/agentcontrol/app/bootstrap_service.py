"""Application services for project bootstrap and upgrade."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from agentcontrol.domain.project import (
    PROJECT_DIR,
    ProjectCapsule,
    ProjectId,
    ProjectNotInitialisedError,
    project_settings_hash,
)
from agentcontrol.domain.template import TemplateDescriptor
from agentcontrol.ports.template_repo import TemplateRepository
from agentcontrol.settings import RuntimeSettings


class BootstrapService:
    def __init__(self, template_repo: TemplateRepository, settings: RuntimeSettings) -> None:
        self._templates = template_repo
        self._settings = settings

    def bootstrap(
        self,
        project_id: ProjectId,
        channel: str,
        *,
        template: str = "default",
        force: bool = False,
    ) -> None:
        target_root = project_id.root
        target_root.mkdir(parents=True, exist_ok=True)
        descriptor = project_id.descriptor_path()
        if descriptor.exists() and not force:
            raise RuntimeError(
                "Project already initialised. Use --force or agentcall upgrade."
            )
        template_descriptor = self._templates.ensure_available(
            self._settings.cli_version, channel, template
        )
        self._copy_template(template_descriptor, target_root, force=force)
        capsule = ProjectCapsule(
            project_id=project_id,
            template_version=template_descriptor.version,
            channel=channel,
            template_name=template_descriptor.template,
            settings_hash=project_settings_hash(
                template_descriptor.version, channel, template_descriptor.template
            ),
            metadata={"created_with": self._settings.cli_version},
        )
        capsule.store()
        self._register_project(capsule)

    def upgrade(self, project_id: ProjectId, channel: str, template: str | None = None) -> None:
        try:
            existing = ProjectCapsule.load(project_id)
        except (ProjectNotInitialisedError, FileNotFoundError) as exc:
            raise RuntimeError("Project not initialised; run agentcall init first.") from exc
        template_name = template or existing.template_name
        template_descriptor = self._templates.ensure_available(
            self._settings.cli_version, channel, template_name
        )
        self._copy_template(template_descriptor, project_id.root, force=True)
        capsule = ProjectCapsule(
            project_id=project_id,
            template_version=template_descriptor.version,
            channel=channel,
            template_name=template_descriptor.template,
            settings_hash=project_settings_hash(
                template_descriptor.version, channel, template_descriptor.template
            ),
            metadata=existing.metadata,
        )
        capsule.store()
        self._register_project(capsule)

    def _copy_template(self, template: TemplateDescriptor, destination: Path, *, force: bool) -> None:
        template.validate()
        capsule_src = template.root_dir / PROJECT_DIR
        if not capsule_src.exists():
            raise RuntimeError("Template missing agentcontrol capsule")
        capsule_dst = destination / PROJECT_DIR
        if capsule_dst.exists():
            if force:
                shutil.rmtree(capsule_dst)
            elif any(capsule_dst.iterdir()):
                raise RuntimeError("AgentControl capsule already exists; use agentcall upgrade.")
        capsule_dst.mkdir(parents=True, exist_ok=True)
        self._copy_tree(capsule_src, capsule_dst, force=force)

        legacy_entries = [p for p in template.root_dir.iterdir() if p.name not in {PROJECT_DIR}]
        for entry in legacy_entries:
            target = capsule_dst / entry.name
            if entry.name == "template.sha256":
                target = capsule_dst / "template.sha256"
            if entry.is_dir():
                self._copy_tree(entry, target, force=force)
            else:
                self._copy_file(entry, target, force=force)

    def _copy_tree(self, source: Path, destination: Path, *, force: bool) -> None:
        if destination.exists():
            if force:
                shutil.rmtree(destination)
            else:
                shutil.copytree(source, destination, dirs_exist_ok=True)
                return
        shutil.copytree(source, destination)

    def _copy_file(self, source: Path, destination: Path, *, force: bool) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() and not force:
            return
        if destination.exists():
            if destination.is_dir():
                shutil.rmtree(destination)
            else:
                destination.unlink()
        shutil.copy2(source, destination)

    def _register_project(self, capsule: ProjectCapsule) -> None:
        registry = self._settings.project_registry_file
        registry.parent.mkdir(parents=True, exist_ok=True)
        data: dict[str, Any]
        if registry.exists():
            data = json.loads(registry.read_text("utf-8"))
        else:
            data = {}
        data[str(capsule.project_id.root)] = {
            "template_version": capsule.template_version,
            "channel": capsule.channel,
            "settings_hash": capsule.settings_hash,
            "template": capsule.template_name,
        }
        registry.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

    def ensure_bootstrap_prerequisites(self) -> None:
        self._settings.home_dir.mkdir(parents=True, exist_ok=True)
        self._settings.template_dir.mkdir(parents=True, exist_ok=True)
        self._settings.state_dir.mkdir(parents=True, exist_ok=True)
