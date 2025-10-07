# AgentControl SDK — Agent-First Architecture Blueprint
> **Goal:** make `.agentcontrol/` the effortless control plane for autonomous agents. Any project, any existing documentation, no manual babysitting.

---
## 1. Agent Personas & Journeys
| Persona | Goals | Core Journey |
| --- | --- | --- |
| **AgentInitializer** | Bootstrap SDK in legacy repo, map existing docs, run first sync | Detect project doc setup → `agentcall quickstart` (init + verify) → configure bridge → `architecture-sync` → report results |
| **AgentMaintainer** | Keep docs/architecture aligned during work | Change manifest → `agentcall run architecture-sync` → inspect doc diff → commit |
| **MigrationAgent** | Upgrade legacy `agentcontrol/docs` projects | `agentcall migrate --dry-run` → human approval → migration → rollback if desired |

Each journey must expose machine-friendly APIs (JSON) and actionable events.

---
## 2. Success Criteria (0.5.x hardening)
| Category | Metric | Target |
| --- | --- | --- |
| Template Integrity | Packaged templates checksum == repo snapshot, `agentcall verify` enforces | 100% runs |
| Init UX | `agentcall quickstart` finishes ≤ 20s, zero manual prompts, emits structured report | 100% scenarios |
| Agent Digest | `agentcall status --json` emits `agent_digest` payload ≤ 4 KB with latest AGENTS/todo summary | Every invocation |
| Pipeline SLA | Each verify step emits structured log with duration ≤ configured timeout (default 90s) | 100% steps |
| Docs Sync | Consecutive `architecture-sync` produces no diff | 0 unexpected diffs |
| Error UX | All blocking errors emit structured code + remediation hint | 100% |
| Compatibility | Legacy migration pass rate | 100% tested repos |
| Quality | diff coverage ≥ 90%, pytest/verify green | Continuous |
| Sandbox Discipline | `.test_place/` remains the only in-repo sandbox; packaged SDK never bundles development artefacts | Always |

## 0. Phase 4 Delivery Contract
AC::FUNC-7::command_exists::agentcall sandbox start::—::scope=.agentcontrol
AC::UX-4::mission_dashboard_filters::>=3::—::includes=docs,qa,tasks
AC::QA-7::property_tests::>=2::—::targets=docs_bridge,cli_json
AC::QA-8::diff_coverage::>=90%::—::changed_lines_only
AC::PERF-2::docs_auto_p95_ms::<=60000::—::dataset=1000_files
AC::DOC-5::tutorials_published::>=3::—::formats=guide,troubleshooting,sample_repo

### Assumptions Ledger
- **A1**: Mission twin pipeline can ingest timeline data from `journal/task_events.jsonl`. *Verification*: Step 3 updates mission service and tests ensure ingestion.
- **A2**: Sandbox launch may reuse packaged templates under `src/agentcontrol/templates`. *Verification*: Step 2 validates by integration test.
- **A3**: Performance harness can run locally within ≤5 min using Python stdlib. *Verification*: Step 5 executes benchmark script.
- **A4**: Hypothesis is allowed in dependency tree without license conflicts. *Verification*: Step 4 updates SBOM/licence checks via tests.
- **A5**: Tutorials can live under `docs/tutorials/` without breaking managed regions. *Verification*: Step 6 runs docs bridge diagnose after additions.

### Unknowns & Risks
1. Telemetry log may grow large during benchmarks (risk: disk usage). *Plan*: rotate logs before benchmark; script truncates afterwards.
2. Sandbox workspace permissions may clash on Windows. *Plan*: default to POSIX temp dir; document constraints.
3. Hypothesis shrinking could slow CI. *Plan*: cap `max_examples` and parallelize tests.
4. Mission timeline parsing may fail on malformed events. *Plan*: add safe parsing with fallback + tests.
5. Sample repo copying may bloat package size. *Plan*: store as compressed fixtures and exclude from wheel via MANIFEST.

### Domain Glossary
- **Sandbox Capsule**: Disposable project skeleton generated under `.agentcontrol/sandbox` for experimentation.
- **Mission Twin**: JSON snapshot combining docs, roadmap, QA, and timeline signals.
- **Bridge Section**: Managed documentation region defined in `docs.bridge.yaml`.
- **Automation Recipe**: Predefined CLI workflow executed via `agentcall auto <target>`.
- **MCP Registry**: Catalog of MCP servers stored under `.agentcontrol/config/mcp`.

### Decision Criteria
1. Correctness (0.35) – all ACs met, tests/property/fuzz pass.
2. Performance (0.25) – benchmarks stay within 60s p95 goal.
3. Simplicity (0.20) – commands intuitive, zero manual babysitting.
4. Evolvability (0.15) – DDD boundaries & schemas documented.
5. Cost (0.05) – minimal ongoing maintenance, no heavy deps.


