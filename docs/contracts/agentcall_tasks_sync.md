# Контракт CLI: `agentcall tasks sync`

> Цель: синхронизировать локальный борт `data/tasks.board.json` с внешним провайдером задач. Команда фиксирует план действий (create/update/close) и публикует структурированный отчёт для миссии и аналитики.

## 1. Вызов команды
```
agentcall tasks sync [PATH] \
  [--config config/tasks.provider.json | --provider TYPE] \
  [--input PATH] \
  [--provider-option KEY=VALUE] \
  [--output reports/tasks_sync.json] \
  [--apply] \
  [--json]
```

- `PATH` — корень проекта (по умолчанию текущая директория).
- `--config` — путь к конфигурации провайдера (по умолчанию `config/tasks.provider.json`). Взаимоисключает `--provider`.
- `--provider` — inline-режим без файла: укажите тип (`file`, `jira`, `github`), а опции передайте через `--input`/`--provider-option`.
- `--input` — короткая запись основного источника данных (`file` → `options.path`, удалённые провайдеры → `options.snapshot_path`).
- `--provider-option` — доп. опции в виде `ключ=значение`; поддерживает точечную нотацию (`auth.email_env=JIRA_EMAIL`). Флаг можно повторять.
- `--output` — путь для сохранения отчёта. Значение по умолчанию: `reports/tasks_sync.json`.
- `--apply` — разрешает применение изменений к `data/tasks.board.json`. Без флага выполняется dry-run.
- `--json` — печатает результат в stdout в формате JSON.

Пример inline-вызова без отдельного JSON-файла:
```bash
agentcall tasks sync --provider file --input state/provider/tasks_snapshot.json --json
```
Дополнительные параметры можно задать повторяющимся `--provider-option`, например `--provider-option auth.token_env=JIRA_API_TOKEN`.
Пример для Jira с локальным снапшотом и шифрованием:
```bash
agentcall tasks sync --provider jira \
  --provider-option snapshot_path=state/provider/jira_issues.enc \
  --provider-option snapshot_encryption.mode=aes-256-gcm \
  --provider-option snapshot_encryption.key_env=TASKS_AES_KEY \
  --json
```


Команда возвращает 0 при успешном расчёте/применении и 1 при ошибках конфигурации или чтения данных.

## 2. Конфигурация провайдера

### `file`
```json
{
  "type": "file",
  "options": {
    "path": "state/provider/tasks_snapshot.json"
  }
}
```
- `type` — идентификатор адаптера (`file`, `jira`, `github`).
- `options.path` — путь к снимку задач (относительно корня проекта или абсолютный).

### `jira`
```json
{
  "type": "jira",
  "options": {
    "base_url": "https://example.atlassian.net",
    "jql": "project = AC AND statusCategory != Done",
    "auth": {
      "email_env": "JIRA_EMAIL",
      "token_env": "JIRA_API_TOKEN"
    },
    "fields": ["summary", "status", "priority", "assignee"],
    "snapshot_path": "state/provider/jira_issues.json"
  }
}
```
- При наличии `snapshot_path` данные читаются из подготовленного JSON, иначе выполняются запросы `rest/api/3/search` с пагинацией.
- Авторизация происходит по email/API token, извлекаемым из окружения `JIRA_EMAIL` и `JIRA_API_TOKEN`.
- Для зашифрованных снапшотов задайте `"snapshot_encrypted": true` и ключ через `snapshot_key_env`.

### `github`
```json
{
  "type": "github",
  "options": {
    "owner": "agentcontrol",
    "repo": "sdk",
    "state": "all",
    "token_env": "GITHUB_TOKEN",
    "snapshot_path": "state/provider/github_issues.json"
  }
}
```
- Без `snapshot_path` провайдер обращается к `GET /repos/{owner}/{repo}/issues` с токеном из `GITHUB_TOKEN` и обрабатывает пагинацию по заголовку `Link`.
- Для `file` используйте `options.encryption`, для `jira/github` — `options.snapshot_encryption`.
- Значения `key` никогда не попадают в отчёты: в JSON остаются `key_env` и маска `***`.

#### Шифрование снимков
```json
{
  "snapshot_path": "state/provider/tasks_snapshot.enc",
  "snapshot_encryption": {
    "mode": "aes-256-gcm",
    "key_env": "TASKSYNC_KEY"
  }
}
```
- Поддерживаются режимы `xor` (base64 XOR) и `aes-256-gcm` (nonce+ciphertext+tag в base64).
- Ключ можно задать напрямую через `key` или передать в окружении через `key_env`; в отчётах значение маскируется.
- Для AES ключ должен быть длиной 16/24/32 байта; снапшот содержит 12-байтовый nonce и зашифрованные данные в base64.
- Для режима AES требуется пакет `cryptography` в окружении CLI.

## 3. Структура отчёта
```json
{
  "generated_at": "2025-10-07T14:15:22Z",
  "project_root": "/abs/path/to/project",
  "board_path": "data/tasks.board.json",
  "provider": {
    "type": "file",
    "options": {"path": "state/provider/tasks_snapshot.json"}
  },
  "applied": false,
  "summary": {
    "total": 3,
    "create": 1,
    "update": 1,
    "close": 1,
    "unchanged": 0
  },
  "actions": [
    {
      "op": "create",
      "task": {
        "id": "OPS-010",
        "title": "Provision SLA webhooks",
        "status": "open"
      }
    },
    {
      "op": "update",
      "task_id": "P7-002",
      "changes": {
        "status": {"from": "in_progress", "to": "done"}
      }
    },
    {
      "op": "close",
      "task_id": "ARCH-003",
      "reason": "provider_removed"
    }
  ]
}
```
- Поле `applied` показывает, были ли изменения внесены в борт.
- При применения файл отчёта дополняется `report_path` и `board_path` (относительно корня проекта).

## 4. Дифф и приоритет полей
- Обязательные поля задачи: `id`, `title`, `status`.
- Дополнительные поля (`priority`, `owner`, `epic`, `metrics`, `comments`) обновляются, если присутствуют у провайдера.
- Поля, отсутствующие у провайдера, остаются без изменений в локальном борде.

## 5. Поведение применения (`--apply`)
- `create` — добавляет задачу в конец массива `tasks`.
- `update` — изменяет только поля из `changes` (значение `to`).
- `close` — выставляет `status="done"`, добавляет `completed_at` в формате ISO8601 UTC и переносит задачу в конец списка.
- После применения файл `data/tasks.board.json` перезаписывается канонически (`indent=2`, `ensure_ascii=False`).

## 6. Ошибки
- `tasks.sync.config_not_found` — не найден файл конфигурации провайдера.
- `tasks.sync.config_invalid` — конфигурация некорректна (тип, формат опций, невалидный JSON).
- `tasks.sync.provider_not_supported` — `type` провайдера не поддерживается.
- `tasks.sync.board_invalid` — локальный борт отсутствует или повреждён.
- `tasks.sync.input_invalid` — провайдер вернул некорректные данные (без `id` и т. п.).

Ошибки печатаются в stderr, команда завершает работу с кодом 1.
