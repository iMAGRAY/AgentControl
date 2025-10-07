# Mission Dashboard Guide

`agentcall mission dashboard` delivers an interactive (curses) snapshot of the mission twin so agents can inspect docs, quality, tasks, MCP state, and the latest timeline without leaving the terminal.

## Launch
```bash
agentcall mission dashboard
```
- `1`–`5` toggle sections (docs, quality, tasks, mcp, timeline).
- `r` refreshes the twin in place.
- `q` exits.

Use `--filter` to preselect sections and `--timeline-limit` to control the number of events rendered:
```bash
agentcall mission dashboard --filter docs --filter quality --timeline-limit 5
```

### Sample Layout
```
Mission Dashboard • generated_at=2025-10-06T10:00:00Z
Sections: docs, quality, timeline
Keys: 1-docs 2-quality 3-tasks 4-mcp 5-timeline r-refresh q-quit

[DOCS]
{ "status": "ok", "issues": [] }

[QUALITY]
{ "tests": { "passed": 10, "failed": 0 }, "status": "ok" }

[TIMELINE]
[   { "timestamp": "2025-10-06T09:45:00Z", "category": "tasks", "event": "tasks.update" } ]
```
The static output mirrors what agents see in the TUI: top line shows the generated timestamp, the second lists active sections, then each pane renders JSON payloads or timeline snippets honouring the `--timeline-limit` setting.

> TIP: `agentcall help --json` summarises the latest verify status, watcher rules, and recommended mission commands so agents know when to open the dashboard.

### Tasks Pane & Sync Reports
- Панель `tasks` объединяет данные борда (`data/tasks.board.json`) и свежие отчёты синхронизации.
- Каждое успешное `agentcall tasks sync` сохраняет сводку в `reports/tasks/sync.json` и историю в `reports/tasks/history/`.
- Dashboard отображает `lastSync.summary` и до 10 последних записей истории; поля `provider.options` уже маскированы (секреты не выводятся).

## Snapshots
Generate an HTML snapshot for sharing or archiving:
```bash
agentcall mission dashboard --snapshot reports/mission/dashboard-$(date +%s).html
```

Snapshots embed section payloads and drill-down data so the dashboard can be reviewed offline by humans or agents.

## Non-Interactive Mode
In CI or non-TTY environments pass `--no-curses` (or redirect output) to print a static summary that mirrors the TUI layout:
```bash
agentcall mission dashboard --no-curses
```

## Web Mode
Start a stateless web dashboard when agents need a browser view or remote monitoring:
```bash
agentcall mission dashboard --serve --bind 127.0.0.1 --port 8765
```

- Authentication uses the bearer token stored in `.agentcontrol/state/session.json` (printed on startup) or a custom value via `--token`.
- Server-Sent Events stream live mission twins to `/sse/events`; triggers go through `POST /playbooks/<issue>`.
- `--interval` controls the refresh cadence (seconds).

For a detailed walkthrough, see `docs/mission/dashboard_web.md`.

## Telemetry
Each invocation records structured events:
- `mission.dashboard` (`mode=static|curses`, filters, timeline limit)
- Snapshot exports annotate the path for audit trails.

### Mission Actions & Timeline Hooks
- Palette hotkeys and `mission exec` now append entries to `reports/automation/mission-actions.json` and emit timeline events `mission.ui.<actionId>`/`mission.exec.<issue>` so headless watchers can react without polling the CLI.
- `/playbooks/<issue>` calls in web mode log `mission.web` actions with matching `operationId`. The same payload is mirrored into `journal/task_events.jsonl` as `mission.web.<issue>` to maintain a single activity stream.
- Mission analytics ingests these artefacts to surface total counts, recent actors, and the latest operation ids, а дашборд отображает топовые source/tag/actor и `last_operation` прямо в хедере.

### Analytics Filters
- `agentcall mission analytics --source mission.exec` keeps only actions triggered via the mission CLI, recomputing counts and `recent` history on the fly.
- Combine multiple flags (`--actor`, `--tag`) to pinpoint automation noise—for example `--tag docs_sync` isolates documentation remediations across UI, web, and watcher sources.
- JSON output now includes `filters` metadata and `sources`/`actors`/`tags` aggregates so dashboards can render trend charts without re-reading the raw log.
- `reports/mission-activity.json` хранит свежий срез активности (counts/sources/actors/tags + filters) для внешних дашбордов/BI-пайплайнов.

The dashboard reuses the mission twin (`.agentcontrol/state/twin.json`) and palette artefacts, so refreshes are instant and consistent with `mission summary`, `mission detail`, and `mission analytics`.
