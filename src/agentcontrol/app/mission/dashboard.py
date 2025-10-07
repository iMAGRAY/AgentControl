"""Mission dashboard rendering utilities."""

from __future__ import annotations

import curses
import json
import shutil
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

from agentcontrol.app.mission.service import MISSION_FILTERS, MissionService


def _short_json(data: Any, limit: int = 240) -> str:
    try:
        raw = json.dumps(data, ensure_ascii=False, indent=2)
    except TypeError:
        raw = str(data)
    if len(raw) <= limit:
        return raw
    return raw[: limit - 3] + "..."


@dataclass
class DashboardView:
    filters: Sequence[str]
    timeline_limit: int
    summary: dict[str, Any]
    generated_at: str
    timeline: list[dict[str, Any]] = field(default_factory=list)

    def section_payload(self, name: str) -> Any:
        if name == "docs":
            return self.summary.get("docsBridge", {})
        if name == "quality":
            return self.summary.get("quality", {})
        if name == "tasks":
            return self.summary.get("tasks", {})
        if name == "mcp":
            return self.summary.get("mcp", {})
        if name == "timeline":
            return self.timeline[: self.timeline_limit]
        return {}

    def drilldown(self, name: str) -> Any:
        drill = self.summary.get("drilldown", {})
        return drill.get(name, {}) if isinstance(drill, dict) else {}


class MissionDashboardRenderer:
    def __init__(self, summary: dict[str, Any], filters: Iterable[str] | None, timeline_limit: int) -> None:
        self._filters = tuple(filters) if filters else tuple(MISSION_FILTERS)
        self._timeline_limit = timeline_limit
        self._view = self._build_view(summary)

    def update(self, summary: dict[str, Any]) -> None:
        self._view = self._build_view(summary)

    def _build_view(self, summary: dict[str, Any]) -> DashboardView:
        timeline = summary.get("timeline", [])
        if not isinstance(timeline, list):
            timeline = []
        generated_at = summary.get("generated_at", "unknown")
        return DashboardView(
            filters=self._filters,
            timeline_limit=self._timeline_limit,
            summary=summary,
            generated_at=generated_at,
            timeline=timeline,
        )

    @property
    def filters(self) -> Sequence[str]:
        return self._filters

    def toggle_filter(self, name: str) -> None:
        if name not in MISSION_FILTERS:
            return
        if name in self._filters:
            remaining = tuple(filter(lambda item: item != name, self._filters))
            self._filters = remaining if remaining else tuple(MISSION_FILTERS)
        else:
            self._filters = tuple(dict.fromkeys((*self._filters, name)))
        self._view.filters = self._filters

    def render_lines(self, width: int = 120) -> list[str]:
        lines: list[str] = []
        activity = self._view.summary.get("activity") if isinstance(self._view.summary, dict) else {}
        filters_meta = self._view.summary.get("activityFilters") if isinstance(self._view.summary, dict) else None
        header = f"Mission Dashboard • generated_at={self._view.generated_at}"
        lines.append(header)
        lines.append("Sections: " + ", ".join(self._filters))
        activity_line = self._format_activity_line(activity, filters_meta)
        if activity_line:
            lines.append(activity_line)
        lines.append("Keys: 1-docs 2-quality 3-tasks 4-mcp 5-timeline r-refresh q-quit")
        lines.append("" )
        for section in self._filters:
            lines.extend(self._render_section(section, width))
            lines.append("")
        return lines

    def _format_activity_line(self, activity: Any, filters_meta: Any) -> str | None:
        if not isinstance(activity, dict):
            return None
        count = activity.get("count")
        sources = activity.get("sources") if isinstance(activity.get("sources"), dict) else {}
        tags = activity.get("tags") if isinstance(activity.get("tags"), dict) else {}
        actors = activity.get("actors") if isinstance(activity.get("actors"), dict) else {}
        last_id = activity.get("lastOperationId")
        parts: list[str] = []
        if isinstance(count, int):
            parts.append(f"activity={count}")
        if sources:
            top_source = max(sources.items(), key=lambda item: item[1])[0]
            parts.append(f"top_source={top_source}")
        if tags:
            top_tag = max(tags.items(), key=lambda item: item[1])[0]
            parts.append(f"top_tag={top_tag}")
        if actors:
            top_actor = max(actors.items(), key=lambda item: item[1])[0]
            parts.append(f"top_actor={top_actor}")
        if last_id:
            parts.append(f"last_operation={last_id}")
        if filters_meta and isinstance(filters_meta, dict):
            filter_fragments = []
            for key in ("sources", "actors", "tags"):
                values = filters_meta.get(key)
                if values:
                    filter_fragments.append(f"{key}={','.join(values)}")
            if filter_fragments:
                parts.append("filters:" + " ".join(filter_fragments))
        if not parts:
            return None
        return "Activity: " + " | ".join(parts)

    def render_text(self, width: int = 120) -> str:
        return "\n".join(self.render_lines(width))

    def render_html(self) -> str:
        body_parts: list[str] = ["<h1>Mission Dashboard</h1>"]
        body_parts.append(f"<p><strong>Generated at:</strong> {self._view.generated_at}</p>")
        for section in self._filters:
            body_parts.append(f"<h2>{section.title()}</h2>")
            payload = self._view.section_payload(section)
            drilldown = self._view.drilldown(section)
            body_parts.append("<pre>" + _short_json(payload, 4096) + "</pre>")
            if drilldown:
                body_parts.append("<details><summary>Drilldown</summary><pre>" + _short_json(drilldown, 4096) + "</pre></details>")
        html = "\n".join(body_parts)
        return f"<!doctype html><html><head><meta charset='utf-8'><title>Mission Dashboard</title></head><body>{html}</body></html>"

    def _render_section(self, section: str, width: int) -> list[str]:
        payload = self._view.section_payload(section)
        drilldown = self._view.drilldown(section)
        header = f"[{section.upper()}]"
        lines = [header]
        if section == "tasks" and isinstance(payload, dict):
            counts = payload.get("counts", {})
            lines.append(
                "counts: open={open} done={done} total={total}".format(
                    open=counts.get("open", 0),
                    done=counts.get("done", 0),
                    total=counts.get("total", 0),
                )
            )
            last_sync = payload.get("lastSync")
            if isinstance(last_sync, dict):
                provider = last_sync.get("provider") or {}
                if isinstance(provider, dict):
                    provider_name = provider.get("type") or provider.get("name")
                else:
                    provider_name = provider
                summary = last_sync.get("summary") or {}
                lines.append(
                    "last sync: {ts} provider={pv} applied={ap}".format(
                        ts=last_sync.get("generated_at", "unknown"),
                        pv=provider_name,
                        ap=last_sync.get("applied"),
                    )
                )
                if summary:
                    lines.append(
                        "  changes: create={create} update={update} close={close} unchanged={unchanged}".format(
                            create=summary.get("create", 0),
                            update=summary.get("update", 0),
                            close=summary.get("close", 0),
                            unchanged=summary.get("unchanged", 0),
                        )
                    )
            board = payload.get("board") or {}
            preview = board.get("preview") or []
            if preview:
                lines.append("  open preview:")
                for item in preview[:5]:
                    lines.append(
                        "    - {identifier}: {title} [{status}]".format(
                            identifier=item.get("id"),
                            title=item.get("title"),
                            status=item.get("status"),
                        )
                    )
            history = payload.get("history") or []
            if history:
                latest = history[0].get("generated_at") if isinstance(history[0], dict) else None
                lines.append(f"  history entries: {len(history)} (latest {latest or 'unknown'})")
            return lines
        body = _short_json(payload, limit=width * 3)
        lines.extend(textwrap.wrap(body, width=width) or ["(no data)"])
        if drilldown:
            lines.append("  drilldown:")
            wrapped = textwrap.wrap(_short_json(drilldown, limit=width * 3), width=width)
            lines.extend(["    " + item for item in wrapped])
        return lines


