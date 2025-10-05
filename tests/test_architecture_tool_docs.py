from __future__ import annotations

import json
from pathlib import Path

import sys

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.lib import architecture_tool as tool
from agentcontrol.utils import docs_bridge as doc_bridge


def write_manifest(path: Path) -> None:
    manifest = {
        "version": "0.1.0",
        "updated_at": "2025-10-01T00:00:00Z",
        "program": {
            "meta": {
                "program": "v1",
                "program_id": "test",
                "name": "Test Program",
                "objectives": [],
            },
            "progress": {"progress_pct": 100, "health": "green"},
            "milestones": [],
        },
        "systems": [],
        "tasks": [],
        "big_tasks": [],
        "epics": [],
        "adr": [],
        "rfc": [],
    }
    path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")


def test_architecture_sync_writes_managed_docs(tmp_path, monkeypatch):
    workspace = tmp_path
    (workspace / "architecture").mkdir(parents=True)
    manifest_path = workspace / "architecture" / "manifest.yaml"
    write_manifest(manifest_path)

    config_path = workspace / ".agentcontrol" / "config" / "docs.bridge.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
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

    docs_root = workspace / "docs"
    docs_root.mkdir()
    overview_path = docs_root / "architecture" / "overview.md"

    monkeypatch.setattr(tool, "ROOT", workspace)
    monkeypatch.setattr(tool, "MANIFEST_PATH", manifest_path)
    monkeypatch.setattr(tool, "STATE_DIR", workspace / ".sdk" / "arch")
    monkeypatch.setattr(tool, "STATE_FILE", (workspace / ".sdk" / "arch" / "outputs.json"))

    tool.sync_outputs()

    assert overview_path.exists()
    text = overview_path.read_text(encoding="utf-8")
    assert "agentcontrol:start:agentcontrol-architecture-overview" in text
    state_data = json.loads(tool.STATE_FILE.read_text(encoding="utf-8"))
    doc_keys = [k for k in state_data if k.startswith("doc::architecture_overview")]
    assert doc_keys
