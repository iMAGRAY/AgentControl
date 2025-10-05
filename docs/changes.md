## 0.4.3 — 2025-10-05
- Автоматизирован follow-up для perf регрессий: `scripts/perf/compare_history.py` пишет `reports/automation/perf_followup.json` (status+рекомендация) и события `perf.regression`.
- Mission twin/analytics показывают activity, acknowledgements и perf follow-up; dashboard (`reports/architecture-dashboard.json`) обновляется вызовом `mission analytics`.
- `mission ui` отображает acknowledgements и рекомендации, `mission exec`/autopilot обновляют `mission_ack.json`.

## 0.4.2 — 2025-10-05
- `agentcall mission analytics` выводит activity/ack/perf сводку; mission summary отражает последние действия, ack-статусы и perf регрессии.
- Autopilot действия обновляют `.agentcontrol/state/mission_ack.json` и `perf` overview; perf follow-up сохраняется в `reports/automation/perf_followup.json`.
- `scripts/perf/compare_history.py` создаёт follow-up payload и таймлайн событие `perf.regression`; CLI dashboard показывает ack/perf сводку.
- `mission ui` рендерит acknowledgements, perf diff, hotkeys; verify дополнился lint-скриптом `scripts/check_hint_docs.py`.

## 0.4.1 — 2025-10-05
- Mission twin теперь включает mission activity (`reports/automation/mission-actions.json`), а dashboard показывает последние действия.
- Team playbooks пополнены задачами runtime/status и автоматическим плейбуком `perf_regression`; `agentcall mission exec --issue` поддерживает targeted execution.
- `scripts/perf/compare_history.py` добавляет события `perf.regression` в timeline и закрыт тестом; timeline hints снабжены `hintId`/`docPath` с проверкой `scripts/check_hint_docs.py`.
- Mission UI logирует palette actions, palette JSON экспортируется в `mission_palette.json`, CLI обрабатывает горячие клавиши и записи.

## 0.4.0 — 2025-10-05
- Mission UI command palette с hotkeys (`mission ui` ↔ `mission_palette.json`), интерактивным запуском playbooks/automation hooks и телеметрией `mission.ui.action`.
- `mission exec --issue` и расширенные playbook экшены: quality reruns (`verify`) и MCP диагностика (warning при незаполненных endpoint), новые JSON telemetry поля (`category`, `action`).
- Timeline events получили `hintId`/`docPath`, ведут к tutorials/architecture_plan; tutorials дополнены `perf_nightly` гайдом и GitHub Actions шаблоном (`examples/github/perf-nightly.yaml`).
- Verify pipeline включает `perf-history` шаг и nightly workflow инструкции; automation hooks + palette сохраняются в `mission_palette.json`/`reports/automation` для агентов.

## 0.3.31 — 2025-10-05
- Governance: AGENTS charter закрепляет обязательное обновление версий (`pyproject.toml` + `agentcontrol/__init__.py`) и мгновенный git commit/push; введена шкала — major для крупных изменений, десятичные для функциональных, сотые для точечных корректировок.

## 0.3.3 — 2025-10-05
- `agentcall mission exec` now respects CLI shorthands (`mission exec <path>`) and emits structured telemetry payloads with playbook/action context; tests cover event logging.
- Templates ship `.agentcontrol/config/automation.sh` with verify hooks that append docs diff / mission summary / MCP status reports to `reports/automation/` and load automatically via `sdk::load_commands`.
- Added `scripts/perf/compare_history.py` with verify integration to diff nightly docs benchmarks, persist JSON history, and alert on regressions; new tests validate regression detection and retention trimming.
- Mission timeline hints surface actionable remediation strings (docs sync, QA reruns, MCP status, task sync) and documentation updates describe the richer hints + automation artefacts.
- Managed region engine writes using UTF-8 surrogatepass to preserve non-BMP inputs covered by property tests.

## 0.3.2 — 2025-10-04
- Added `agentcall cache` helper (`download`, `add`, `list`, `verify`) to simplify подготовку оффлайн-колеса перед запуском в закрытых контурах.
- Persisted auto-update telemetry summary into `reports/status.json` и `context/auto-update-summary.json`, что делает события fallback/succeeded доступными для mission control.
- Ввели флаги `AGENTCONTROL_ALLOW_AUTO_UPDATE_IN_DEV=1` и `AGENTCONTROL_FORCE_AUTO_UPDATE_FAILURE=1` для безопасного моделирования отказов PyPI при локальной отладке.
- Auto-update fallback теперь по умолчанию использует `~/.agentcontrol/cache`, даже если переменная `AGENTCONTROL_AUTO_UPDATE_CACHE` не задана, что устраняет массовые `fetch_failed` при наличии предзагруженных колёс.
- `scripts/release.sh` создаёт временный изолированный venv, устанавливает build/twine и автоматически добавляет свежий wheel в оффлайн-кэш, упрощая поддержку закрытых сегментов.
- CLI-подсказки и auto-bootstrap: `agentcall` сразу инициализирует капсулу, если нет запрета, и выводит сообщение "This directory is not an AgentControl project." для операторов.
- Docs bridge: `.agentcontrol/config/docs.bridge.yaml` настраивает целевые файлы, а `architecture-sync` заполняет managed-блоки в существующей документации (без дублирования `docs/`).
- `agentcall init` автоматически подхватывает уже существующий каталог `docs/` и прокладывает мост без перезаписи пользовательских файлов.

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
