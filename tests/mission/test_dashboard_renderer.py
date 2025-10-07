from __future__ import annotations

import json
from pathlib import Path

from agentcontrol.app.mission.dashboard import MissionDashboardRenderer, write_snapshot


def _dummy_summary() -> dict:
    return {
        "generated_at": "2025-10-06T10:00:00Z",
        "docsBridge": {"status": "ok", "issues": []},
        "quality": {"status": "ok", "tests": {"passed": 10, "failed": 0}},
        "tasks": {
            "counts": {"open": 2, "done": 8, "total": 10},
            "board": {"preview": [{"id": "TASK-1", "title": "Docs", "status": "open"}]},
            "lastSync": {
                "generated_at": "2025-10-06T09:50:00Z",
                "provider": {"type": "github"},
                "summary": {"create": 1, "update": 0, "close": 1, "unchanged": 0},
                "applied": True
            },
            "history": [
                {"generated_at": "2025-10-06T09:50:00Z", "provider": {"type": "github"}}
            ]
        },
        "mcp": {"servers": [{"name": "staging", "endpoint": "https://mcp.example.com"}]},
        "timeline": [
            {"timestamp": "2025-10-06T09:45:00Z", "category": "tasks", "event": "tasks.update"},
            {"timestamp": "2025-10-06T09:30:00Z", "category": "quality", "event": "verify.pass"},
            {"timestamp": "2025-10-06T09:00:00Z", "category": "docs", "event": "docs.sync"},
        ],
        "drilldown": {
            "docs": {"sections": 4},
            "quality": {"coverage": 92},
        },
    }


def test_renderer_text_output_contains_sections() -> None:
    summary = _dummy_summary()
    renderer = MissionDashboardRenderer(summary, filters=["docs", "quality", "timeline"], timeline_limit=5)
    text = renderer.render_text(width=80)
    assert "[DOCS]" in text
    assert "[QUALITY]" in text


def test_renderer_tasks_section_shows_counts() -> None:
    summary = _dummy_summary()
    renderer = MissionDashboardRenderer(summary, filters=["tasks"], timeline_limit=5)
    text = renderer.render_text(width=80)
    assert "counts: open=2 done=8 total=10" in text


def test_snapshot_writer(tmp_path: Path) -> None:
    summary = _dummy_summary()
    renderer = MissionDashboardRenderer(summary, filters=None, timeline_limit=5)
    output = tmp_path / "dashboard.html"
    write_snapshot(renderer, output)
    html = output.read_text(encoding="utf-8")
    assert "Mission Dashboard" in html
    assert "docs.sync" in html


def test_renderer_toggle_filter_roundtrip() -> None:
    summary = _dummy_summary()
    renderer = MissionDashboardRenderer(summary, filters=["docs", "quality", "timeline"], timeline_limit=5)

    # Toggle off docs, ensure fallback retains remaining filters.
    renderer.toggle_filter("docs")
    assert tuple(renderer.filters) == ("quality", "timeline")

    # Toggle back on and confirm ordering matches insertion semantics.
    renderer.toggle_filter("docs")
    assert tuple(renderer.filters) == ("quality", "timeline", "docs")

    lines = renderer.render_lines(width=80)
    assert any(line.startswith("Sections: ") for line in lines)


def test_renderer_timeline_limit_respected() -> None:
    summary = _dummy_summary()
    renderer = MissionDashboardRenderer(summary, filters=["timeline"], timeline_limit=1)
    lines = renderer.render_lines(width=60)
    timeline_lines = [line for line in lines if any(token in line for token in ("tasks.update", "verify.pass", "docs.sync"))]
    # Only the most recent event (tasks.update) should appear given limit=1.
    assert timeline_lines == [line for line in timeline_lines if "tasks.update" in line]
