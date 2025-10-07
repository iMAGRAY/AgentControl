# Контракт CLI: `agentcall docs lint --knowledge`

> Цель: контролировать полноту и актуальность обучающих материалов (tutorials/ADR/RFC), отлавливать битые ссылки и «осиротевшие» документы, формируя отчёт для CI и агентов.

## 1. Вызов команды
```
agentcall docs lint --knowledge [PATH] \
  [--json] \
  [--output reports/docs_coverage.json] \
  [--max-age-hours 168]
```

- `PATH` — корень проекта (по умолчанию текущая директория).
- `--json` — печатает отчёт в stdout (идентичен файлу отчёта).
- `--output` — путь сохранения отчёта (по умолчанию `reports/docs_coverage.json`).
- `--max-age-hours` — порог «устаревания» знаний. Файл, не обновлявшийся дольше порога, выдаёт ошибку `KNOWLEDGE_FILE_STALE`.

Коды выхода:

| Код | Значение |
| --- | --- |
| `0` | ошибок нет (возможны предупреждения). |
| `1` | найдены ошибки или достигнут порог устаревания. |
| `2` | фатальная ошибка (например, отсутствует `docs/tutorials/`). |

## 2. Проверки
- **Tutorials (`docs/tutorials/**/*.md`)**
  - H1-заголовок в первых 120 строках → иначе `KNOWLEDGE_MISSING_TITLE`.
  - Первый непустой абзац ≥ 80 символов → иначе `KNOWLEDGE_SHORT_SUMMARY`.
  - Внутренние ссылки (без `http(s)://`, `mailto:` и `#`) должны резолвиться → иначе `KNOWLEDGE_BROKEN_LINK`.
  - Внешние ссылки `http://` помечаются как предупреждение `KNOWLEDGE_INSECURE_LINK`.
  - Индекс (`docs/tutorials/index.md` или `README.md`) обязан ссылаться на каждый туториал → иначе `KNOWLEDGE_ORPHAN_TUTORIAL`.
- **ADR (`docs/adr/*.md`)** и **RFC (`docs/rfc/*.md`)**
  - H1-заголовок → иначе `KNOWLEDGE_ADR_MISSING_TITLE` / `KNOWLEDGE_RFC_MISSING_TITLE`.
  - Первый абзац ≥ 40 символов → предупреждение `KNOWLEDGE_ADR_SHORT_SUMMARY` / `KNOWLEDGE_RFC_SHORT_SUMMARY`.
  - Индекс обязан перечислять все записи → `KNOWLEDGE_ADR_ORPHAN`, `KNOWLEDGE_RFC_ORPHAN`.
- **Актуальность** — при указании `--max-age-hours` любой файл старше порога добавляет ошибку `KNOWLEDGE_FILE_STALE`.

## 3. Формат отчёта (`reports/docs_coverage.json`)
```json
{
  "generated_at": "2025-10-07T12:58:32Z",
  "project_root": "/abs/path",
  "tutorials": {
    "count": 5,
    "with_title": 5,
    "with_summary": 4,
    "checked_links": 28,
    "checked_external_links": 12,
    "insecure_links": 1,
    "latest_modified_at": "2025-10-07T11:54:11Z"
  },
  "index": {
    "path": "docs/tutorials/index.md",
    "listed": 4,
    "expected": 5
  },
  "collections": {
    "tutorials": {
      "count": 5,
      "with_title": 5,
      "with_summary": 4,
      "latest_modified_at": "2025-10-07T11:54:11Z",
      "index": {
        "path": "docs/tutorials/index.md",
        "listed": 4,
        "expected": 5
      }
    },
    "adr": {
      "count": 2,
      "with_title": 2,
      "with_summary": 2,
      "latest_modified_at": "2025-10-07T11:40:12Z",
      "index": {
        "path": "docs/adr/index.md",
        "listed": 1,
        "expected": 2
      }
    },
    "rfc": {
      "count": 0,
      "with_title": 0,
      "with_summary": 0,
      "latest_modified_at": null,
      "index": {
        "path": null,
        "listed": 0,
        "expected": 0
      }
    }
  },
  "issues": [
    {
      "code": "KNOWLEDGE_SHORT_SUMMARY",
      "path": "docs/tutorials/onboarding.md",
      "message": "First paragraph shorter than 80 characters",
      "severity": "warning"
    },
    {
      "code": "KNOWLEDGE_BROKEN_LINK",
      "path": "docs/tutorials/api.md",
      "message": "Broken link: ./missing_example.md",
      "severity": "error"
    },
    {
      "code": "KNOWLEDGE_ADR_ORPHAN",
      "path": "docs/adr/ADR-0002.md",
      "message": "Entry not referenced in docs/adr/index.md",
      "severity": "error"
    },
    {
      "code": "KNOWLEDGE_FILE_STALE",
      "path": "docs/tutorials/archive.md",
      "message": "Knowledge file stale (420.0h > 168h)",
      "severity": "error"
    }
  ],
  "status": "error",
  "report_path": "reports/docs_coverage.json"
}
```

- `status` — `ok`, `warning` или `error` (при наличии хотя бы одной ошибки).
- `issues[*].severity` — `error` блокирует команду, `warning` фиксируется в отчёте, но не влияет на код завершения.
- `report_path` — путь сохранённого отчёта (используется verify и телеметрией).

## 4. Коды диагностик
- Туториалы: `KNOWLEDGE_MISSING_TITLE`, `KNOWLEDGE_SHORT_SUMMARY`, `KNOWLEDGE_BROKEN_LINK`, `KNOWLEDGE_ORPHAN_TUTORIAL`, `KNOWLEDGE_INSECURE_LINK`.
- ADR: `KNOWLEDGE_ADR_MISSING_TITLE`, `KNOWLEDGE_ADR_SHORT_SUMMARY`, `KNOWLEDGE_ADR_ORPHAN`.
- RFC: `KNOWLEDGE_RFC_MISSING_TITLE`, `KNOWLEDGE_RFC_SHORT_SUMMARY`, `KNOWLEDGE_RFC_ORPHAN`.
- Актуальность: `KNOWLEDGE_FILE_STALE`.
- Каталоги: `KNOWLEDGE_ROOT_MISSING`.

## 5. Телеметрия
- `docs.lint.knowledge` — события `status=start|success|warning|error`, payload содержит путь отчёта и счётчики ошибок/предупреждений.

## 6. Интеграция с verify
- Verify вызывает `agentcall docs lint --knowledge --json`; при `status=error` пайплайн падает.
- Артефакт `reports/docs_coverage.json` коммитится вместе с остальными отчётами verify.
