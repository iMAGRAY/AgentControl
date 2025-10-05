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
