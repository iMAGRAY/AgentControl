# AGENTS.md — Project Control Surface (Linux)

```yaml
agents_doc: v1
updated_at: 2025-09-29T00:00:00Z
owners: [ "vibe-coder", "gpt-5-codex" ]
harness: { approvals: "never", sandbox: { fs: "danger-full-access", net: "enabled" } }
budgets: { p99_ms: 0, memory_mb: 0, bundle_kb: 0 }
stacks: { runtime: "bash@5", build: "make@4" }
teach: true
```
## Commands
- `make init` — автоконфигурация (commands, roadmap, task board, state, reports/status.json).
- `make dev` — печать quickref и запуск команд разработки из config/commands.sh.
- `make verify` — базовые проверки + пользовательские `SDK_VERIFY_COMMANDS`; включает валидацию roadmap/task board и генерацию отчёта `reports/status.json`.
- `make fix` — авто-фиксы из `SDK_FIX_COMMANDS`.
- `make ship` — `make verify` + релизные команды `SDK_SHIP_COMMANDS`.
- `make status` — компактный дашборд (Roadmap + TaskBoard) и сохранение JSON статуса.
- `make roadmap` — полный отчёт по фазам MVP→Q1…Q7 (с расчётом прогресса из task board).
- `make task-add TITLE="..." [EPIC=...]` — добавить задачу без редактирования JSON (alias: `make task add`).
- `make task take [AGENT=...]` — взять ближайшую доступную задачу (alias grab).
- `make task drop TASK=<id>` — освободить задачу (alias release).
- `make task done TASK=<id> [AGENT=...]` — завершить задачу (alias complete).
- `make task status` — подробный список задач с критериями успеха/провала.
- `make task summary --json` — машинно-читаемая сводка для автоматизации.
- `make task conflicts` — карта конфликтов (alias работает и для `task-conflicts`).
- `make task comment TASK=<id> MESSAGE="..." [AUTHOR=...]` — журнал комментариев.
- `LIMIT=N [JSON=1] make task-history` — просмотр событий из `journal/task_events.jsonl` (alias: `make task history`).
- `make task validate` — строгая проверка доски.

## Plan
- Global: Program + Epics + Big Tasks в `todo.machine.md`.
- Micro: через Update Plan Tool (UPT), в репозиторий не добавляется.
- Task board: `data/tasks.board.json` + runtime `state/task_state.json` + `journal/task_events.jsonl`.
- AGENT по умолчанию: `gpt-5-codex` (можно переопределять при вызове команд).

## Quality Gates
- Структура SDK (AGENTS.md, todo.machine.md, .editorconfig, .codexignore).
- Shellcheck (если доступен).
- Пользовательские проверки из `config/commands.sh`.
- Roadmap консистентна (`make roadmap` / верификация внутри `make verify`).
- Task board консистентна (`make task validate`), события логируются.

## Rollback
- Flags/env toggles: `SDK_*_COMMANDS` в config/commands.sh.
- Emergency steps: вернуть файл config/commands.sh к шаблону и повторно `make verify`.
- Task board reset: восстановить `data/tasks.board.json`, очистить `state/task_selection.json`, архивировать `journal/task_events.jsonl`.

## Links
- ADRs: `docs/adr/` (создайте при необходимости).
- Journal: `docs/changes.md`.
- Scripts: `scripts/`, Hooks: настраиваются вручную.
- Roadmap: `todo.machine.md`.
- Task Board: `data/tasks.board.json`.
- Event Log: `journal/task_events.jsonl`.
- Status Snapshot: `reports/status.json`.
