# TODO — Agent-First Roadmap Backlog

## Phase 0 (Sprint)
- [x] JSON Schema for `docs.bridge.yaml` + `agentcall docs diagnose --json`.
- [x] Managed region engine: removal, multi-section, atomic writes, detection проломленных маркеров.
- [x] `agentcall status --json`: expose `docsBridge` summary + warnings.
- [x] Error codes & remediation hints for all docs bridge failures.
- [x] CLI `agentcall docs info --json` (capabilities & sections).
- [x] Tests: init_existing_docs, doc removal, marker corruption, atomic file ops.
- [x] Project Twin v0: generate `.agentcontrol/state/twin.json` + `agentcall mission --json` summary replacing Memory Heart.
- [x] Sunset legacy Memory Heart scripts/config/tests (done).

## Phase 1
- [x] Anchor placement (insert_after heading / marker), multi-block support.
- [x] External adapters (MkDocs, Docusaurus, Confluence) with dry-run + retries.
- [x] CLI suite `docs list|diff|repair|adopt|rollback` (JSON output & docs).
- [x] `agentcall info --json` capabilities manifest.
- [x] Telemetry event schema (start/success/error events).
- [x] MCP manager: `agentcall mcp add|remove|status`, store configs under `.agentcontrol/config/mcp/`.
- [x] Mission control streaming view (TUI/web) reading twin.json.

## Phase 2
- [x] Define `.agentcontrol/runtime.json` schema & event spec.
- [x] Implement streaming event channel + Python helper (`agentcontrol.runtime`).
- [x] Integration test: scripted agent performing init → sync → docs update via JSON interfaces.
- [x] Automation recipes (`agentcall auto docs|tests|release`) with guardrails.
 - [x] Self-healing playbooks surfaced via mission events.

## Phase 3
- [x] `agentcall migrate` (dry-run, ask/auto, backup, rollback).
- [x] Legacy detection + autoplan (diff preview).
- [x] Telemetry counters for migration results.

## Phase 4
- [x] Property/fuzz tests for doc parser & CLI JSON.
- [x] Performance benchmarks (1k+ files) + optimisation plan.
- [x] Tutorials, sample repos, troubleshooting guide.
- [x] Developer sandbox (`agentcall sandbox start`) for agent experimentation.
- [x] Mission dashboard polish (filters, timeline, drill-down).

## Phase 5
- [ ] Automated upgrade step to rewrite legacy `./agentcontrol/` pipelines to the new `.agentcontrol/` capsule layout.
- [ ] Verify/ship pipeline guard that ensures `Makefile` stays consistent with registered CLI pipelines.

## Phase 5 (Complete)
- [x] `agentcall mission exec` auto-executes топовый плейбук и логирует результат в telemetry.
- [x] Ship verify hook library (`.agentcontrol/config/automation.sh`) + программу for templates/Docs.
- [x] Nightly perf comparisons (history vs baseline) с алертами при превышении порога.
- [x] Расширить timeline hints (links/guides) и документацию по ремедиациям.
- [x] Mission UI command palette для быстрого запуска playbooks и automation hooks.
- [x] Publish reference pipeline for nightly perf history (`.github/workflows/perf-nightly.yaml`).
- [x] Расширить `mission exec` (quality/mcp/tasks/runtime/perf) + ack telemetry.
- [x] Привязать timeline hints к разделам документации (knowledge base identifiers).
- [x] Mission UI palette → `mission-actions.json` + telemetry `mission.ui.action`.
- [x] Perf regression alerts + follow-up payload + automatic tasks (`perf_tasks.json`, `reports/tasks/PERF-*.json`).
- [x] Mission analytics (`agentcall mission analytics`) + dashboard sync.
- [x] Шаблоны 0.4.4 с актуальными скриптами и governance.

