# AgentControl SDK — Agent-First Architecture Blueprint
> **Goal:** make `.agentcontrol/` the effortless control plane for autonomous agents. Any project, any existing documentation, no manual babysitting.

---
## 1. Agent Personas & Journeys
| Persona | Goals | Core Journey |
| --- | --- | --- |
| **AgentInitializer** | Bootstrap SDK in legacy repo, map existing docs, run first sync | Detect project doc setup → `agentcall init` → configure bridge → `architecture-sync` → report results |
| **AgentMaintainer** | Keep docs/architecture aligned during work | Change manifest → `agentcall run architecture-sync` → inspect doc diff → commit |
| **MigrationAgent** | Upgrade legacy `agentcontrol/docs` projects | `agentcall migrate --dry-run` → human approval → migration → rollback if desired |

Each journey must expose machine-friendly APIs (JSON) and actionable events.

---
## 2. Success Criteria (0.5.x hardening)
| Category | Metric | Target |
| --- | --- | --- |
| Template Integrity | Packaged templates checksum == repo snapshot, `agentcall verify` enforces | 100% runs |
| Init UX | `agentcall init` (existing docs) finishes ≤ 20s, zero manual prompts | 100% scenarios |
| Agent Digest | `agentcall status --json` emits `agent_digest` payload ≤ 4 KB with latest AGENTS/todo summary | Every invocation |
| Pipeline SLA | Each verify step emits structured log with duration ≤ configured timeout (default 90s) | 100% steps |
| Docs Sync | Consecutive `architecture-sync` produces no diff | 0 unexpected diffs |
| Error UX | All blocking errors emit structured code + remediation hint | 100% |
| Compatibility | Legacy migration pass rate | 100% tested repos |
| Quality | diff coverage ≥ 90%, pytest/verify green | Continuous |

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

---
## 4. Current Baseline (2025-10-06)
- Packaged capsule templates (0.5.1) exist in-tree, но git состояние содержит удалённые артефакты `.agentcontrol/` → `agentcall init/upgrade` ломаются.
- Verify конвейер жёсткий, но отсутствуют SLA per-step timeouts и structured log/JSON сводки.
- Нет компактного контекстного дайджеста: агентам приходится читать целый `AGENTS.md`/`todo.machine.md`.
- Updater/mission сервисы покрыты тестами частично; сценарии с offline-cache, timeline ingest и dev guard остаются незафиксированными.
- Docs bridge схемы и managed регионы стабильны, но отсутствует автоматический контроль целостности шаблонов.

---
## 5. Roadmap Phases
### Phase 0 – Foundation Hardening (current sprint)
**Objectives**
- Восстановить эталонные шаблоны и `.agentcontrol/` капсулу, исключить дрейф и поломку auto-bootstrap.
- Снизить когнитивную нагрузку агентов через автоматический digest и SLA по времени выполнения пайплайна.
- Поднять покрытие критичных сервисов (updater, mission) для защиты от регрессий.

**Deliverables & Acceptance**
1. **Template Integrity Wall** – `agentcall verify` выполняет шаг `template-integrity` (checksum diff → fail). Каталоги `.agentcontrol/` и `src/agentcontrol/templates/0.5.1` свернуты к эталону; git status чистый.
2. **Agent Digest + SLA** – CLI формирует `.agentcontrol/state/agent_digest.json` (≤4 KB, содержит health/tasks summary). Каждый шаг `scripts/verify.sh` протоколирует JSON (`step`, `status`, `durationMs`, `timeoutMs`) и поддерживает конфигурируемый таймаут.
3. **Coverage Expansion** – pytest модули для updater (force failure, cache fallback, dev guard) и mission twin (timeline ingest, palette persist) обеспечивают ≥90 % diff coverage по изменённым файлам.
4. **Docs Refresh** – README, `docs/getting_started.md`, AGENTS.md, todo.machine.md отражают digest, template wall и SLA.

**Phase update (2025-10-06):** Integrity guard и агентский digest внедрены: verify теперь включает `template-integrity`, генерирует `reports/verify_steps.jsonl` и `.agentcontrol/state/agent_digest.json`, а per-step SLA контролируется `VERIFY_STEP_TIMEOUT`. Unit-тесты для updater/mission добавлены. Остаётся синхронизировать исторические `.agentcontrol` артефакты и закрыть legacy warnings.

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

**Phase update (2025-10-05):** Hypothesis-powered property/fuzz tests cover managed regions and CLI JSON, sandbox CLI ships with templated capsule + unit tests, mission dashboard добавляет `--filter`/`detail`, ранжирует плейбуки по приоритету с подсказками, а docs включают tutorials (включая automation hooks), troubleshooting и sample MCP/sandbox репозитории. Performance benchmark (`scripts/perf/docs_benchmark.py`) фиксирует `docs diagnose` p95=646 мс на 1 200 секций, verify теперь гоняет связку `perf-docs`/`check_docs_perf` и держит порог ≤60 с на 1000 секций; кэширование конфигов и регионов снижает повторный I/O практически до нуля.

