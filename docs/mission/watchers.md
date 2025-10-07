# Mission Watchers & SLA Configuration

`agentcall mission watch` runs headless automation that listens for mission timeline events and executes playbooks without human oversight.

## 1. watch.yaml
Create `.agentcontrol/config/watch.yaml` with event triggers:
```yaml
events:
  - id: perf_regression
    event: "perf.regression"
    playbook: "perf_regression"
    debounce_minutes: 30
    max_retries: 3
```
- `event` matches the `event` field in mission timeline entries.
- `playbook` references the playbook issue executed via `agentcall mission exec --issue <playbook>`.
- `debounce_minutes` controls how soon a trigger can re-fire.
- `max_retries` guards against loops when playbooks continue to fail.

## 2. sla.yaml
Define acknowledgement SLAs in `.agentcontrol/config/sla.yaml`:
```yaml
slas:
  - id: docs_followup
    acknowledgement: "docs"
    max_minutes: 60
    severity: warning
  - id: perf_followup
    acknowledgement: "perf"
    max_minutes: 120
    severity: critical
```
Each SLA monitors the acknowledgement status persisted in `.agentcontrol/state/mission_ack.json`. When the status stays non-success longer than `max_minutes`, an `sla.breach` entry is reported.

## 3. Running the Watcher
```bash
agentcall mission watch --interval 120
```
Options:
- `--once` — run a single iteration (useful for CI).
- `--max-iterations N` — limit the number of loops.
- `--json` — emit machine-readable reports per iteration.

Reports:
- `reports/automation/watch.json` captures triggered actions.
- `reports/automation/sla.json` summarises active SLA breaches.
- `journal/task_events.jsonl` receives `mission.watch.<rule>` entries enriched with `actorId`, `origin`, `tags`, and remediation outcome so the mission twin and dashboards surface watcher activity.

Watcher execution records `mission.watch` telemetry events with action counts and SLA breaches, and refreshes the mission twin on every iteration.
