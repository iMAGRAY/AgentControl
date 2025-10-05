from __future__ import annotations

import json
from pathlib import Path

import yaml

from agentcontrol.app.docs.operations import DocsCommandService, STATE_FILE


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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")


def write_config(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "version: 1",
                "root: docs",
                "sections:",
                "  architecture_overview:",
                "    mode: managed",
                "    target: architecture/overview.md",
                "    marker: agentcontrol-architecture-overview",
                "    insert_after_heading: '# Architecture Overview'",
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


def test_docs_operations_roundtrip(tmp_path: Path) -> None:
    project = tmp_path
    write_manifest(project / "architecture" / "manifest.yaml")
    write_config(project / ".agentcontrol" / "config" / "docs.bridge.yaml")

    overview = project / "docs" / "architecture" / "overview.md"
    overview.parent.mkdir(parents=True, exist_ok=True)
    original_text = "# Architecture Overview\n\nLegacy content\n"
    overview.write_text(original_text, encoding="utf-8")

    service = DocsCommandService()

    diff_payload = service.diff_sections(project)
    statuses = {entry["name"]: entry["status"] for entry in diff_payload["diff"]}
    assert statuses.get("architecture_overview") in {"missing_marker", "missing_file", "differs"}

    repair_payload = service.repair_sections(project)
    assert repair_payload["actions"]
    backup_path = Path(repair_payload["backup"])
    assert backup_path.exists()
    baseline_timestamp = backup_path.name

    updated_text = overview.read_text(encoding="utf-8")
    assert "agentcontrol:start:agentcontrol-architecture-overview" in updated_text

    diff_after_repair = service.diff_sections(project)
    assert all(entry["status"] == "match" for entry in diff_after_repair["diff"])

    adopt_payload = service.adopt_sections(project)
    state_path = project / STATE_FILE
    assert state_path.exists()
    snapshot = json.loads(state_path.read_text(encoding="utf-8"))
    assert "architecture_overview" in snapshot["sections"]

    overview.write_text("# Architecture Overview\n\nManual drift\n", encoding="utf-8")
    diff_drift = service.diff_sections(project)
    assert any(entry["status"] != "match" for entry in diff_drift["diff"])

    repair_payload_2 = service.repair_sections(project)
    backup_path_2 = Path(repair_payload_2["backup"])
    assert backup_path_2.exists()

    overview.write_text("# Architecture Overview\n\nAnother drift\n", encoding="utf-8")
    rollback_payload = service.rollback_sections(project, timestamp=baseline_timestamp)
    assert rollback_payload["actions"]
    restored_text = overview.read_text(encoding="utf-8")
    assert "Another drift" not in restored_text
    assert restored_text.strip() == original_text.strip()

    diff_final = service.diff_sections(project)
    assert any(entry["status"] != "match" for entry in diff_final["diff"])


def test_external_adapters(tmp_path: Path) -> None:
    project = tmp_path
    write_manifest(project / "architecture" / "manifest.yaml")
    config_path = project / ".agentcontrol" / "config" / "docs.bridge.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
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
                "  mkdocs_nav:",
                "    mode: external",
                "    adapter: mkdocs",
                "    target: mkdocs.yml",
                "    options:",
                "      entry:",
                "        Architecture: docs/architecture/overview.md",
                "      insert_after: Home",
                "  docusaurus_sidebar:",
                "    mode: external",
                "    adapter: docusaurus",
                "    target: sidebars.json",
                "    options:",
                "      sidebar: docs",
                "      category: Architecture",
                "      doc_id: architecture-overview",
                "  confluence_overview:",
                "    mode: external",
                "    adapter: confluence",
                "    options:",
                "      space: ENG",
                "      ancestor_id: '1234'",
                "      title: Architecture Overview",
                "      slug: architecture-overview",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    docs_root = project / "docs"
    (docs_root / "architecture").mkdir(parents=True, exist_ok=True)
    (docs_root / "architecture" / "overview.md").write_text(
        "<!-- agentcontrol:start:agentcontrol-architecture-overview -->\nOverview\n<!-- agentcontrol:end:agentcontrol-architecture-overview -->\n",
        encoding="utf-8",
    )
    (docs_root / "adr").mkdir(parents=True, exist_ok=True)
    (docs_root / "adr" / "index.md").write_text(
        "<!-- agentcontrol:start:agentcontrol-adr-index -->\nADR Index\n<!-- agentcontrol:end:agentcontrol-adr-index -->\n",
        encoding="utf-8",
    )
    (docs_root / "rfc").mkdir(parents=True, exist_ok=True)
    (docs_root / "rfc" / "index.md").write_text(
        "<!-- agentcontrol:start:agentcontrol-rfc-index -->\nRFC Index\n<!-- agentcontrol:end:agentcontrol-rfc-index -->\n",
        encoding="utf-8",
    )

    mkdocs_file = project / "mkdocs.yml"
    mkdocs_file.write_text("nav:\n  - Home: index.md\n", encoding="utf-8")

    sidebar_file = project / "sidebars.json"
    sidebar_file.write_text(json.dumps({"docs": []}), encoding="utf-8")

    service = DocsCommandService()
    diff = service.diff_sections(project)
    statuses = {entry["name"]: entry["status"] for entry in diff["diff"]}
    assert statuses.get("Architecture") == "missing"
    assert statuses.get("Architecture Overview") == "missing"

    repair = service.repair_sections(project)
    assert any(action["path"].endswith("mkdocs.yml") and action["action"] == "updated" for action in repair["actions"])
    assert any(action["path"].endswith("sidebars.json") and action["action"] == "updated" for action in repair["actions"])
    assert (project / ".agentcontrol/state/docs/confluence/architecture-overview.json").exists()

    updated_yaml = yaml.safe_load(mkdocs_file.read_text(encoding="utf-8"))
    assert {"Architecture": "docs/architecture/overview.md"} in updated_yaml["nav"]
    updated_sidebar = json.loads(sidebar_file.read_text(encoding="utf-8"))
    assert updated_sidebar["docs"][0]["label"] == "Architecture"
