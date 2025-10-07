# AgentControl — Operations Charter (Linux)

```yaml
agents_doc: v1
updated_at: 2025-10-04T10:05:00Z
owners: ["vibe-coder", "agentcontrol-core"]
harness: { approvals: "never", sandbox: { fs: "danger-full-access", net: "enabled" } }
budgets: { p99_ms: 0, memory_mb: 0, bundle_kb: 0 }
stacks: { runtime: "bash@5", build: "agentcall@0.5.2" }
teach: true
```

## 1. Command Surface
- `agentcall help [--json]` - contextual project guidance (verify/watch/SLA) for agents & humans.
- `agentcall status [PATH]` - dashboard plus capsule auto-bootstrap (tuned via `AGENTCONTROL_DEFAULT_TEMPLATE`, `AGENTCONTROL_DEFAULT_CHANNEL`, `AGENTCONTROL_NO_AUTO_INIT`).
- `agentcall init / upgrade [PATH]` - template provisioning or migration.
- `agentcall verify` - canonical quality gate (fmt/tests/security/docs/SBOM).
- `agentcall fix` / `agentcall review` / `agentcall ship` - remediation, diff review, release gate.
- `agentcall agents <install|auth|status|logs|workflow>` - agent CLI lifecycle management.
- `agentcall templates` - list installed templates.
- `agentcall telemetry <report|tail|clear>` - local telemetry management.
- `agentcall plugins <list|install|remove|info>` - plugin control via entry points.
- `agentcall extension <init|add|list|lint|publish>` - manage project extensions.
- `agentcall mission dashboard` - interactive TUI / snapshot for mission twin.
- `agentcall mission watch` - headless automation reacting to timeline events.
- `scripts/install_agentcontrol.sh` - one-time template installation on the workstation.

## 2. Workflow Governance
- **Workflow registry:** `config/agents.json`, overridable through env (`ASSIGN_AGENT`, `REVIEW_AGENT`, etc.).
- **Agent logs:** stored under `reports/agents/` with metadata for each run.
- **Micro tasks:** managed exclusively via the Update Plan Tool; must be empty before `agentcall ship`.
- **Task board:** synchronised across `data/tasks.board.json`, `state/task_state.json`, and `journal/task_events.jsonl`.

## 3. Quality Controls
- Mandatory artefacts: `AGENTS.md`, `architecture/manifest.yaml`, `todo.machine.md`, `.editorconfig`, `.codexignore`.
- Reports: `reports/verify.json`, `reports/review.json`, `reports/status.json`, `reports/doctor.json`.
- Release guard: `agentcall ship` blocks on failed checks or open micro tasks.

## 4. Recovery Playbook
- Pipeline tuning: adjust `SDK_*_COMMANDS` within `.agentcontrol/config/commands.sh`.
- Emergency reset: restore `config/commands.sh` from the template, run `agentcall verify`.
- Task board recovery: restore `data/tasks.board.json`, clear `state/task_selection.json`, archive `journal/task_events.jsonl`.
- Agent credentials: remove `state/agents/` or run `agentcall agents logout`.

## 5. References
- Architecture manifest: `architecture/manifest.yaml`.
- Change control: `docs/changes.md`, `docs/adr/`, `docs/rfc/`.
- Docs bridge: `.agentcontrol/config/docs.bridge.yaml` defines which sections of external documentation are updated automatically.
- Automation watcher: `.agentcontrol/config/watch.yaml` and `sla.yaml` configure mission watchers and SLA thresholds.
- Mission control and digital twin (roadmap): `agentcall mission --json` reads `.agentcontrol/state/twin.json`, delivering a complete snapshot (docs/tests/tasks/MCP).
- Script inventory: `scripts/` (including `scripts/agents/*.sh`, `scripts/lib/*.py`).
- Status snapshots: `reports/status.json`, `reports/architecture-dashboard.json`.
- Agent authentication state: `state/agents/auth_status.json`.

## 6. Escalation
- Owners: AgentControl Core (see YAML header).
- Raise issues via `agentcall agents workflow --task=<ID>` with SLA context; escalate directly to owners for critical incidents.
