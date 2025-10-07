# Tutorial: Синхронизация task board с провайдером

`agentcall tasks sync` автоматизирует сравнение локального `data/tasks.board.json` с внешним источником задач и готовит план действий для миссий.

## 1. Подготовьте снимок провайдера
Сформируйте JSON с задачами (объект или массив). Минимальные поля — `id`, `title`, `status`; дополнительные данные сохраняются без изменений. Пример:
```json
{
  "tasks": [
    {"id": "TASK-1", "title": "Staging docs", "status": "in_progress", "priority": "P1"},
    {"id": "TASK-2", "title": "Nightly perf", "status": "open", "priority": "P0"}
  ]
}
```
Поместите снимок, например, в `state/provider/tasks_snapshot.json`.

## 2. Настройте конфигурацию
Создайте `config/tasks.provider.json`:
```json
{
  "type": "file",
  "options": {
    "path": "state/provider/tasks_snapshot.json"
  }
}
```

### Inline-параметры вместо файла
Если нужно выполнить разовый dry-run, можно обойтись без `config/tasks.provider.json` и задать настройки прямо в CLI:
```bash
agentcall tasks sync --provider file --input state/provider/tasks_snapshot.json --json
```
`--input` подставляет путь в `options.path`. Дополнительные параметры задаются через `--provider-option`, например `--provider-option snapshot_path=state/provider/jira.json` или `--provider-option auth.token_env=JIRA_API_TOKEN`.
Для удалённых провайдеров добавьте идентификаторы репозитория/фильтры:
```bash
agentcall tasks sync --provider jira   --provider-option snapshot_path=state/provider/jira.json   --provider-option base_url=https://example.atlassian.net   --provider-option jql="project = AC"
```

## 3. Просмотрите план (dry-run)
```bash
agentcall tasks sync --json
```
Команда выводит сводку (`create/update/close/unchanged`) и список действий. Файл `data/tasks.board.json` не изменяется, отчёт сохраняется в `reports/tasks_sync.json`.

## 4. Примените изменения
```bash
agentcall tasks sync --apply
```
- Новые задачи добавляются в конец списка.
- Изменённые поля обновляются точечно.
- Задачи без соответствий помечаются `status=done`, получают `completed_at` и переносятся в конец.
Обновлённый отчёт хранится в `reports/tasks_sync.json`.

## 5. Персонализация
- Используйте `--config /path/to/custom.json`, чтобы переключиться на другой провайдер.
- `--output /tmp/tasks_sync.json` переопределяет путь к отчёту.
- Для живой интеграции:
  - **Jira** — задайте в конфиге `type: "jira"`, укажите `base_url`, `jql`, а в окружении сохраните `JIRA_EMAIL` и `JIRA_API_TOKEN`.
  - **GitHub** — используйте `type: "github"`, параметры `owner`/`repo`, и выдайте токен через `GITHUB_TOKEN`.
  - Для оффлайн-тестов можно указать `snapshot_path`, чтобы читать подготовленный JSON без сетевых запросов.
  - Используйте `options.encryption` (для `file`) или `options.snapshot_encryption` (для `jira`/`github`) чтобы указать `mode` (`xor` или `aes-256-gcm`) и источник ключа (`key`/`key_env`).
  - Ключи никогда не попадают в отчёты: при сериализации остаются только `key_env` и маска `***`.
  - Бинарные снапшоты кодируются в base64. Для AES-GCM структура файла: `nonce(12 байт) + ciphertext + tag`, затем base64.
  - Для использования AES потребуется установить пакет `cryptography` в окружении, где запускается CLI.

## 6. Интеграция с миссией
`agentcall mission analytics` и панели миссии читают `reports/tasks_sync.json`, поэтому операции синхронизации сразу появляются в аналитике.

## 7. Отладка и проверки
- Ошибки конфигурации (`tasks.sync.config_not_found`, `tasks.sync.provider_not_supported`) печатаются в stderr.
- `scripts/test-place.sh` выполняет dry-run внутри изолированного проекта, проверяя, что синхронизация не ломает шаблон.