---
## 3. Principles
1. **Declarative Everything** – config/commands must be machine editable (`agentcall … --json`).
2. **Immutable Capsule** – everything lives in `.agentcontrol/`; no host pollution.
3. **Bridge not Clone** – managed regions with anchors; no parallel doc trees.
4. **Explainable Failure** – error code + message + remediation.
5. **Transactional Safety** – atomic writes, backups, rollback utilities.
6. **Observability** – structured events/logs with correlation ids.
7. **No Recursive Hosting** – the SDK repository never instantiates `.agentcontrol/`; all simulations live under `.test_place/` or external fixtures.

---
## 4. Self-Hosting Sandbox Discipline
- Development-only assets (`.test_place/**`, `state/**`, `reports/**` produced by `scripts/test-place.sh`) stay ignored and are pruned before packaging.
- Packaged templates stamp `AGENTS.md` alongside `.agentcontrol/`; developer governance files from this repo never ship inside the capsule.
- Integration tests must call `scripts/test-place.sh` or dedicated fixtures, never `agentcall …` directly inside the SDK repo.
- Global installers (`scripts/update-global.sh`) remain user-local helpers and stay excluded from wheels/published artefacts.
- Verify pipeline guards (`template-integrity`, `make-alignment`, upcoming `extension-integrity`) enforce the boundary automatically.

---
## 5. Current Baseline (2025-10-06)
- Packaged capsule templates (0.5.1) are present in-tree, but git still lists removed `.agentcontrol/` artefacts, breaking `agentcall init/upgrade`.
- The verify pipeline is strict, yet lacks per-step SLA timeouts and structured JSON step summaries.
- No compact contextual digest exists: agents must read the entire `AGENTS.md`/`todo.machine.md`.
- Updater/mission services have partial coverage; offline-cache, timeline ingest, and dev guard scenarios are untested.
- Docs bridge schemas and managed regions are stable, but there is no automated template integrity enforcement.

---
## 6. Roadmap Phases
### Phase 0 – Foundation Hardening (current sprint)
**Objectives**
- Restore the canonical templates and `.agentcontrol/` capsule to eliminate drift and auto-bootstrap failures.
- Reduce agent cognitive load through an automatic digest and per-step pipeline SLAs.
- Increase coverage of critical services (updater, mission) to guard against regressions.

**Deliverables & Acceptance**
1. **Template Integrity Wall** – `agentcall verify` runs the `template-integrity` step (checksum drift fails the build). `.agentcontrol/` and `src/agentcontrol/templates/0.5.1` match the canonical tree; git status is clean.
2. **Agent Digest + SLA** – CLI writes `.agentcontrol/state/agent_digest.json` (≤4 KB with health/task summary). Every `scripts/verify.sh` step logs JSON (`step`, `status`, `durationMs`, `timeoutMs`) with configurable timeouts.
3. **Coverage Expansion** – pytest modules for updater (forced failure, cache fallback, dev guard) and mission twin (timeline ingest, palette persistence) deliver ≥90% diff coverage on touched files.
4. **Docs Refresh** – README, `docs/getting_started.md`, AGENTS.md, and todo.machine.md describe the digest, template guard, and SLA expectations.

**Phase update (2025-10-06):** Integrity guard и agent digest активны; verify включает `template-integrity`, пишет `reports/verify_steps.jsonl`, управляется `VERIFY_STEP_TIMEOUT`. Добавлены unit-тесты updater/mission. Legacy `agentcontrol/` → `.agentcontrol/` авто-монтаж через `agentcall upgrade` (dry-run/JSON + бэкап), verify пополнился `make-alignment` guard, `agentcall extension` закрывает экосистему расширений (CLI/catalog/примеры), а mission dashboard получил curses TUI/HTML snapshot. Осталось синхронизировать исторические артефакты и закрыть legacy warnings.

### Phase 1 – Bridge Evolution
- Insertion anchors (`insert_after heading`, `insert_before marker`).
- External adapters: MkDocs nav (yaml merge), Docusaurus sidebar (json), Confluence REST (mode `external`).
- CLI tools: `docs list|diff|repair|adopt|rollback`, JSON output.
- Capability discovery: `agentcall info --json` enumerates SDK features, versions.
- Telemetry event spec v1 (start, success, failure; correlation id, duration).
- Mission Control UI: structured mission log streaming + basic TUI/web panel reading twin.json.
- MCP manager: `agentcall mcp add|remove|status` storing configs under `.agentcontrol/config/mcp/`.

