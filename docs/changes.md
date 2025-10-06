## 0.5.2 — 2025-10-06
- `agentcall help` выводит контекстную справку (статус verify, watch-регламенты, рекомендации, ссылки на документацию) и поддерживает `--json`.
- `agentcall upgrade` auto-detects legacy `agentcontrol/` capsules, offers `--dry-run/--json`, migrates to `.agentcontrol/`, and keeps a timestamped backup.
- Verify pipeline gains `make-alignment` guard: Makefile targets must mirror CLI pipelines; dry-run emits actionable hints.
- Added unit coverage for upgrade scenarios (`tests/cli/test_upgrade_command.py`) and Makefile guard (`tests/scripts/test_make_alignment.py`).
- `agentcall extension` CLI scaffolds/list/lints/publishes extensions with catalog export; sandbox verify checks an example extension.
- Two reference extensions (`examples/extensions/auto_docs`, `auto_perf`) and a dedicated tutorial document the workflow.
- `agentcall mission dashboard` provides curses TUI, static mode, and HTML snapshot for docs/quality/tasks/mcp/timeline sections.
- `agentcall mission dashboard --serve` ships a stdlib web server (SSE feed + `/playbooks/<issue>` REST trigger) with `docs/mission/dashboard_web.md` as the operator guide.
- Mission watcher actions now record `actorId`, `origin`, remediation outcomes, and taxonomy tags, feeding `watch.json`, `journal/task_events.jsonl`, and mission dashboards.
- `agentcall mission watch` automates playbooks based on timeline events, writes `reports/automation/watch.json` & `sla.json`, and honours `.agentcontrol/config/watch.yaml` / `sla.yaml`.
- Mission analytics/summary expose aggregated activity (sources/actors/tags, last operation), TUI headers reflect filters, a snapshot lands in `reports/mission-activity.json`, and verify checks its integrity.
- GitHub Actions release workflow теперь автоматически запускается при push в `main` и публикует пакет на PyPI (при наличии `PYPI_TOKEN`).

## 0.4.4 — 2025-10-05
- The performance remediation flow now creates follow-up tasks (`reports/tasks/PERF-*.json`, `.agentcontrol/state/perf_tasks.json`), keeps their status in sync, and emits `task.followup.*` timeline events.
- Mission twin/analytics list performance tasks with recommended actions and update the dashboard (`reports/architecture-dashboard.json`).
- `mission ui` renders the performance tasks, and `mission analytics --json` includes them in the summary payload.

## 0.4.3 — 2025-10-05
- Automated performance regression follow-up: `scripts/perf/compare_history.py` writes `reports/automation/perf_followup.json` (status plus recommendation) and emits `perf.regression` events.
- Mission twin/analytics expose activity, acknowledgements, and performance follow-ups; the dashboard (`reports/architecture-dashboard.json`) refreshes via `mission analytics`.
- `mission ui` displays acknowledgements and recommendations, while `mission exec`/autopilot update `mission_ack.json`.

## 0.4.2 — 2025-10-05
- `agentcall mission analytics` now emits a combined activity/ack/performance summary; mission summary mirrors recent actions, acknowledgement states, and performance regressions.
- Autopilot actions update `.agentcontrol/state/mission_ack.json` and the performance overview; follow-up payloads land in `reports/automation/perf_followup.json`.
- `scripts/perf/compare_history.py` builds the follow-up payload and `perf.regression` timeline events; the CLI dashboard renders the acknowledgement/performance summary.
- `mission ui` renders acknowledgements, performance deltas, and hotkeys; verify now includes the `scripts/check_hint_docs.py` lint stage.

## 0.4.1 — 2025-10-05
- Mission twin now captures mission activity (`reports/automation/mission-actions.json`), and the dashboard surfaces the latest actions.
- Team playbooks gained runtime/status tasks plus the automated `perf_regression` playbook; `agentcall mission exec --issue` supports targeted runs.
- `scripts/perf/compare_history.py` appends `perf.regression` timeline events and ships with regression tests; timeline hints now include `hintId`/`docPath` validated by `scripts/check_hint_docs.py`.
- Mission UI logs palette actions, exports palette JSON to `mission_palette.json`, and the CLI processes the associated hotkeys and entries.

## 0.4.0 — 2025-10-05
- Mission UI command palette now supports hotkeys (`mission ui` ↔ `mission_palette.json`), interactive playbook/automation hook launches, and `mission.ui.action` telemetry.
- `mission exec --issue` adds extended playbook actions: quality reruns (`verify`) and MCP diagnostics (warnings when endpoints are missing), plus new JSON telemetry fields (`category`, `action`).
- Timeline events carry `hintId`/`docPath` pointers to tutorials and the architecture plan; tutorials add the `perf_nightly` guide and GitHub Actions example (`examples/github/perf-nightly.yaml`).
- The verify pipeline includes the `perf-history` step and nightly workflow guidance; automation hooks and palettes persist in `mission_palette.json` and `reports/automation/` for agents.