## Phase 6 — Bootstrap & Profiles
- [x] `agentcall bootstrap` wizard (опрос стека, CICD, MCP, repo scale) → `.agentcontrol/state/profile.json`, `reports/bootstrap_summary.json`.
- [x] Профили по умолчанию (`profiles/python.yaml`, `profiles/monorepo.yaml`, `profiles/meta.yaml`).
- [x] Onboarding checklist `docs/getting_started.md` + update README/AGENTS с ссылкой.
- [x] Doctor enhancements: `agentcall doctor --bootstrap` (проверка версий, MCP доступности, hints).

## Phase 7 — Extension Ecosystem
- [ ] Extension SDK: `agentcall extension init|add|list|remove` с каталогом `extensions/`.
  - [ ] Поддержка кастомных playbooks (YAML/py), automation hooks, MCP адаптеров, CLI команд.
  - [ ] Schema + валидация + тестовые фикстуры (`tests/extensions`).
- [ ] Extension registry (`reports/extensions.json`) + marketplace docs.
- [ ] Tutorial `docs/tutorials/extensions.md` и примеры (hook, playbook, MCP). 

## Phase 8 — Mission Dashboard UX
- [ ] TUI dashboard `agentcall mission dashboard` (панели: docs/quality/tasks/perf/mcp/timeline, hotkeys, ack indicators).
- [ ] Web UI (`agentcall mission dashboard --serve`) с авторизацией (read-only vs control), построено на twin + analytics JSON.
- [ ] Snapshot экспорт (`reports/mission/dashboard-<ts>.html`) для статусов.

## Phase 9 — Automation Watcher & Notifications
- [ ] Демон `agentcall mission watch` (follow-up: автозапуск playbooks при событиях `perf.regression`, `docs_drift`, `verify_failed`).
- [ ] Notification adapters (Slack, email, generic webhook) с конфигом `.agentcontrol/config/alerts.yaml`.
- [ ] SLA policies: эскалация при просрочке perf follow-up (N часов) и docs drift.
- [ ] Telemetry enrichment: actor, remediation outcome, auto-tagging задач.

## Phase 10 — Task Ecosystem Integration
- [ ] Sync perf tasks ↔ `data/tasks.board.json` (создание, обновление, закрытие, ссылки на playbooks).
- [ ] Внешние коннекторы (Jira/GitHub Issues) — CLI `agentcall tasks sync --jira` с конфигом `config/tasks.yaml`.
- [ ] Backfeed: изменение статуса во внешней системе → обновление `mission_ack.json`/follow-up.
- [ ] Интеграционные тесты (mock Jira API, GitHub). 

## Phase 11 — Knowledge & Documentation DX
- [ ] Docs portal генератор (`agentcall docs portal`) → статический HTML/MD из tutorials/guides.
- [ ] Knowledge lint расширить: проверка устаревших ссылок, orphan tutorials, coverage отчёт (`reports/docs_coverage.json`).
- [ ] Автоматический changelog/релиз-ноты (`agentcall release notes`).
- [ ] Sample gallery: mono, poly, meta-repo (100+ реп), включая CI wiring.

## Phase 12 — Meta-Repo & Scale Readiness
- [ ] Meta workspace descriptor (`workspace.yaml`) с поддержкой сотен реп → `agentcall mission summary --workspace` агрегирует статусы.
- [ ] Distributed agents: конфиг роли/квоты, scheduler задач (`agentcall mission assign`).
- [ ] Шардированные perf бенчмарки (parallel docs_benchmark + отчет per shard).
- [ ] Stress/fuzz tests для meta workflows и massive documentation trees.

## Phase 13 — Install/Distribution UX
- [ ] Упаковать bootstrap installer (`agentcontrol-install.sh`, pipx recipe) с проверкой зависимостей.
- [ ] Кэш management (`agentcall cache doctor`) для шаблонов/скриптов.
- [ ] Binary bundle/standalone? исследование + PoC.
- [ ] Telemetry opt-in/out wizard.

> Self-hosting: планы ведём здесь и в `architecture_plan.md`; автоматикой agentcall проект не управляємо.

> Self-hosting: планы ведём здесь и в `architecture_plan.md`; автоматикой agentcall проект не управляємо.
