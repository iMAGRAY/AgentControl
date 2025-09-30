# AGENTS.md — Project Control Surface (Linux)

```yaml
agents_doc: v1
updated_at: 2025-09-30T06:05:00Z
owners: [ "vibe-coder", "gpt-5-codex" ]
harness: { approvals: "never", sandbox: { fs: "danger-full-access", net: "enabled" } }
budgets: { p99_ms: 0, memory_mb: 0, bundle_kb: 0 }
stacks: { runtime: "bash@5", build: "make@4" }
teach: true
```
## Commands
- `make setup` — единоразовая установка системных инструментов, .venv и CLI зависимостей.
- `make init` — автоконфигурация (commands, roadmap, task board, state, reports/status.json).
- `make dev` — печать quickref и запуск команд разработки из config/commands.sh.
- `make verify` — базовые проверки + пользовательские `SDK_VERIFY_COMMANDS`; включает валидацию roadmap/task board, синхронизацию архитектуры и генерацию отчёта `reports/status.json`.
- `make review` — дифф-фокусированное ревью (`SDK_REVIEW_LINTERS`, `SDK_TEST_COMMAND`, diff-cover, quality_guard) с отчётом `reports/review.json`.
- `make doctor` — проверка окружения/зависимостей, сохраняет `reports/doctor.json`.
- `make fix` — авто-фиксы из `SDK_FIX_COMMANDS`.
- `make ship` — `make verify` + релизные команды `SDK_SHIP_COMMANDS`.
- Альтернатива Make — `python3 scripts/sdk.py {verify|review|doctor|status|summary|task|qa}`.
- `make status` — компактный дашборд (Roadmap + TaskBoard) и сохранение JSON статуса.
- `make roadmap` — полный отчёт по фазам MVP→Q1…Q7 (с расчётом прогресса из task board).
- `make architecture-sync` — регенерация todo.machine.md, task board, архитектурного обзора и ADR/RFC из `architecture/manifest.yaml`.
- `make progress` — пересчёт прогресса программы/эпиков/Big Tasks и синхронизация todo.machine.md.
- `make arch-edit` / `make arch-apply` — подготовка и безопасное применение изменений в `architecture/manifest.yaml`.
- `make agent-cycle` — полный Hybrid-H цикл: sync → проверки → отчёт `reports/agent_runs/<ts>.yaml`.
- `make task-add TITLE="..." [EPIC=...] [BIG_TASK=...]` — добавить задачу без редактирования JSON (alias: `make task add`).
- `make task take [AGENT=...]` — взять ближайшую доступную задачу (alias grab).
- `make task drop TASK=<id>` — освободить задачу (alias release).
- `make task done TASK=<id> [AGENT=...]` — завершить задачу (alias complete).
- `make task status` — подробный список задач с критериями успеха/провала.
- `make task summary --json` — машинно-читаемая сводка для автоматизации.
- `make task conflicts` — карта конфликтов (alias работает и для `task-conflicts`).
- `make task metrics` — метрики загрузки (WIP по агентам, throughput, незахваченные ready).
- `make task comment TASK=<id> MESSAGE="..." [AUTHOR=...]` — журнал комментариев.
- `LIMIT=N [JSON=1] make task-history` — просмотр событий из `journal/task_events.jsonl` (alias: `make task history`).
- `make task validate` — строгая проверка доски.

## Plan
- Global: Program + Epics + Big Tasks в `todo.machine.md` (обновляется автоматически).
- Micro: через Update Plan Tool (UPT), в репозиторий не добавляется.
- Task board: `data/tasks.board.json` + runtime `state/task_state.json` + `journal/task_events.jsonl`.
- AGENT по умолчанию: `gpt-5-codex` (можно переопределять при вызове команд).

## Quality Gates
- Структура SDK (AGENTS.md, todo.machine.md, .editorconfig, .codexignore).
- Shellcheck (если доступен).
- Пользовательские проверки из `config/commands.sh`.
- Quality guard (заглушки/секреты) возвращает предупреждения, строгий режим — `EXIT_ON_FAIL=1`.
- Отчёты: `reports/verify.json`, `reports/review.json`, `reports/status.json`.
- Если в `config/commands.sh` остались плейсхолдеры (`echo 'configure …'`), SDK подбирает безопасные команды для найденных стеков (npm/Yarn/pnpm, Poetry/Pipenv, Go, Cargo, Gradle/Maven, .NET и др.) автоматически.
- Если в `config/commands.sh` остались плейсхолдеры (`echo 'configure …'`), SDK подбирает команды для найденных стеков (npm/Yarn/pnpm, Poetry/Pipenv, Go, Cargo, Gradle/Maven, .NET и т.д.) автоматически.
- `make ship` блокирует релиз при `exit_code != 0`, упавших шагах или findings в quality guard.
- Roadmap консистентна (`make roadmap` / верификация внутри `make verify`).
- Task board консистентна (`make task validate`), события логируются.

## Rollback
- Flags/env toggles: `SDK_*_COMMANDS` в config/commands.sh.
- Emergency steps: вернуть файл config/commands.sh к шаблону и повторно `make verify`.
- Task board reset: восстановить `data/tasks.board.json`, очистить `state/task_selection.json`, архивировать `journal/task_events.jsonl`.

## Links
- ADRs: `docs/adr/` (генерируются из `architecture/manifest.yaml`).
- Journal: `docs/changes.md`.
- Scripts: `scripts/`, Hooks: настраиваются вручную.
- Roadmap: `todo.machine.md` (генерируется).
- Task Board: `data/tasks.board.json` (генерируется).
- Event Log: `journal/task_events.jsonl`.
- Status Snapshot: `reports/status.json`, `reports/architecture-dashboard.json`.
- Roadmap sync: `scripts/sync-roadmap.sh` (автоматически вызывается `status`/`verify`).
- Architecture sync: `scripts/sync-architecture.sh` (автоматически вызывается `verify`/`agent-cycle`).
