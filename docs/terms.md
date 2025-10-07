# Глоссарий AgentControl

- **Mission Dashboard Web API** — статeless HTTP-сервер (`agentcall mission dashboard --serve`), отдающий HTML/SSE и REST-триггеры для плейбуков; все вызовы логируются в `mission-actions.json` и телеметрию `mission.dashboard.api`.
- **Mission OperationId** — детерминированный идентификатор ответа веб-API, привязанный к записи в `mission-actions.json`; используется для аудита и сопоставления событий между журналами и телеметрией.
- **Mission Watch Status** — последнее состояние (success/error/warning/skipped и т. д.), зафиксированное в `.agentcontrol/state/watch.json` для правила; управляет сбросом попыток и повторными запусками плейбуков.
- **Agentcall Help Overview** — контекстная справка `agentcall help`, которая агрегирует статус verify, watch-конфигурацию, SLA и рекомендуемые команды (поддерживает `--json`).
- **Task Sync Plan** — результат `agentcall tasks sync`: список операций (`create/update/close`) и сводка (`summary`) в `reports/tasks/sync.json`, пригодная для аналитики миссии.
- **Task Provider Snapshot** — JSON-снимок задач внешней системы (например, `state/provider/tasks_snapshot.json`), который адаптеры поставляют в доменную модель перед расчётом плана синхронизации.