### Phase 5 – Autonomous Ops Assist
- Mission autopilot: `agentcall mission exec` запускает рекомендованный плейбук, логирует исход.
- Actionable telemetry: timeline события тегируются хинтами + remediate scripts.
- Verify hook library: пакет `automation/hooks.sh` с типовыми `SDK_VERIFY_COMMANDS` (docs sync, perf, QA).
- Continuous perf guard: `perf-docs` выносится в nightly + сравнение с историей.
- Agent UX polish: command palette / cheatsheet для основных автоматизаций.

**Phase update (2025-10-05):** mission exec CLI фиксирует шорткаты и логирует playbook/action, verify hooks подгружаются автоматически через `.agentcontrol/config/automation.sh`, nightly perf сравнивается скриптом `scripts/perf/compare_history.py` (история+diff), mission UI получила command palette (hotkeys + JSON API `mission_palette.json`), а timeline hints теперь включают `hintId`/`docPath` и ведут в tutorials (`docs/tutorials/auto…`, `perf_nightly`, `mcp_integration`). Референс workflow (`examples/github/perf-nightly.yaml`) закрепляет nightly perf guard.

### Phase 6 – Bootstrap & Profiles
- Bootstrap wizard: capture stack, CI/CD, MCP, repo scale, automation focus, constraints.
- Default profiles: python/monorepo/meta curated requirements & automation hints.
- Onboarding docs: flagship getting-started guide linked from README/AGENTS.
- Doctor enhancements: bootstrap-focused health checks with JSON output.

**Phase update (2025-10-05):** `agentcall bootstrap` now persists `.agentcontrol/state/profile.json` and `reports/bootstrap_summary.json`, loading curated YAML profiles and emitting operator recommendations. `docs/getting_started.md` documents the checklist, with README/AGENTS linking directly. `agentcall doctor --bootstrap` validates Python runtime, packaged profile drift, and MCP connectivity, returning structured telemetry events.

---
## 6. Risk Register
| Risk | Impact | Mitigation |
| --- | --- | --- |
| Conflicting manual edits | Broken managed region | Detect at sync → emit `DOC_BRIDGE_CONFLICT` with diff, require approve/diff |
| External API failures | Sync abort | Provide dry-run + retries/backoff, surface error code, leave host docs untouched |
| Large repo perf | Slow agents | Incremental hashing, parallel chunk updates, telemetry for hotspots |
| Missing markers | Data loss risk | Treat as error, suggest `agentcall docs repair` |
| Migration rollback | Lost docs | Automatic backups + `rollback` command |

---
## 7. Quality & Testing Strategy
- **Unit**: doc parser, config validation, CLI JSON schema tests.
- **Integration**: agent journeys (init, sync, migrate) scripted via CLI JSON outputs.
- **Property**: fuzz managed region editing (random whitespace, multiple markers).
- **Performance**: synthetic repo with 1k+ docs, measure runtime.
- **Manual QA**: weekly run across sample stacks (python/node/monorepo).

---
## 8. Observability & Telemetry
- Structured logs `doc_bridge` with fields: `section`, `mode`, `target`, `duration`, `status`.
- Event stream schema (JSON): `{type, section, stage, severity, remediationHint}`.
- Telemetry counters for init/sync success/failure, migration stats.

---
## 9. Migration Blueprint
1. Detect legacy artifacts (`agentcontrol/docs`, missing bridge config).
2. Generate migration plan: mapping, new config, diffs.
3. Present via `agentcall migrate --dry-run --json`.
4. On approval: insert markers, update state, backup old files.
5. Provide rollback instructions with timestamp.

---
## 10. Communication Plan
- Update `AGENTS.md` (self-hosting caveat, docs bridge usage).
- Release notes per phase (Changelog entries).
- Publish tutorials + sample repos.
- Telemetry dashboards for adoption metrics.

---
## 11. Immediate Next Steps (0.4.x → 0.5 Roadmap)
- Bootstrap adoption telemetry: surface profile status in mission dashboard & doctor JSON feeds.
- Extension ecosystem: CLI/API для кастомных playbooks/hooks/MCP, registry и tutorial.
- Mission dashboard UX: TUI + web UI поверх twin/analytics, snapshot экспорт.
- Automation watcher & notifications: фоновые auto playbooks, Slack/email/webhook алерты, SLA.
- Task integration: синхронизировать perf follow-up с `data/tasks.board.json` + внешние PM (Jira/GitHub).
- Knowledge & docs DX: портал, lint coverage, auto changelog.
- Meta-repo readiness: workspace descriptor, distributed agents, шардированные perf.
- Distribution UX: bootstrap installer, cache doctor, telemetry opt-in.

> **Self-hosting constraint:** development tracked via `architecture_plan.md` + `todo.md`; no recursive usage of agentcall automation on the SDK itself.
