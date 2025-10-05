from __future__ import annotations

import json
import tempfile
from pathlib import Path

import yaml
from hypothesis import given, settings
from hypothesis import strategies as st

from agentcontrol.app.docs.service import DocsBridgeService, DocsBridgeServiceError

_identifier = st.text(alphabet=st.characters(min_codepoint=97, max_codepoint=122), min_size=3, max_size=10)
_marker = st.text(alphabet=st.characters(min_codepoint=97, max_codepoint=122), min_size=3, max_size=20)


@st.composite
def managed_section(draw: st.DataObject) -> dict[str, str]:
    name = draw(_identifier)
    marker = draw(_marker)
    return {
        "mode": "managed",
        "target": f"bench/{name}.md",
        "marker": f"agentcontrol-{marker}",
    }


sections_strategy = st.dictionaries(_identifier, managed_section(), min_size=1, max_size=4)


@st.composite
def bridge_config(draw: st.DataObject) -> dict[str, object]:
    sections = draw(sections_strategy)
    return {
        "version": 1,
        "root": "docs",
        "sections": sections,
    }


@settings(max_examples=30)
@given(config=bridge_config())
def test_docs_bridge_diagnose_is_schema_valid(config: dict[str, object]) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp)
        config_dir = project / ".agentcontrol" / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_path = config_dir / "docs.bridge.yaml"
        config_path.write_text(yaml.safe_dump(config, sort_keys=True), encoding="utf-8")

        docs_root = project / "docs"
        docs_root.mkdir(parents=True, exist_ok=True)
        sections = config["sections"]
        assert isinstance(sections, dict)
        for section in sections.values():
            target = section["target"]
            target_path = docs_root / target
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text("Initial", encoding="utf-8")

        service = DocsBridgeService()
        diagnose = service.diagnose(project)
        schema = diagnose.get("schema", {})
        assert schema.get("id")
        assert isinstance(schema.get("errors"), list)
        assert isinstance(diagnose.get("issues"), list)
        try:
            info = service.info(project)
        except DocsBridgeServiceError:
            return
        json.dumps(info)
