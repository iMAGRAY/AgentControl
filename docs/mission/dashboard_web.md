# Mission Dashboard Web Mode

`agentcall mission dashboard --serve` exposes the mission twin through a lightweight HTTP server that speaks only standard library protocols (no uvicorn/gunicorn). It is optimised for agent usage: deterministic payloads, SSE streaming, and zero dependency on global services.

## Quick Start
```bash
agentcall mission dashboard --serve --bind 127.0.0.1 --port 8765
```

- The CLI prints the listening URL, the bearer token, and the token path (`.agentcontrol/state/session.json`).
- Keep the token secret; pass it as `Authorization: Bearer <token>` or as `?token=<token>` for browser previews.
- Stop the server with `Ctrl+C`.

## Endpoints
| Path | Method | Description |
| --- | --- | --- |
| `/` | GET | Static HTML bundle that consumes the SSE feed and renders sections client-side. |
| `/healthz` | GET | Liveness probe returning `{ "status": "ok" }`. |
| `/sse/events` | GET | Server-Sent Events stream delivering the latest mission twin (requires token). |
| `/playbooks/<issue>` | POST | Executes the requested playbook and returns `{ operationId, status, remediationHint, ... }`. |

All endpoints require the bearer token except `/` (for the HTML shell) and `/healthz`.

### Telemetry & Logs
- Every `/playbooks/<issue>` invocation appends an entry to `reports/automation/mission-actions.json` with `source: mission.web` and the generated `operationId`.
- Structured telemetry is emitted under the `mission.dashboard.api` event name (see `~/.agentcontrol/logs/telemetry.jsonl`) so watchers and dashboards can trace remote triggers.
- Responses are idempotent: repeated POSTs reuse the same playbook execution logic and each response carries a unique `operationId` for auditing.

## Streaming Behaviour
- The SSE stream sends a fresh mission twin every `--interval` seconds (default `5`).
- Payload shape mirrors `agentcall mission summary --json` with additional keys:
  - `timeline`: trimmed to `--timeline-limit` events.
  - `playbooks`: the actionable queue.
  - `filters`: the active section filters.

## Tokens & Sessions
- When `session.json` is absent, the server generates a 32-byte token and persists it.
- Override the token for transient sessions with `--token <value>`; this does not modify `session.json`.
- Rotate tokens by deleting `session.json` or overwriting it with a new `token` value.

## Example Playbook Trigger
```bash
curl -X POST \
  -H "Authorization: Bearer $MISSION_TOKEN" \
  http://127.0.0.1:8765/playbooks/docs_sync
```

The response contains `operationId` (useful for logs) and `remediationHint` derived from the playbook metadata or execution log.

Mission actions triggered through the API are visible in the dashboard activity panel after the next SSE refresh (default every 5 seconds).

## Troubleshooting
- **401 Unauthorized**: check the token, regenerate `session.json`, or pass `--token`.
- **No updates in the UI**: ensure `mission summary` succeeds; the server relies on `MissionService.persist_twin`.
- **Port conflicts**: run with `--port 0` to bind a random free port.

## Next Steps
- Wire the HTML bundle into your preferred observability stack via the SSE endpoint.
- Use `/playbooks/<issue>` from automation recipes to trigger responses without invoking the full CLI.
