# Workspace Summary

`workspace.yaml` описывает несколько проектов, с которыми работает агент. Команда `agentcall mission summary --workspace` агрегирует их состояние.

## 1. workspace.yaml
```yaml
version: 1
projects:
  - id: agentcontrol-sdk
    name: AgentControl SDK
    path: .
    tags: ["sdk", "core"]
```
- `path` может быть относительным или абсолютным.
- `tags` и `description` помогают фильтровать вывод.

## 2. Запуск агрегатора
```bash
agentcall mission summary --workspace --json
```
Результат содержит массив проектов и для каждого — прогресс программы (`program.progress_pct`), статус verify и путь.

## 3. Сохранение отчёта
```bash
agentcall mission summary --workspace --output reports/workspace_summary.json
```
Json-файл можно добавить в CI, чтобы следить за состоянием всех репозиториев.

## 4. Совет
Добавьте `workspace.yaml` в каждый мета-репозиторий верхнего уровня, чтобы агенты сразу знали, какие проекты надо учитывать.
