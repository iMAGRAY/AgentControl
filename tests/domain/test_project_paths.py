from __future__ import annotations

from pathlib import Path

import pytest

from agentcontrol.domain.project import ProjectId, ProjectNotInitialisedError


def test_command_descriptor_prefers_capsule(tmp_path: Path) -> None:
    project_root = tmp_path / "proj"
    capsule = project_root / ".agentcontrol"
    capsule.mkdir(parents=True)
    (capsule / "agentcall.yaml").write_text("commands: {}\n", encoding="utf-8")
    project_id = ProjectId.for_new_project(project_root)
    resolved = project_id.command_descriptor_path()
    assert resolved == capsule / "agentcall.yaml"


def test_command_descriptor_requires_capsule(tmp_path: Path) -> None:
    project_root = tmp_path / "proj"
    project_root.mkdir(parents=True)
    legacy = project_root / "agentcall.yaml"
    legacy.write_text("commands: {}\n", encoding="utf-8")

    with pytest.raises(ProjectNotInitialisedError):
        ProjectId.from_existing(project_root)
