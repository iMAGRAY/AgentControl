# AgentControl — Operations Charter (Linux)

```yaml
agents_doc: v1
updated_at: 2025-10-04T09:50:00Z
owners: [ "vibe-coder", "agentcontrol-core" ]
harness: { approvals: "never", sandbox: { fs: "danger-full-access", net: "enabled" } }
budgets: { p99_ms: 0, memory_mb: 0, bundle_kb: 0 }
stacks: { runtime: "bash@5", build: "agentcall@0.3" }
teach: true
```

## 1. Command Surface (для агентов и инженеров)
- `agentcall status [PATH]` — дашборд и автоинициализация капсулы (`AGENTCONTROL_DEFAULT_TEMPLATE/CHANNEL`, `AGENTCONTROL_NO_AUTO_INIT`).
- `agentcall init|upgrade [PATH]` — управление шаблонами и миграциями.
- `agentcall verify` — стандарт качества (fmt/tests/security/docs/SBOM/Heart).
- `agentcall fix` / `agentcall review` / `agentcall ship` — коррекция, код-ревью и релизный гейт.
- `agentcall agents <install|auth|status|logs|workflow>` — управление CLI агентов.
- `agentcall heart <sync|query|serve>` — Memory Heart.
- `agentcall templates` — перечень пакетов шаблонов.
- `agentcall telemetry <report|tail|clear>` — телеметрия.
- `agentcall plugins <list|install|remove|info>` — расширения через entry points.
- Скрипт `scripts/install_agentcontrol.sh` — первичное размещение шаблонов.

## 2. Управление рабочим процессом
- **Workflow registry:** `config/agents.json`, override через `ASSIGN_AGENT`, `REVIEW_AGENT` и т.д.
- **Логи:** `reports/agents/<timestamp>.log` + метаданные.
- **Микрозадачи:** ведутся только через Update Plan Tool; перед `agentcall ship` очередь должна быть пустой.
- **Task board:** `data/tasks.board.json`, `journal/task_events.jsonl`, `state/task_state.json`.

## 3. Контроль качества
- Обязательные артефакты: `AGENTS.md`, `architecture/manifest.yaml`, `todo.machine.md`, `.editorconfig`, `.codexignore`.
- Проверки: `agentcall verify` (shellcheck, quality_guard, sbom, lock, heart_check).
- Отчёты: `reports/verify.json`, `reports/review.json`, `reports/status.json`, `reports/doctor.json`.
- Release gate: `agentcall ship` прерывается на любых красных шагах или открытых micro tasks.

## 4. Восстановление
- Настройка пайплайнов: переменные `SDK_*_COMMANDS` в `config/commands.sh`.
- Срочный откат: восстановить `config/commands.sh` из шаблона, выполнить `agentcall verify`.
- Очистка task board: восстановить `data/tasks.board.json`, обнулить `state/task_selection.json`, архивировать `journal/task_events.jsonl`.
- Агентские токены: удалить `state/agents/` или `agentcall agents logout`.

## 5. Справочные материалы
- Архитектура: `architecture/manifest.yaml`, `docs/architecture/overview.md`.
- Управление изменениями: `docs/changes.md`, `docs/adr/`, `docs/rfc/`.
- Скрипты: `scripts/` (включая `scripts/agents/*.sh`, `scripts/lib/*.py`).
- Снапшоты статуса: `reports/status.json`, `reports/architecture-dashboard.json`.
- Авторизация агентов: `state/agents/auth_status.json`.

## 6. Контакты и эскалация
- Владелец: команда AgentControl Core (см. `owners` в YAML блоке).
- Эскалация: `agentcall agents workflow --task=<ID>` с указанием SLA; при критических инцидентах — прямой контакт владельца.