def run_dashboard_curses(
    summary_builder: MissionService,
    project_path: Path,
    renderer: MissionDashboardRenderer,
    filters: Iterable[str] | None,
    timeline_limit: int,
) -> int:
    def _loop(stdscr: Any) -> None:
        curses.curs_set(0)
        current_filters = list(renderer.filters)
        while True:
            stdscr.erase()
            height, width = stdscr.getmaxyx()
            for idx, line in enumerate(renderer.render_lines(width=width - 1)):
                if idx >= height - 1:
                    break
                stdscr.addnstr(idx, 0, line, width - 1)
            stdscr.refresh()
            key = stdscr.getch()
            if key in (ord('q'), ord('Q'), 27):
                break
            if key in (ord('r'), ord('R')):
                result = summary_builder.persist_twin(project_path)
                renderer.update(result.twin)
                continue
            key_map = {
                ord('1'): 'docs',
                ord('2'): 'quality',
                ord('3'): 'tasks',
                ord('4'): 'mcp',
                ord('5'): 'timeline',
            }
            section = key_map.get(key)
            if section:
                renderer.toggle_filter(section)

    curses.wrapper(_loop)
    return 0


def write_snapshot(renderer: MissionDashboardRenderer, path: Path) -> Path:
    html = renderer.render_html()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return path


def terminal_width(default: int = 120) -> int:
    size = shutil.get_terminal_size(fallback=(default, 40))
    return size.columns
