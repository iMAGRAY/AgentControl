# Контракт CLI: `agentcall docs portal`

> Цель: сгенерировать автономный статический портал знаний из управляемых документов AgentControl, включая индекс обучающих материалов и примеров с указанием происхождения.

## 1. Вызов команды
```
agentcall docs portal [PATH] \
  [--output reports/docs/portal] \
  [--force] \
  [--budget 1048576] \
  [--json]
```

- `PATH` — корень проекта (по умолчанию текущая директория).
- `--output` — каталог вывода. Значение по умолчанию: `reports/docs/portal`.
- `--force` — разрешает очистку целевого каталога перед генерацией (иначе команда завершится ошибкой, если каталог не пуст и не содержит ожидаемой структуры портала).
- `--budget` — максимальный суммарный размер артефактов портала в байтах (по умолчанию `1048576`, что соответствует 1 МиБ).
- `--json` — выводит итоговый отчёт в stdout в формате JSON (описан ниже).

Команда возвращает 0 при успешной генерации и 1 при ошибках (например, превышение бюджета, отсутствие манифеста, повреждённая конфигурация мостика документов).

## 2. Генерируемая структура
Каталог портала содержит:
```
index.html
assets/styles.css
assets/snarkdown.js
assets/app.js
```

- `index.html` — статическая страница с клиентским рендерингом Markdown и поиском.
- `assets/styles.css` — минимальный дизайн (адаптивная сетка, тёмная/светлая тема).
- `assets/snarkdown.js` — встроенный Markdown-парсер (MIT, без внешних зависимостей).
- `assets/app.js` — инициализация данных, отрисовка секций, полнотекстовый поиск по материалам.

Все данные портала встраиваются в `index.html` в виде JSON (объект `window.__AGENTCONTROL_DOCS_PORTAL__`). Дополнительных сетевых запросов для отображения не требуется.

## 3. Содержимое JSON-пакета
```json
{
  "generated_at": "2025-10-07T12:34:56Z",
  "project_root": "/abs/path/to/project",
  "docs_root": "docs",
  "sections": [
    {
      "id": "architecture_overview",
      "title": "Architecture Overview",
      "markdown": "# Architecture Overview\\n...",
      "source": "architecture/manifest.yaml"
    }
  ],
  "status": {
    "configPath": ".agentcontrol/config/docs.bridge.yaml",
    "rootExists": true,
    "sections": [
      {"name": "architecture_overview", "status": "match", "target": "docs/architecture/overview.md"}
    ]
  },
  "inventory": [
    {
      "kind": "tutorial",
      "title": "Mission Control Walkthrough",
      "path": "docs/tutorials/mission_control_walkthrough.md",
      "summary": "Как запустить панель миссии…",
      "tags": ["docs", "tutorial"],
      "modified_at": "2025-10-05T08:12:44Z"
    },
    {
      "kind": "example",
      "title": "Sample GitHub Automation",
      "path": "examples/github/README.md",
      "summary": "Пайплайн nightly perf guard…",
      "tags": ["examples", "automation"],
      "modified_at": "2025-10-02T17:03:11Z"
    }
  ]
}
```

- `sections` — Markdown-секции, полученные из архитектурного манифеста (`architecture/manifest.yaml` или `.agentcontrol/architecture/manifest.yaml`). Клиентский JS конвертирует их в HTML.
- `status` — сводка `DocsCommandService.list_sections`, включая путь до цели и текущий статус (`match`, `missing_file`, `missing_marker`, …).
- `inventory` — поисковый каталог. Для каждого элемента хранится тип (`tutorial`/`example`), заголовок, относительный путь, краткое описание (до 240 символов), набор тегов и время последней модификации (UTC ISO8601).

## 4. Поиск и доказуемость происхождения
- Полнотекстовый поиск выполняется по `title`, `summary`, `tags`.
- Каждый результат отображает относительный путь (provenance) и время модификации.
- Клик по результату открывает соответствующий раздел/файл (используя `path` как относительный URL внутри репозитория).

## 5. Ограничения и ошибки
- Размер каталога не должен превышать указанный бюджет (`--budget`). При превышении команда завершится с кодом 1 и сообщением об ошибке `DOCS_PORTAL_SIZE_BUDGET_EXCEEDED`.
- При отсутствии архитектурного манифеста команда завершится с кодом 1 (`DOCS_PORTAL_MANIFEST_MISSING`).
- Если конфигурация `docs.bridge.yaml` отсутствует или невалидна, используется дефолтная (root=`docs`). Ошибки валидации пробрасываются из `DocsBridgeService` и сохраняют исходные коды (`DOC_BRIDGE_*`).
- Каталог вывода должен быть пуст или соответствовать структуре портала; иначе без `--force` возвращается код 1 (`DOCS_PORTAL_OUTPUT_NOT_EMPTY`).

## 6. JSON-отчёт
При использовании `--json` команда печатает:
```json
{
  "status": "ok",
  "path": "reports/docs/portal",
  "files": 4,
  "size_bytes": 48211,
  "generated_at": "2025-10-07T12:34:56Z",
  "inventory": {"tutorials": 5, "examples": 3}
}
```

- `status` — `ok` или `error`.
- `inventory` — количество элементов по видам (при ошибке отсутствует).
- При ошибке объект содержит `error` с полями `code`, `message`, `remediation`.

## 7. Телеметрия
Генерация публикует события:

1. `docs.portal` — `status=start`, payload: `{"path": "<abs>", "output": "<abs>", "budget": 1048576}`.
2. `docs.portal` — `status=success|error`, payload дополняется `{"files": n, "size_bytes": m}` или `{"error_code": "...", "error": "..."}`.

События пишутся в `~/.agentcontrol/logs/telemetry.jsonl`.
