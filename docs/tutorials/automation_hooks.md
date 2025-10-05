# Tutorial: Automation Hooks with `SDK_VERIFY_COMMANDS`

AgentControl позволяет расширять `agentcall verify` и другие пайплайны, не правя системные скрипты. Все, что требуется, — задать переменную окружения `SDK_VERIFY_COMMANDS` со списком команд.

## Быстрый старт
1. Создайте скрипт, который выполняет нужный шаг, например, локальный линтер:
   ```bash
   cat > scripts/custom/lint.sh <<'SH'
   #!/usr/bin/env bash
   set -Eeuo pipefail
   poetry run ruff check .
   SH
   chmod +x scripts/custom/lint.sh
   ```
2. Вызовите verify с `SDK_VERIFY_COMMANDS`:
   ```bash
   SDK_VERIFY_COMMANDS=("scripts/custom/lint.sh") agentcall verify
   ```
   Каждая команда выполняется в конце пайплайна и попадает в отчёт `reports/verify.json`.

## JSON-ориентированный режим
Все команды исполняются в контексте проекта. Если требуется JSON-выход для агентов, используйте `--json` или сериализацию самостоятельно — verify сохраняет хвост логов и статус.

## Составные пайплайны
Можно передать несколько команд:
```bash
SDK_VERIFY_COMMANDS=(
  "agentcall docs sync --json"
  "pytest --maxfail=1 --disable-warnings"
) agentcall verify --json
```
Команды выполняются последовательно; при отказе результат фиксируется со статусом `fail`, но основной verify продолжит работу (если не задан `EXIT_ON_FAIL=1`).

## Автоматизация через CI
В CI достаточно экспортировать переменную в шаге запуска verify:
```yaml
env:
  SDK_VERIFY_COMMANDS: |
    agentcall docs sync --json
    pytest --maxfail=1
run: agentcall verify --json
```
Используйте `SDK_VERIFY_COMMANDS+=(...)` в shell-скриптах, если необходимо дополнять список из разных модулей.

> **Совет:** храните набор команд в `.agentcontrol/config/automation.sh` и source-ите файл в CI, чтобы агенты могли автоматически монтировать общие сценарии.