## 0.3.31 — 2025-10-05
- Governance: the AGENTS charter now mandates immediate version bumps (`pyproject.toml` + `agentcontrol/__init__.py`) with instant git commit/push. Versioning uses majors for large changes, tenths for feature work, and hundredths for surgical fixes.

## 0.3.3 — 2025-10-05
- `agentcall mission exec` now respects CLI shorthands (`mission exec <path>`) and emits structured telemetry payloads with playbook/action context; tests cover event logging.
- Templates ship `.agentcontrol/config/automation.sh` with verify hooks that append docs diff / mission summary / MCP status reports to `reports/automation/` and load automatically via `sdk::load_commands`.
- Added `scripts/perf/compare_history.py` with verify integration to diff nightly docs benchmarks, persist JSON history, and alert on regressions; new tests validate regression detection and retention trimming.
- Mission timeline hints surface actionable remediation strings (docs sync, QA reruns, MCP status, task sync) and documentation updates describe the richer hints + automation artefacts.
- Managed region engine writes using UTF-8 surrogatepass to preserve non-BMP inputs covered by property tests.

## 0.3.2 — 2025-10-04
- Added the `agentcall cache` helper (`download`, `add`, `list`, `verify`) to streamline preparing offline wheels before running in air-gapped environments.
- Persisted auto-update telemetry summaries into `reports/status.json` and `context/auto-update-summary.json`, making fallback/success events visible to mission control.
- Introduced `AGENTCONTROL_ALLOW_AUTO_UPDATE_IN_DEV=1` and `AGENTCONTROL_FORCE_AUTO_UPDATE_FAILURE=1` flags to safely simulate PyPI outages during local debugging.
- Auto-update fallback now defaults to `~/.agentcontrol/cache` even when `AGENTCONTROL_AUTO_UPDATE_CACHE` is unset, eliminating widespread `fetch_failed` statuses when preloaded wheels exist.
- `scripts/release.sh` builds an isolated temporary venv, installs build/twine, and automatically adds the fresh wheel to the offline cache to simplify closed-network support.
- CLI hints and auto-bootstrap: `agentcall` auto-initialises the capsule when permitted and prints "This directory is not an AgentControl project." to orient operators.
- Docs bridge: `.agentcontrol/config/docs.bridge.yaml` configures target files, and `architecture-sync` fills managed regions in existing documentation without duplicating `docs/`.
- `agentcall init` now adopts an existing `docs/` directory, wiring the bridge without overwriting user files.

## 0.3.1 — 2025-10-04
- Added automatic self-update before command execution with telemetry, configurable modes (`AGENTCONTROL_AUTO_UPDATE_MODE`), and environment-based overrides (`AGENTCONTROL_DISABLE_AUTO_UPDATE`, `AGENTCONTROL_AUTO_UPDATE=0`).
- Introduced offline auto-update fallback via `AGENTCONTROL_AUTO_UPDATE_CACHE`, selecting the newest cached wheel when the network is unreachable and surfacing dedicated telemetry statuses.
- Added developer overrides `AGENTCONTROL_ALLOW_AUTO_UPDATE_IN_DEV=1` and `AGENTCONTROL_FORCE_AUTO_UPDATE_FAILURE=1` to validate fallback without leaving the repository.
- Updated documentation and templates to describe the auto-update experience and exit-on-upgrade behaviour.
- Dependency alignment: pinned `packaging>=25.0` across CLI and lockfiles.

## 0.3.0 — 2025-10-04
- Rebranded to *AgentControl Universal Agent SDK* with corporate documentation (README, AGENTS charter, architecture brief).
- Auto-initialisation now opt-in (`AGENTCONTROL_AUTO_INIT=1`) with explicit disable override (`AGENTCONTROL_NO_AUTO_INIT=1`) and improved onboarding hints when no capsule is detected.
- Roadmap/status scripts now tolerate empty epics, big tasks, and milestones, emitting actionable warnings without failing pipelines.
- Templates 0.3.0 provide nested capsule layout, packaged dotfiles, mission control hooks, and `PYTHONPATH` injection under `./.agentcontrol/`.

## 0.2.1 — 2025-10-04
- Improved project detection errors with guidance (`agentcall status` outside project).
- Added telemetry commands and plugin APIs to CLI.
- Hardened release pipeline and PyPI packaging flow.

## 0.2.0 — 2025-10-04T00:00:00Z
- Added template-aware bootstrap (`agentcall init --template`), packaged templates for Python/Node/Monorepo.
- Introduced plugin system with sample `hello-plugin` and CLI commands `agentcall plugins ...`.
- Added telemetry framework (`agentcall telemetry report|tail|clear`) with opt-out via `AGENTCONTROL_TELEMETRY`.
- Hardened release pipeline (`scripts/release.sh`, GitHub workflow) and changelog tooling.
