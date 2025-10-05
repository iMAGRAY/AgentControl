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

## Step 4 — Stream for Live Operations
During long-running tasks run:
```bash
agentcall mission ui --filter quality --filter tasks --interval 1.5
```
The dashboard refreshes every 1.5 seconds, printing quality gate status and task progress only. A termination (Ctrl+C) emits a structured telemetry event so the orchestrator knows the session ended intentionally.

> Новое: playbooks выводятся с приоритетом (`[priority] issue`) и hint — так агент понимает, какое действие запустить первым.

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

## Step 6 — Persist Findings
Agents should persist the twin path (`.agentcontrol/state/twin.json`) in case logs are needed later. The file is overwritten on each summary call, so archive it when capturing RCA artifacts.

> **Next:** Register MCP servers using the [MCP integration tutorial](./mcp_integration.md) to extend the mission dashboard with tool availability.
