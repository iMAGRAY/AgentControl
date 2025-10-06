from __future__ import annotations

import json
from pathlib import Path

from agentcontrol.app.mission.service import MissionPaletteEntry, MissionService


def test_timeline_hint_docs_has_expected_context() -> None:
    service = MissionService()
    payload = {"section": "architecture_overview", "target": "docs/architecture/overview.md"}

    hint = service._timeline_hint("docs", payload)

    assert hint is not None
    assert "agentcall docs sync" in hint.text
    assert hint.doc_path and hint.doc_path.endswith("automation_hooks.md")
    assert "architecture_overview" in hint.hint_id


def test_persist_palette_creates_state_payload(tmp_path: Path) -> None:
    service = MissionService()
    entries = [
        MissionPaletteEntry(
            id="docs_sync",
            label="Sync Docs",
            command="agentcall docs sync --json",
            category="docs",
            type="automation",
            hotkey="d",
            summary="Repair managed documentation",
        )
    ]

    path = service.persist_palette(tmp_path, entries)

    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["entries"][0]["id"] == "docs_sync"
    assert data["entries"][0]["command"] == "agentcall docs sync --json"
    state_file = tmp_path / ".agentcontrol" / "state" / "mission_palette.json"
    assert path == state_file
