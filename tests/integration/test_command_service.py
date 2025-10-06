from __future__ import annotations

import os
from pathlib import Path

import pytest

from agentcontrol.app.command_service import CommandService
from agentcontrol.domain.project import COMMAND_DESCRIPTOR, ProjectCapsule, ProjectId, project_settings_hash
from agentcontrol.settings import RuntimeSettings


def _mk_settings(tmp_path: Path) -> RuntimeSettings:
    from agentcontrol.settings import RuntimeSettings as SettingsCls

    home = tmp_path / "home"
    template_dir = tmp_path / "templates"
    state_dir = tmp_path / "state"
    log_dir = tmp_path / "logs"
    for path in (home, template_dir, state_dir, log_dir):
        path.mkdir(parents=True, exist_ok=True)
    return SettingsCls(home_dir=home, template_dir=template_dir, state_dir=state_dir, log_dir=log_dir, cli_version="0.2.0")


def test_command_service_runs_pipeline(tmp_path: Path, monkeypatch) -> None:
    settings = _mk_settings(tmp_path)
    service = CommandService(settings)

    project_root = tmp_path / "proj"
    project_root.mkdir()
    capsule_dir = project_root / ".agentcontrol"
    scripts_dir = capsule_dir / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    script = scripts_dir / "hello.sh"
    script.write_text("#!/usr/bin/env bash\necho 'hi'\n", encoding="utf-8")
    os.chmod(script, 0o755)
    descriptor = capsule_dir / COMMAND_DESCRIPTOR
    descriptor.write_text(
        """
        commands:
          hello:
            steps:
              - name: hello
                exec: ["./.agentcontrol/scripts/hello.sh"]
        """,
        encoding="utf-8",
    )
    project_id = ProjectId.for_new_project(project_root)
    capsule = ProjectCapsule(
        project_id=project_id,
        template_version="0.2.0",
        channel="stable",
        template_name="default",
        settings_hash=project_settings_hash("0.2.0", "stable", "default"),
    )
    capsule.store()
    result = service.run(ProjectId.from_existing(project_root), "hello", [])
    assert result == 0


def test_command_service_missing_executable(tmp_path: Path) -> None:
    settings = _mk_settings(tmp_path)
    service = CommandService(settings)

    project_root = tmp_path / "proj-missing"
    project_root.mkdir()
    capsule_dir = project_root / ".agentcontrol"
    capsule_dir.mkdir(parents=True, exist_ok=True)
    descriptor = capsule_dir / COMMAND_DESCRIPTOR
    descriptor.write_text(
        """
        commands:
          missing:
            steps:
              - name: missing
                exec: ["./.agentcontrol/scripts/not-there.sh"]
        """,
        encoding="utf-8",
    )

    project_id = ProjectId.for_new_project(project_root)
    capsule = ProjectCapsule(
        project_id=project_id,
        template_version="0.2.0",
        channel="stable",
        template_name="default",
        settings_hash=project_settings_hash("0.2.0", "stable", "default"),
    )
    capsule.store()

    with pytest.raises(RuntimeError) as exc:
        service.run(ProjectId.from_existing(project_root), "missing", [])

    assert "missing executable" in str(exc.value)
