# AgentControl — Operations Charter (Linux)

```yaml
agents_doc: v1
updated_at: 2025-10-05T12:00:00Z
owners: ["vibe-coder", "agentcontrol-core"]
harness: { approvals: "never", sandbox: { fs: "danger-full-access", net: "enabled" } }
budgets: { p99_ms: 0, memory_mb: 0, bundle_kb: 0 }
stacks: { runtime: "bash@5", build: "agentcall@0.3" }
teach: true
```

## 1. Command Surface
- `agentcall status [PATH]` — dashboard plus capsule auto-bootstrap (tuned via `AGENTCONTROL_DEFAULT_TEMPLATE`, `AGENTCONTROL_DEFAULT_CHANNEL`, `AGENTCONTROL_NO_AUTO_INIT`). JSON output now embeds `docsBridge` diagnostics.
- `agentcall docs diagnose|info --json [PATH]` — schema validation, status/sections for in-place documentation bridge.
- `agentcall docs list|diff|repair|adopt|rollback [--json] [PATH]` — managed documentation lifecycle (backups, anchor-aware updates, MkDocs/Docusaurus/Confluence adapters).
- `agentcall docs sync [--mode repair|adopt] [--json] [PATH]` — автоматизированный diff→repair/adopt конвейер для managed секций.
- `agentcall sandbox start|list|purge [PATH]` — provision disposable capsules under `.agentcontrol/sandbox/` for experimentation.
- `agentcall mission summary|ui|detail|exec [--json] [PATH]` — generate twins, stream dashboard, drill into sections или автоматически выполнить топ-плейбук (`exec`).
- `agentcall info [PATH] [--json]` — enumerate available capabilities, telemetry schema, and optional mission snapshot.
- `agentcall mcp add|remove|status [PATH]` — manage per-project MCP server registry under `.agentcontrol/config/mcp/`.
- `agentcall runtime status|events [PATH]` — refresh `.agentcontrol/runtime.json` and stream structured telemetry events.
- `agentcall auto docs|tests|release [PATH] [--apply]` — run automation playbooks with dry-run guardrails by default.
- `agentcall migrate [--apply] [PATH]` — detect and upgrade legacy `agentcontrol/` capsules; emits telemetry counters.
- `agentcall self-update --mode <print|pip|pipx>` — manual override for updating the CLI (auto-update runs by default on launch and exits once an upgrade is applied).
- `agentcall init / upgrade [PATH]` — template provisioning or migration.
- `agentcall verify` — canonical quality gate (fmt/tests/security/docs/SBOM).
- `agentcall fix` / `agentcall review` / `agentcall ship` — remediation, diff review, release gate.
- `agentcall agents <install|auth|status|logs|workflow>` — agent CLI lifecycle management.
- `agentcall templates` — list installed templates.
- `agentcall telemetry <report|tail|clear>` — local telemetry management.
- `agentcall plugins <list|install|remove|info>` — plugin control via entry points.
- `agentcall cache <list|add|download>` — curate offline update wheels used by auto-update fallback.
- `scripts/install_agentcontrol.sh` — one-time template installation on the workstation.

## 2. Workflow Governance
- **Workflow registry:** `config/agents.json`, overridable through env (`ASSIGN_AGENT`, `REVIEW_AGENT`, etc.).
- **Agent logs:** stored under `reports/agents/` with metadata for each run.
- **Micro tasks:** managed exclusively via the Update Plan Tool; must be empty before `agentcall ship`.
- **Task board:** synchronised across `data/tasks.board.json`, `state/task_state.json`, and `journal/task_events.jsonl`.
- **Planning integrity (MANDATORY):** при любом изменении кода необходимо немедленно обновлять `architecture_plan.md` и `todo.md`: отмечать завершённые пункты, добавлять новые цели, поддерживать полноту и актуальность. Несоблюдение правила считается нарушением процесса.

## 3. Quality Controls
- Mandatory artefacts: `AGENTS.md`, `architecture/manifest.yaml`, `todo.machine.md`, `.editorconfig`, `.codexignore`.
- Reports: `reports/verify.json`, `reports/review.json`, `reports/status.json`, `reports/doctor.json`.
- Release guard: `agentcall ship` blocks on failed checks or open micro tasks.

## 4. Recovery Playbook
- Pipeline tuning: adjust `SDK_*_COMMANDS` within `.agentcontrol/config/commands.sh`.
- Emergency reset: restore `config/commands.sh` from the template, run `agentcall verify`.
- Task board recovery: restore `data/tasks.board.json`, clear `state/task_selection.json`, archive `journal/task_events.jsonl`.
- Agent credentials: remove `state/agents/` or run `agentcall agents logout`.

## 7. Offline Update Cache Runbook
1. Build or obtain the target wheel (see `docs/release.md`).
2. Stage the artefact via:
   ```bash
   agentcall cache add ~/dist/agentcontrol-<version>-py3-none-any.whl
   ```
3. Export `AGENTCONTROL_AUTO_UPDATE_CACHE=/path/to/cache` (or rely on default `~/.agentcontrol/cache`).
4. Validate inventory:
   ```bash
   agentcall cache list
   ```
5. Monitor fallback telemetry under `auto-update` events (`fallback_attempt`, `fallback_succeeded`, `fallback_failed`).
6. For dry-runs inside the repository, export `AGENTCONTROL_ALLOW_AUTO_UPDATE_IN_DEV=1` and `AGENTCONTROL_FORCE_AUTO_UPDATE_FAILURE=1` to simulate PyPI outages; reset `~/.agentcontrol/state/update.json` between runs as needed.

## 5. References
- Architecture manifest: `architecture/manifest.yaml`.
- Change control: `docs/changes.md`, `docs/adr/`, `docs/rfc/`.
- Tutorials: `docs/tutorials/` (docs bridge adoption, mission control walkthrough, MCP integration, automation hooks).
- Troubleshooting: `docs/troubleshooting/docs_bridge.md`.
- Planning artefacts: `architecture_plan.md`, `todo.md` — поддерживаются строго актуальными и полными (см. §2).
- Docs bridge: `agentcall docs diagnose|info|list|diff|repair|adopt|rollback --json` работают поверх `.agentcontrol/config/docs.bridge.yaml`, управляя маркерами непосредственно в боевой документации; managed регионы находятся в исходных `docs/` файлах — дублирующих деревьев нет. Анкоры (`insert_after_heading`, `insert_before_marker`) управляют первой вставкой; адаптеры поддерживают MkDocs/Docusaurus/Confluence через `mode: external`.
- Mission control & digital twin (roadmap): `agentcall mission --json` создаёт/читает `.agentcontrol/state/twin.json`, предоставляя агенту вектор текущего статуса (docs/tests/tasks/MCP).
- **Self-hosting caveat:** при разработке самого SDK не используем встроенные системные команды (`agentcall init/status/...`) для управления проектом. Планирование ведём вручную в `architecture_plan.md` и `todo.md`, чтобы исключить рекурсивные побочные эффекты. Любые изменения фиксируем здесь.
- Script inventory: `scripts/` (including `scripts/agents/*.sh`, `scripts/lib/*.py`).
- Status snapshots: `reports/status.json`, `reports/architecture-dashboard.json`.
- Agent authentication state: `state/agents/auth_status.json`.

## 6. Escalation
- Owners: AgentControl Core (see YAML header).
- Raise issues via `agentcall agents workflow --task=<ID>` with SLA context; escalate directly to owners for critical incidents.
