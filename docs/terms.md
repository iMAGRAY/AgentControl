# Глоссарий AgentControl

- **Mission Dashboard Web API** — статeless HTTP-сервер (`agentcall mission dashboard --serve`), отдающий HTML/SSE и REST-триггеры для плейбуков; все вызовы логируются в `mission-actions.json` и телеметрию `mission.dashboard.api`.
- **Mission OperationId** — детерминированный идентификатор ответа веб-API, привязанный к записи в `mission-actions.json`; используется для аудита и сопоставления событий между журналами и телеметрией.
- **Mission Watch Status** — последнее состояние (success/error/warning/skipped и т. д.), зафиксированное в `.agentcontrol/state/watch.json` для правила; управляет сбросом попыток и повторными запусками плейбуков.
- **Agentcall Help Overview** — контекстная справка `agentcall help`, которая агрегирует статус verify, watch-конфигурацию, SLA и рекомендуемые команды (поддерживает `--json`).
- **Task Sync Plan** — результат `agentcall tasks sync`: список операций (`create/update/close`) и сводка (`summary`) в `reports/tasks/sync.json`, пригодная для аналитики миссии.
- **Task Provider Snapshot** — JSON-снимок задач внешней системы (например, `state/provider/tasks_snapshot.json`), который адаптеры поставляют в доменную модель перед расчётом плана синхронизации.
- **Encrypted Snapshot** — base64-представление XOR-зашифрованного снимка; ключ передаётся через `options.encryption` (не хранится в отчётах).
- **Docs Portal** — статический портал знаний, генерируемый `agentcall docs portal`; агрегирует управляемые разделы, статус моста и поисковый каталог с обеспечением происхождения материалов.
- **Knowledge Inventory** — поисковый индекс портала, объединяющий обучающие материалы и примеры; содержит заголовок, краткое описание, теги и относительный путь для верификации источника.
- **Docs Coverage Report** — JSON-отчёт (`reports/docs_coverage.json`) с результатами `agentcall docs lint --knowledge`: метрики по туториалам и список нарушений (ошибки/предупреждения) для verify/CI.
- **Extension Manifest Schema** — JSON-схема `extension_manifest.schema.json`, по которой `agentcall extension lint` валидирует структуру и совместимость расширений (в т.ч. версии и точки входа).
