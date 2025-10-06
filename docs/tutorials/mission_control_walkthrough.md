# Tutorial: Mission Control Dashboard Deep Dive

This pocket guide shows an agent how to consume the digital twin (`mission summary`/`mission ui`) and react without human babysitting.

## Objectives
- Filter dashboard output to relevant domains (docs, quality, tasks, MCP servers).
- Drill into a specific section to fetch actionable detail.
- Stream updates while an automation recipe runs.

## Step 1 — Generate a Fresh Twin
```bash
agentcall mission summary --json --timeline-limit 10
```
Key payload fields:
- `filters`: the sections supported by the dashboard (`["docs", "quality", "tasks", "timeline", "mcp"]`).
- `timeline`: most recent events gathered from `journal/task_events.jsonl`.
- `drilldown`: per-section data for precise follow-up.

## Step 2 — Focus on Documentation Health
```bash
agentcall mission summary --filter docs
```
Only the docs segment is rendered. When `issues` is non-empty, queue `agentcall auto docs --apply` immediately.

## Step 3 — Inspect Detailed Timeline
```bash
agentcall mission detail timeline --timeline-limit 5 --json
```
The response includes chronological events with `timestamp`, `category`, and `event` keys—ideal for feeding into alerting playbooks.

Every entry now surfaces a `hint` that spells out the next automation step. Examples:
- Docs drift → `agentcall docs sync --json` + inspect `reports/automation/docs-diff.json`.
- QA degradation → `agentcall auto tests --apply` + review `reports/verify.json`.
- Task events → double-check `architecture_plan.md` / AGENTS.md (todo section), then re-run `mission detail tasks --json`.

## Step 4 — Stream for Live Operations
During long-running tasks run:
```bash
agentcall mission ui --filter quality --filter tasks --interval 1.5
```
The dashboard refreshes every 1.5 seconds, printing quality gate status and task progress only. A termination (Ctrl+C) emits a structured telemetry event so the orchestrator knows the session ended intentionally.

> New: Mission UI ships with a command palette—press `1...9`, `a`, `v`, `m`, `t`, `r`, or `e` to run the mapped playbook or automation instantly. Usage is logged to `reports/automation/mission-actions.json`, emits `mission.ui.action` telemetry, and appends an event (`mission.ui.<actionId>`) to `journal/task_events.jsonl` so downstream watchers can react.

### Step 4.1 — Interactive Dashboard
When a richer overview is needed, launch the dedicated dashboard:
```bash
agentcall mission dashboard --filter docs --filter quality
```
Hotkeys mirror `mission ui`, and `--snapshot <path>` exports an HTML report for async review.

## Step 5 — React via Playbooks
When the twin exposes `playbooks`, execute them in priority order. Example entry:
```json
{
  "issue": "verify_outdated",
  "summary": "Run verification pipeline",
  "command": "agentcall auto tests --apply"
}
```
Invoke the command, then refresh the twin to confirm the playbook cleared.

> Since 0.3.2 the command `agentcall mission exec` automatically selects the highest-priority playbook (for example `docs sync`) and executes it. Run it and verify the refreshed twin.

Need to isolate just the playbooks you triggered? Use the new analytics filters:
```bash
agentcall mission analytics --json --source mission.exec --tag docs_sync
```
This recomputes counts and recent actions on the fly, so the report contains only your remediation run.

## Step 6 — Persist Findings
Agents should persist the twin path (`.agentcontrol/state/twin.json`) in case logs are needed later. The file is overwritten on each summary call, so archive it when capturing RCA artifacts.

> **Next:**
> 1. Register MCP servers using the [MCP integration tutorial](./mcp_integration.md) — timeline hints will link to `agentcall mcp status --json` outputs stored in `reports/automation/mcp-status.json`.
> 2. Schedule nightly perf comparisons via `python3 scripts/perf/compare_history.py --report reports/perf/docs_benchmark.json --history-dir reports/perf/history --update-history` or the [Perf Nightly workflow](./perf_nightly.md).
> 3. Run `agentcall mission analytics --json` to gather aggregated metrics: activity (`mission-actions.json`), performance regressions (`reports/perf/history/diff.json`), and acknowledgement state (docs/quality/tasks/runtime).
> 4. Configure `.agentcontrol/config/watch.yaml` + `sla.yaml` and execute `agentcall mission watch --once` to confirm automation triggers and SLA checks.
