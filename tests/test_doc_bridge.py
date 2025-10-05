from __future__ import annotations

from pathlib import Path
import sys

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agentcontrol.domain.docs.editor import ENGINE, RegionOperation, ManagedRegionCorruptionError
from agentcontrol.domain.docs.value_objects import DocsBridgeConfigError, InsertionPolicy
from agentcontrol.utils import docs_bridge as doc_bridge


def test_update_managed_region_creates_file(tmp_path: Path) -> None:
    target = tmp_path / "doc.md"
    changed = doc_bridge.update_managed_region(target, "sample", "hello world\n")
    assert changed
    text = target.read_text(encoding="utf-8")
    assert "hello world" in text
    assert doc_bridge.read_managed_region(target, "sample") == "hello world"


def test_update_managed_region_respects_existing_content(tmp_path: Path) -> None:
    target = tmp_path / "doc.md"
    doc_bridge.update_managed_region(target, "sample", "first")
    changed = doc_bridge.update_managed_region(target, "sample", "second line\n")
    assert changed
    second = doc_bridge.read_managed_region(target, "sample")
    assert second == "second line"
    changed_again = doc_bridge.update_managed_region(target, "sample", "second line\n")
    assert not changed_again


def test_docs_bridge_default_config():
    config = doc_bridge.default_docs_bridge_config()
    assert str(config.root).endswith("docs")
    assert config.architecture_overview.marker == "agentcontrol-architecture-overview"


def test_update_managed_region_supports_removal(tmp_path: Path) -> None:
    target = tmp_path / "doc.md"
    doc_bridge.update_managed_region(target, "sample", "content")
    removed = doc_bridge.update_managed_region(target, "sample", None)
    assert removed
    assert doc_bridge.read_managed_region(target, "sample") is None


def test_update_managed_region_handles_multiple_sections(tmp_path: Path) -> None:
    target = tmp_path / "doc.md"
    ENGINE.apply(
        target,
        {
            "alpha": RegionOperation(content="alpha block"),
            "beta": RegionOperation(content="beta block"),
        },
    )
    text = target.read_text(encoding="utf-8")
    assert "agentcontrol:start:alpha" in text
    assert "agentcontrol:start:beta" in text


def test_insertion_after_heading(tmp_path: Path) -> None:
    target = tmp_path / "doc.md"
    target.write_text("# Title\n\nBody\n", encoding="utf-8")
    policy = InsertionPolicy(kind="after_heading", value="# Title")
    doc_bridge.update_managed_region(target, "sample", "Inserted", insertion=policy)
    text = target.read_text(encoding="utf-8")
    heading_index = text.index("# Title")
    sample_index = text.index("agentcontrol:start:sample")
    assert sample_index > heading_index


def test_insertion_before_marker(tmp_path: Path) -> None:
    target = tmp_path / "doc.md"
    existing = "<!-- agentcontrol:start:other -->\nOther\n<!-- agentcontrol:end:other -->\n"
    target.write_text(existing, encoding="utf-8")
    policy = InsertionPolicy(kind="before_marker", value="other")
    doc_bridge.update_managed_region(target, "sample", "Inserted", insertion=policy)
    text = target.read_text(encoding="utf-8")
    sample_index = text.index("agentcontrol:start:sample")
    other_index = text.index("agentcontrol:start:other")
    assert sample_index < other_index


def test_config_rejects_conflicting_insertion(tmp_path: Path) -> None:
    config_path = tmp_path / "bridge.yaml"
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
                "    insert_after_heading: '# Title'",
                "    insert_before_marker: other",
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
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    with pytest.raises(DocsBridgeConfigError):
        doc_bridge.DocsBridgeConfig.from_dict(raw, config_path=config_path)


def test_update_managed_region_supports_removal(tmp_path: Path) -> None:
    target = tmp_path / "doc.md"
    doc_bridge.update_managed_region(target, "sample", "content")
    removed = doc_bridge.update_managed_region(target, "sample", None)
    assert removed
    assert doc_bridge.read_managed_region(target, "sample") is None


def test_update_managed_region_handles_multiple_sections(tmp_path: Path) -> None:
    target = tmp_path / "doc.md"
    doc_bridge.update_managed_region(target, "alpha", "first")
    doc_bridge.update_managed_region(target, "beta", "second")
    assert doc_bridge.read_managed_region(target, "alpha") == "first"
    assert doc_bridge.read_managed_region(target, "beta") == "second"


def test_read_managed_region_detects_corruption(tmp_path: Path) -> None:
    target = tmp_path / "doc.md"
    target.write_text("<!-- agentcontrol:start:sample -->\ncorrupted\n", encoding="utf-8")
    with pytest.raises(ManagedRegionCorruptionError):
        doc_bridge.read_managed_region(target, "sample")
