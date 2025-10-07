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

## 2. Просмотрите план (dry-run)
```bash
agentcall tasks sync --provider file --input provider/tasks.json --dry-run --json
```
Ответ содержит список операций (`create/update/close`). Файл `data/tasks.board.json` не изменяется.

## 3. Примените изменения
```bash
agentcall tasks sync --provider file --input provider/tasks.json
```
- Новые задачи добавляются в локальный board.
- Изменённые поля обновляются точечно.
- Задачи, отсутствующие в провайдере, помечаются `status=done`.
Отчёт записывается в `reports/tasks/sync.json` и пригоден для аналитики.

## 4. Интеграция с миссией
`agentcall mission analytics` отображает количество операций и агрегирует данные из `reports/tasks/sync.json`.

## 5. Отладка и проверки
- Любые ошибки провайдера (неизвестный тип, отсутствующий файл) приводят к коду возврата 1 и пояснению в stderr.
- Убедитесь, что `scripts/verify.sh` и `scripts/test-place.sh` выполняются — синхронизация включена в sandbox-проверки.
