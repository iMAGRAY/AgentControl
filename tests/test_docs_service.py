from __future__ import annotations

from pathlib import Path

import pytest

from agentcontrol.app.docs.service import DocsBridgeService


def _write_default_config(base: Path) -> Path:
    config = base / ".agentcontrol" / "config" / "docs.bridge.yaml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(
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
    return config


@pytest.fixture()
def default_config(tmp_path: Path) -> Path:
    return _write_default_config(tmp_path)


def test_diagnose_reports_missing_root(tmp_path: Path, default_config: Path) -> None:
    service = DocsBridgeService()

    payload = service.diagnose(tmp_path)

    assert payload["status"] == "warning"
    codes = [issue["code"] for issue in payload["issues"]]
    assert "DOC_ROOT_MISSING" in codes
    assert payload["schema"]["id"].startswith("agentcontrol://schemas/")


def test_diagnose_invalid_config(tmp_path: Path) -> None:
    config = tmp_path / ".agentcontrol" / "config" / "docs.bridge.yaml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text("version: 1\nroot: docs\nsections: {}\n", encoding="utf-8")

    service = DocsBridgeService()
    payload = service.diagnose(tmp_path)

    assert payload["status"] == "error"
    issue = payload["issues"][0]
    assert issue["code"] == "DOC_BRIDGE_INVALID_CONFIG"
    assert payload["schema"]["valid"] is False


def test_info_returns_capabilities(tmp_path: Path, default_config: Path) -> None:
    docs_root = tmp_path / "docs"
    (docs_root / "architecture").mkdir(parents=True, exist_ok=True)
    (docs_root / "adr").mkdir(parents=True, exist_ok=True)
    (docs_root / "rfc").mkdir(parents=True, exist_ok=True)

    (docs_root / "architecture" / "overview.md").write_text(
        "\n".join(
            [
                "<!-- agentcontrol:start:agentcontrol-architecture-overview -->",
                "Overview",
                "<!-- agentcontrol:end:agentcontrol-architecture-overview -->",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (docs_root / "adr" / "index.md").write_text(
        "\n".join(
            [
                "<!-- agentcontrol:start:agentcontrol-adr-index -->",
                "ADR Index",
                "<!-- agentcontrol:end:agentcontrol-adr-index -->",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (docs_root / "rfc" / "index.md").write_text(
        "\n".join(
            [
                "<!-- agentcontrol:start:agentcontrol-rfc-index -->",
                "RFC Index",
                "<!-- agentcontrol:end:agentcontrol-rfc-index -->",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    service = DocsBridgeService()
    payload = service.info(tmp_path)

    assert payload["status"] == "ok"
    assert payload["config"]["rootExists"] is True
    assert payload["capabilities"]["managedRegions"] is True
    assert payload["capabilities"]["atomicWrites"] is True
    assert payload["capabilities"]["anchorInsertion"] is True


def test_info_exposes_insertion_metadata(tmp_path: Path) -> None:
    config_path = _write_default_config(tmp_path)
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
                "    insert_after_heading: '# Overview'",
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
    docs_root = tmp_path / "docs"
    (docs_root / "architecture").mkdir(parents=True, exist_ok=True)
    (docs_root / "architecture" / "overview.md").write_text("# Overview\n", encoding="utf-8")

    service = DocsBridgeService()
    payload = service.info(tmp_path)

    arch = next(section for section in payload["config"]["sections"] if section["name"] == "architecture_overview")
    assert arch["insertion"]["type"] == "after_heading"
    assert arch["insertion"]["value"] == "# Overview"