**Phase update (2025-10-05):** Anchor policies and external adapters (MkDocs nav merge, Docusaurus sidebar sync, Confluence payload generator) are live with automated regression tests and new CLI flows. Capability discovery (`agentcall info --json`) now ships a machine/json dual output wired to telemetry schema validation, and structured events emit start/success/error with duration + component metadata. Remaining scope: mission control UI and MCP manager.

### Phase 2 – Runtime & Events
- `.agentcontrol/runtime.json` describing workflows, commands, environment.
- Streaming event channel (stdout JSON lines + optional socket) for sync progress.
- Python helper `agentcontrol.runtime` for agents (subscribe -> execute -> handle errors).
- Integration test: script simulating agent performing init→sync→docs update using JSON APIs.
- Automation recipes: `agentcall auto docs|tests|release` with guardrails (`--auto/--dry-run`).
- Self-healing playbooks for common issues (doc drift, git dirty tree) surfaced via mission events.

**Phase update (2025-10-05):** Runtime manifest + telemetry event stream are live (`agentcall runtime status|events`) with helper module `agentcontrol.runtime`. Automated JSON agent flow covered by regression tests. Automation playbooks (`agentcall auto ...`) and mission self-healing recommendations now surface in the twin; remaining scope shifts to future enhancements beyond Phase 2.

### Phase 3 – Migration & Compatibility
- `agentcall migrate` (dry-run report, ask/auto modes, backup). 
- Legacy detection (if `agentcontrol/docs` present) with autoplan.
- Observability: migration success/failure counters.
- Rollback command `agentcall docs rollback --timestamp`.

**Phase update (2025-10-05):** Migration CLI scaffolding handles legacy `agentcontrol/` capsules, emitting structured telemetry counters and state snapshots. Rollback enhancements remain future work.

### Phase 4 – Performance, QA & DX polish
- Property/fuzz tests for managed parser & CLI JSON.
- Perf benchmarks (≥1000 files) with goal sync < 60s, CPU < 2 cores.
- Enhanced docs: tutorials, code samples, troubleshooting matrix.
- Build sample repos per adapter (MkDocs, Confluence stub).
- Developer sandbox: `agentcall sandbox start` spins up disposable workspace with sample data.
- Mission dashboard polish (filters, drill-down, timeline view).

**Phase update (2025-10-05):** Hypothesis-powered property/fuzz tests cover managed regions and CLI JSON. The sandbox CLI ships with templated capsules plus unit tests. Mission dashboard adds `--filter`/`detail`, ranks playbooks by priority with hints, and documentation now bundles tutorials (automation hooks), troubleshooting, and sample MCP/sandbox repos. Performance benchmark (`scripts/perf/docs_benchmark.py`) records `docs diagnose` p95 = 646 ms for 1,200 sections; verify now runs the `perf-docs`/`check_docs_perf` pair and keeps the ≤60 s target for 1,000 sections. Config/region caching trims repeat I/O nearly to zero.

### Phase 5 – Autonomous Ops Assist
- Mission autopilot: `agentcall mission exec` runs the recommended playbook and logs the outcome.
- Actionable telemetry: timeline events carry hints plus remediation scripts.
- Verify hook library: `automation/hooks.sh` packages standard `SDK_VERIFY_COMMANDS` (docs sync, perf, QA).
- Continuous perf guard: `perf-docs` promoted to nightly runs alongside history comparisons.
- Agent UX polish: command palette and cheat sheet for core automations.

**Phase update (2025-10-05):** mission exec CLI records shortcuts and playbook/actions, verify hooks autoload via `.agentcontrol/config/automation.sh`, nightly perf comparisons run through `scripts/perf/compare_history.py` (history plus diff), mission UI received the command palette (hotkeys and JSON API `mission_palette.json`), and timeline hints now ship `hintId`/`docPath` pointing to tutorials (`docs/tutorials/automation_hooks.md`, `perf_nightly.md`, `mcp_integration.md`). The reference workflow (`examples/github/perf-nightly.yaml`) locks in the nightly perf guard.

### Phase 6 – Bootstrap & Profiles
- Bootstrap wizard: capture stack, CI/CD, MCP, repo scale, automation focus, constraints.
- Default profiles: python/monorepo/meta curated requirements & automation hints.
- Onboarding docs: flagship getting-started guide linked from README/AGENTS.
- Doctor enhancements: bootstrap-focused health checks with JSON output.

