# AGENTS.md — Project Control Surface (Linux)

```yaml
agents_doc: v1
updated_at: 2025-09-30T21:15:00Z
owners: [ "vibe-coder", "gpt-5-codex" ]
harness: { approvals: "never", sandbox: { fs: "danger-full-access", net: "enabled" } }
budgets: { p99_ms: 0, memory_mb: 0, bundle_kb: 0 }
stacks: { runtime: "bash@5", build: "make@4" }
teach: true
```
## Commands
- `make setup` — единоразовая установка системных инструментов, .venv, основных зависимостей, CLI Codex/Claude и Memory Heart индекса (можно пропустить через `SKIP_AGENT_INSTALL=1`/`SKIP_HEART_SYNC=1`).
- `make vendor-update` — обновление субмодулей (Memory Heart, Codex, Claude).
- `make agents-install` — пересобирает Codex (Rust из `vendor/codex`) и устанавливает Claude CLI в sandbox (`scripts/bin/`), при сбое откатывается к системному `claude`.
- `make agents auth` — интерактивная авторизация всех CLI, копирует учётные данные в `state/agents/<agent>` (или в `~/.local/state/agentcontrol/agents` при отсутствии прав) и обновляет `auth_status.json`. При наличии действующих токенов сообщает о пропуске и напоминает про `make agents auth-logout`.
- `make agents auth-logout` — удаляет сохранённые токены/конфиги, помечает статус `logged_out`.
- `make agents status` — быстрый health-check CLI/токенов/логов.
- `make agents logs [AGENT=...] [LAST=N]` — просмотреть свежие ответы без открытия файлов.
- `make agents workflow pipeline --task=<ID> [--workflow=<имя>]` — связка builder→reviewer.
- Прямые версии команд: `make agents-status`, `make agents-logs`, `make agents-workflow-pipeline` (избегают побочного запуска `make status`).
- `make heart-sync` — обновление индекса памяти; `make heart-query Q="..."`, `make heart-serve` для поиска/сервиса.
- `make init` — автоконфигурация (commands, roadmap, task board, state, reports/status.json).
- `make dev` — печать quickref и запуск команд разработки из config/commands.sh.
- `make verify` — базовые проверки + пользовательские `SDK_VERIFY_COMMANDS`; включает валидацию roadmap/task board, синхронизацию архитектуры и генерацию отчёта `reports/status.json`.
- `make review` — дифф-фокусированное ревью (`SDK_REVIEW_LINTERS`, `SDK_TEST_COMMAND`, diff-cover, quality_guard) с отчётом `reports/review.json`.
- `make doctor` — проверка окружения/зависимостей, сохраняет `reports/doctor.json`.
- `make fix` — авто-фиксы из `SDK_FIX_COMMANDS`.
- `make ship` — `make verify` + релизные команды `SDK_SHIP_COMMANDS`.
- Альтернатива Make — `python3 scripts/sdk.py {verify|review|doctor|status|summary|task|qa}`.
- `make lock` — пересборка `requirements.lock` с SHA256-хешами и обновление SBOM.
- `make status` — табличный дашборд (Roadmap + TaskBoard + Memory Heart), автоматически вызывает `make progress`.
- `make roadmap` — полный отчёт по фазам MVP→Q1…Q7 (с расчётом прогресса из task board).
- `make architecture-sync` — регенерация todo.machine.md, task board, архитектурного обзора и ADR/RFC из `architecture/manifest.yaml`.
- `make progress` — пересчёт прогресса программы/эпиков/Big Tasks и синхронизация todo.machine.md.
- `make agent-assign TASK=… [AGENT=codex] [ROLE=…]` — вызывает ИИ-агента, добавляет комментарий в задачу и сохраняет лог в `reports/agents`.
- `make agent-plan TASK=…` / `make agent-analysis` — получает план действий или обзор (использует Memory Heart и прогресс срезы).
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


### Agent Workflows
- Конфигурация описывается в `config/agents.json` (раздел `workflows`).
- Пример:

```jsonc
{
  "workflows": {
    "default": {
      "assign_agent": "codex",
      "assign_role": "Implementation Lead",
      "review_agent": "claude",
      "review_role": "Staff Reviewer"
    }
  }
}
```

`make agents workflow pipeline --task=T-123` последовательно вызовет назначение и ревью. Переопределяйте агентов на лету через `ASSIGN_AGENT`, `REVIEW_AGENT`, `ASSIGN_ROLE`, `REVIEW_ROLE`.

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
- Memory Heart поддерживается свежим (`make heart-sync`, шаг `heart-check` в `make verify`).

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
- Agent Auth State: `state/agents/auth_status.json`.
- Agent Binaries: `scripts/bin/` (генерируется `make agents-install`).
- Status Snapshot: `reports/status.json`, `reports/architecture-dashboard.json`.
- Roadmap sync: `scripts/sync-roadmap.sh` (автоматически вызывается `status`/`verify`).
- Architecture sync: `scripts/sync-architecture.sh` (автоматически вызывается `verify`/`agent-cycle`).
