from __future__ import annotations

from pathlib import Path
import json

from agentcontrol.adapters.fs_template_repo import FSTemplateRepository
from agentcontrol.app.sandbox.service import SandboxService
from agentcontrol.settings import RuntimeSettings


def make_runtime_settings(base: Path) -> RuntimeSettings:
    home = base / "home"
    template_dir = base / "templates"
    state_dir = base / "state"
    log_dir = base / "logs"
    for directory in (home, template_dir, state_dir, log_dir):
        directory.mkdir(parents=True, exist_ok=True)
    return RuntimeSettings(
        home_dir=home,
        template_dir=template_dir,
        state_dir=state_dir,
        log_dir=log_dir,
        cli_version="0.1.0",
    )


def seed_template(base: Path) -> None:
    template_root = base / "stable" / "0.1.0" / "sandbox"
    (template_root / "docs" / "samples").mkdir(parents=True, exist_ok=True)
    (template_root / "examples").mkdir(parents=True, exist_ok=True)
    (template_root / "docs" / "samples" / "demo.md").write_text("demo", encoding="utf-8")
    (template_root / "README.md").write_text("sandbox", encoding="utf-8")
    (template_root / "template.sha256").write_text("dummy\n", encoding="utf-8")
    (template_root / "template.json").write_text(json.dumps({"version": "0.1.0", "channel": "stable", "template": "sandbox"}, indent=2) + "\n", encoding="utf-8")
    (template_root / ".agentcontrol").mkdir(parents=True, exist_ok=True)


def test_sandbox_service_minimal(tmp_path: Path) -> None:
    settings = make_runtime_settings(tmp_path)
    seed_template(settings.template_dir)
    repo = FSTemplateRepository(settings.template_dir)
    service = SandboxService(repo, settings)

    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)

    descriptor = service.start(project_root, template="sandbox", minimal=True)

    assert descriptor.path.exists()
    assert not (descriptor.path / "docs" / "samples").exists()
    assert not (descriptor.path / "examples").exists()
    assert (descriptor.path / "README.md").exists()
