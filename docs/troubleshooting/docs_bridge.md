# Docs Bridge Troubleshooting Matrix

Use this matrix when automated runs surface issues in the documentation bridge.

| Symptom | Detection | Root Cause | Remediation | Automation Hook |
| --- | --- | --- | --- | --- |
| `DOC_BRIDGE_INVALID_CONFIG` | `agentcall docs diagnose` status = `error` | YAML syntax error or conflicting anchors | Fix YAML, rerun diagnose; schema path shown in payload | Gate PRs with `agentcall docs diagnose --json` |
| Managed marker duplicated | `diagnose.issues[].code = DOC_BRIDGE_DUPLICATE_MARKER` | Manual edits duplicated `<!-- agentcontrol:start:end -->` pairs | Run `agentcall docs repair --section <name>` | Add `agentcall auto docs --apply` to CI |
| `docs list` slow (>1s) | Perf benchmark thresholds exceeded | Large section count without caching | Enable docs benchmark (`scripts/perf/docs_benchmark.py`) and cache YAML loader | Compare against `reports/perf/docs_benchmark.json` |
| Timeline missing docs events | `mission summary` timeline empty despite docs drift | `journal/task_events.jsonl` not flushed | Ensure automation recipes emit telemetry via `record_structured_event` | Add telemetry write in custom scripts |
| Sandbox cannot start | `agentcall sandbox start` returns error `Template ... unavailable` | Template sync not run or sandbox template missing | Run `agentcall init` once to trigger template sync or install from wheel | Wrap sandbox creation in bootstrap playbook |

## Quick Commands
- Rebuild bridge state: `agentcall docs repair --json`
- Re-adopt as baseline: `agentcall docs adopt --json`
- Roll back from backup: `agentcall docs rollback --timestamp <ts>`

## Escalation Checklist
1. Capture `.agentcontrol/state/docs/history/` contents.
2. Persist `reports/perf/docs_benchmark.json` if perf regression suspected.
3. Attach `mission detail timeline --json` output for context.
4. Tag the owning squad listed in `AGENTS.md`.
