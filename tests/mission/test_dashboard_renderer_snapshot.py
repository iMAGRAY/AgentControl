from __future__ import annotations

from agentcontrol.app.mission.dashboard import MissionDashboardRenderer


def test_render_lines_with_filters() -> None:
    summary = {
        "generated_at": "2025-10-06T12:34:56Z",
        "docsBridge": {"status": "warning"},
        "quality": {"verify": {"status": "success"}},
        "tasks": {"open": 2},
        "mcp": {"count": 1},
        "timeline": [],
        "activity": {
            "count": 3,
            "sources": {"mission.exec": 2, "mission.web": 1},
            "actors": {"mission.web:docs": 1},
            "tags": {"docs_sync": 3},
            "lastOperationId": "abcd1234",
            "lastTimestamp": "2025-10-06T12:34:00Z",
        },
        "activityFilters": {"sources": ["mission.exec"]},
    }
    renderer = MissionDashboardRenderer(summary, filters=["docs", "quality"], timeline_limit=5)
    lines = renderer.render_lines(width=80)
    header = lines[1]
    activity_line = lines[2]
    assert header.startswith("Sections: docs, quality")
    assert "activity=" in activity_line
    assert "top_source=mission.exec" in activity_line
    assert "filters:sources=mission.exec" in activity_line