**Phase update (2025-10-05):** `agentcall bootstrap` now persists `.agentcontrol/state/profile.json` and `reports/bootstrap_summary.json`, loading curated YAML profiles and emitting operator recommendations. `docs/getting_started.md` documents the checklist, with README/AGENTS linking directly. `agentcall doctor --bootstrap` validates Python runtime, packaged profile drift, and MCP connectivity, returning structured telemetry events.

---
## 7. Risk Register
| Risk | Impact | Mitigation |
| --- | --- | --- |
| Conflicting manual edits | Broken managed region | Detect at sync → emit `DOC_BRIDGE_CONFLICT` with diff, require approve/diff |
| External API failures | Sync abort | Provide dry-run + retries/backoff, surface error code, leave host docs untouched |
| Large repo perf | Slow agents | Incremental hashing, parallel chunk updates, telemetry for hotspots |
| Missing markers | Data loss risk | Treat as error, suggest `agentcall docs repair` |
| Migration rollback | Lost docs | Automatic backups + `rollback` command |

---
## 8. Quality & Testing Strategy
- **Unit**: doc parser, config validation, CLI JSON schema tests.
- **Integration**: agent journeys (init, sync, migrate) scripted via CLI JSON outputs.
- **Property**: fuzz managed region editing (random whitespace, multiple markers).
- **Performance**: synthetic repo with 1k+ docs, measure runtime.
- **Manual QA**: weekly run across sample stacks (python/node/monorepo).

---
## 9. Observability & Telemetry
- Structured logs `doc_bridge` with fields: `section`, `mode`, `target`, `duration`, `status`.
- Event stream schema (JSON): `{type, section, stage, severity, remediationHint}`.
- Telemetry counters for init/sync success/failure, migration stats.

---
## 10. Migration Blueprint
1. Detect legacy artifacts (`agentcontrol/docs`, missing bridge config).
2. Generate migration plan: mapping, new config, diffs.
3. Present via `agentcall migrate --dry-run --json`.
4. On approval: insert markers, update state, backup old files.
5. Provide rollback instructions with timestamp.

---
## 11. Communication Plan
- Update `AGENTS.md` (self-hosting caveat, docs bridge usage).
- Release notes per phase (Changelog entries).
- Publish tutorials + sample repos.
- Telemetry dashboards for adoption metrics.

---
## 12. Immediate Next Steps (0.5.1 → 0.6 Roadmap)
1. **Phase 7 – Extension Ecosystem Hardening**: deliver command parity, packaging policy, and deterministic help UX (todo `P7.1–P7.3`). Extend verify with `extension-integrity` once manifests land.  
   **Phase update (2025-10-07):** `agentcall extension lint` now validates against `extension_manifest.schema.json`, sandbox verify publishes `reports/extensions.json`, and sample extensions are packaged with SHA256 + integrity checks.
2. **Phase 8 – Mission Dashboard Web Mode**: ✅ delivered (stateless `--serve`, SSE feed, `/playbooks/<id>` POST, docs in `docs/mission/dashboard_web.md`).
3. **Phase 9 – Automation Watcher Telemetry**: ✅ watcher actions now emit `actorId`, `origin`, remediation outcome, and taxonomy tags into `watch.json` + `journal/task_events.jsonl` (see `tests/mission/test_watch.py`).  
   **Scope adjustment (2025-10-07):** Notification adapters (`P9-002`) removed for AI-only workflows; no human-centric escalation surfaces remain in roadmap.
4. **Phase 10 – Task Ecosystem Integration**: ✅ provider-агностический sync core (`agentcall tasks sync`, отчёт `reports/tasks_sync.json`); далее — Jira/GitHub коннекторы с шифрованием и обратным фидом в миссию.
5. **Phase 11 – Knowledge & Documentation DX**: generate docs portal, knowledge lint, automated release notes, and sample gallery under package size guard.
   **Phase update (2025-10-07):** `agentcall docs portal` теперь выпускает само-достаточный сайт (`reports/docs/portal`), а `agentcall docs lint --knowledge` формирует `reports/docs_coverage.json`, проверяя заголовки/резюме/ссылки и падая на осиротевших туториалах. Портал и lint публикуют телеметрию с бюджетом и счетчиками ошибок; следующая веха — automated release notes и sample gallery.
6. **Phase 12 – Meta-Repo & Scale Readiness**: introduce workspace descriptors, distributed agent scheduler, sharded perf harness, and stress testing.
7. **Phase 13 – Install & Distribution UX**: ship bootstrap installer, cache doctor, standalone bundle research, and telemetry opt-in wizard ensuring zero-sudo installs.

> **Self-hosting constraint:** development tracked via `architecture_plan.md` + AGENTS.md (todo section); no recursive usage of agentcall automation on the SDK itself; all system-level tests run in isolated sandboxes (e.g. `.test_place/`).
