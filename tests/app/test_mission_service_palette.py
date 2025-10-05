from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from agentcontrol.app.mission.service import MissionService


def _seed_project(project: Path) -> None:
    config_dir = project / ".agentcontrol" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "docs.bridge.yaml").write_text(
        "\n".join(
            [
                "version: 1",
                "root: docs",
                "sections:",
                "  architecture_overview:",
                "    mode: managed",
                "    target: architecture/overview.md",
                "    marker: agentcontrol-architecture-overview",
                "  adr_index:",
                "    mode: managed",
                "    target: adr/index.md",
                "    marker: agentcontrol-adr-index",
                "  rfc_index:",
                "    mode: managed",
                "    target: rfc/index.md",
                "    marker: agentcontrol-rfc-index",
                "  adr_entry:",
                "    mode: file",
                "    target_template: adr/{id}.md",
                "  rfc_entry:",
                "    mode: file",
                "    target_template: rfc/{id}.md",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    docs = project / "docs" / "architecture"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "overview.md").write_text(
        "<!-- agentcontrol:start:agentcontrol-architecture-overview -->\nDrifted content\n<!-- agentcontrol:end:agentcontrol-architecture-overview -->\n",
        encoding="utf-8",
    )
    (project / "docs" / "adr").mkdir(parents=True, exist_ok=True)
    (project / "docs" / "rfc").mkdir(parents=True, exist_ok=True)
    (project / "docs" / "adr" / "index.md").write_text(
        "<!-- agentcontrol:start:agentcontrol-adr-index -->\nSeed\n<!-- agentcontrol:end:agentcontrol-adr-index -->\n",
        encoding="utf-8",
    )
    (project / "docs" / "rfc" / "index.md").write_text(
        "<!-- agentcontrol:start:agentcontrol-rfc-index -->\nSeed\n<!-- agentcontrol:end:agentcontrol-rfc-index -->\n",
        encoding="utf-8",
    )

    manifest_dir = project / ".agentcontrol" / "architecture"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "manifest.yaml").write_text("program: {}\ntasks: []\n", encoding="utf-8")


def test_mission_service_generates_palette_and_executes_actions(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir(parents=True, exist_ok=True)
    _seed_project(project)

    service = MissionService()
    twin = service.build_twin(project)
    assert twin["palette"]
    palette_ids = {entry["id"] for entry in twin["palette"]}
    assert "mission:exec" in palette_ids
    assert any(entry["type"] == "playbook" for entry in twin["palette"])

    palette_path = service.persist_palette(project, twin["palette"])
    assert palette_path.exists()
    persisted = json.loads(palette_path.read_text(encoding="utf-8"))
    assert persisted["entries"]

    docs_path = project / "docs" / "architecture" / "overview.md"
    with patch.object(service, "build_twin", return_value=twin), patch.object(
        service._docs_command_service,
        "sync_sections",
        return_value={"status": "ok"},
    ):
        result = service.execute_action(project, {"kind": "docs_sync"})
    assert result.status == "success"
    content = docs_path.read_text(encoding="utf-8")
    assert "agentcontrol:start:agentcontrol-architecture-overview" in content
