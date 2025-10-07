# Mission Assign

`agentcall mission assign` распределяет задачи между агентами по квотам.

## 1. Конфигурация (`config/mission_assign.yaml`)
```yaml
agents:
  - id: alpha
    name: Alpha Agent
    max_active: 3
    tags: ["core"]
```
- `max_active` — лимит одновременно назначенных задач.
- Дополнительные теги помогают фильтровать агентов в аналитике.

## 2. Назначение задачи
```bash
agentcall mission assign --task T1 --agent alpha --json
```
Вывод содержит запись с отметкой времени и контрольной суммой борда.

## 3. Обновление статуса
```bash
agentcall mission assign --task T1 --agent alpha --status done
```
Статус меняется в `.agentcontrol/state/assignments.json`.

## 4. Просмотр очереди
```bash
agentcall mission assign --list --json
```
Отдаёт массив текущих назначений.

## 5. Optimistic Lock
Если `data/tasks.board.json` изменился со времени последнего назначения, команда вернёт ошибку — перезапустите после обновления борда.
