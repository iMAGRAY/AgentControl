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

## Phase 5 (In Progress)
- [x] `agentcall mission exec` auto-executes топовый плейбук и логирует результат в telemetry.
- [x] Ship verify hook library (`.agentcontrol/config/automation.sh`) + программу for templates/Docs.
- [x] Nightly perf comparisons (history vs baseline) с алертами при превышении порога.
- [x] Расширить timeline hints (links/guides) и документацию по ремедиациям.

## Phase 6 (Backlog)
- [x] Mission UI command palette для быстрого запуска playbooks и automation hooks.
- [x] Publish reference pipeline for nightly perf history (`.github/workflows/perf-nightly.yaml`).
- [x] Расширить `mission exec` (quality/mcp плейбуки + telemetry context).
- [x] Привязать timeline hints к разделам документации (knowledge base identifiers).
- [ ] Mission UI command palette command palette hotkeys persist to telemetry dashboard (export to reports/automation/mission-actions.json).
- [ ] Integrate perf regression alerts with mission timeline (auto `perf.regression` event).

> Self-hosting: планы ведём здесь и в `architecture_plan.md`; автоматикой agentcall проект не управляємо.
