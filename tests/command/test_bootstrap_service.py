from __future__ import annotations

import json
from pathlib import Path

from agentcontrol.adapters.fs_template_repo import FSTemplateRepository
from agentcontrol.app.bootstrap_service import BootstrapService
from agentcontrol.domain.project import ProjectId
from agentcontrol.settings import RuntimeSettings


def _make_settings(tmp_path: Path) -> RuntimeSettings:
    home = tmp_path / "home"
    template_dir = tmp_path / "templates"
    state_dir = tmp_path / "state"
    log_dir = tmp_path / "logs"
    for directory in (home, template_dir, state_dir, log_dir):
        directory.mkdir(parents=True, exist_ok=True)
    return RuntimeSettings(home_dir=home, template_dir=template_dir, state_dir=state_dir, log_dir=log_dir, cli_version="0.2.0")


def _seed_template(template_dir: Path, name: str) -> None:
    root = template_dir / "stable" / "0.2.0" / name
    root.mkdir(parents=True, exist_ok=True)
    (root / "template.json").write_text(
        json.dumps({"version": "0.2.0", "channel": "stable", "template": name}),
        encoding="utf-8",
    )
    (root / "template.sha256").write_text("dummy\n", encoding="utf-8")
    (root / "agentcall.yaml").write_text("commands: {}\n", encoding="utf-8")
    agent_dir = root / "agentcontrol"
    (agent_dir / "scripts").mkdir(parents=True, exist_ok=True)
    (agent_dir / "scripts" / "dummy.sh").write_text('#!/usr/bin/env bash\necho dummy\n', encoding="utf-8")


def test_bootstrap_persists_template(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    repo = FSTemplateRepository(settings.template_dir)
    _seed_template(settings.template_dir, "python")

    service = BootstrapService(repo, settings)
    project_id = ProjectId.for_new_project(tmp_path / "proj")
    service.bootstrap(project_id, "stable", template="python")

    descriptor = project_id.descriptor_path()
    data = json.loads(descriptor.read_text(encoding="utf-8"))
    assert data["template"] == "python"
    assert (project_id.root / "agentcontrol" / "agentcall.yaml").exists()
    assert not (project_id.root / "agentcall.yaml").exists()


def test_upgrade_keeps_template_when_not_overridden(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    repo = FSTemplateRepository(settings.template_dir)
    for name in ("default", "python"):
        _seed_template(settings.template_dir, name)

    service = BootstrapService(repo, settings)
    project_root = tmp_path / "proj"
    project_id = ProjectId.for_new_project(project_root)
    service.bootstrap(project_id, "stable", template="default")

    service.upgrade(project_id, "stable")
    data = json.loads(project_id.descriptor_path().read_text("utf-8"))
    assert data["template"] == "default"
