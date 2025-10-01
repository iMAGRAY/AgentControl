## Program
```yaml
program: v1
program_id: codex-sdk
name: GPT-5 Codex SDK Toolkit
objectives:
- Централизовать архитектурные решения и дорожные карты в одном источнике правды.
- Автоматизировать выпуск документации, ADR/RFC и доски задач из архитектурного конфига.
- Обеспечить воспроизводимость агентного цикла принятия решений и доставки.
kpis:
  uptime_pct: 99.9
  tti_ms: 1200
  error_rate_pct: 0.1
owners:
- vibe-coder
- gpt-5-codex
policies:
  task_min_points: 5
teach: true
updated_at: '2025-10-01T04:31:15Z'
health: green
progress_pct: 100
phase_progress:
  MVP: 100
  Q1: 100
  Q2: 100
  Q3: 100
  Q4: 100
  Q5: 100
  Q6: 100
  Q7: 100
milestones:
- id: m_mvp
  title: Phase 0 – Feasibility
  due: '2025-10-15T00:00:00Z'
  status: done
- id: m_q1
  title: Phase 1 – Foundation
  due: '2025-12-31T00:00:00Z'
  status: done
- id: m_q2
  title: Phase 2 – Core Build
  due: '2026-03-31T00:00:00Z'
  status: done
- id: m_q3
  title: Phase 3 – Beta
  due: '2026-06-30T00:00:00Z'
  status: done
- id: m_q4
  title: Phase 4 – GA
  due: '2026-09-30T00:00:00Z'
  status: done
- id: m_q5
  title: Phase 5 – Ops & Scaling
  due: '2026-12-31T00:00:00Z'
  status: done
- id: m_q6
  title: Phase 6 – Optimization
  due: '2027-03-31T00:00:00Z'
  status: done
- id: m_q7
  title: Phase 7 – Sustain & Innovate
  due: '2027-06-30T00:00:00Z'
  status: done
```

## Epics
```yaml
- id: sdk-foundation
  title: SDK Foundation
  type: epic
  status: done
  priority: P0
  size_points: 20
  scope_paths:
  - scripts/**
  - config/**
  - AGENTS.md
  - todo.machine.md
  - architecture/**
  spec: 'Intent: предоставить железобетонный каркас управления архитектурой и документами.

    Given: чистый репозиторий с SDK.

    When: агент запускает make init/dev/verify/ship.

    Then: все артефакты генерируются из manifest.yaml и остаются консистентными.

    '
  budgets:
    latency_ms: 0
    memory_mb: 0
    bundle_kb: 0
  risks:
  - Недостаточное покрытие manifest.yaml приведёт к ручной работе.
  - Нарушение целостности данных при одновременных правках.
  dependencies: []
  docs_updates:
  - README.md
  - AGENTS.md
  - docs/architecture/overview.md
  artifacts:
  - scripts/
  - architecture/
  big_tasks_planned:
  - bigtask-arch-sync
  - bigtask-doc-ops
  - bigtask-test-pytest
  - bigtask-doctor-ux
  progress_pct: 100
  health: green
  tests_required:
  - make verify
  verify_commands:
  - make architecture-sync
  audit:
    created_at: '2025-09-29T18:00:00Z'
    created_by: gpt-5-codex
    updated_at: '2025-09-30T13:20:00Z'
    updated_by: gpt-5-codex
```

## Big Tasks
```yaml
- id: bigtask-arch-sync
  title: Централизация архитектуры
  type: feature
  status: done
  priority: P0
  size_points: 13
  parent_epic: sdk-foundation
  scope_paths:
  - architecture/**
  - scripts/sync-architecture.sh
  - scripts/lib/architecture_tool.py
  spec: 'Given: manifest.yaml описывает систему.

    When: запускается make architecture-sync.

    Then: документация, todo.machine.md и task board синхронизируются автоматически.

    '
  budgets:
    latency_ms: 0
    memory_mb: 0
    bundle_kb: 0
  risks:
  - Ошибочная схема проявится во всех артефактах.
  dependencies: []
  progress_pct: 100
  health: green
  acceptance:
  - Все производные документы зависят только от manifest.yaml.
  - Проверки make verify падают при несогласованности.
  tests_required:
  - make architecture-sync
  verify_commands:
  - make architecture-sync
  docs_updates:
  - docs/architecture/overview.md
  - docs/adr/index.md
  artifacts:
  - scripts/lib/architecture_tool.py
  audit:
    created_at: '2025-09-29T18:00:00Z'
    created_by: gpt-5-codex
    updated_at: '2025-09-30T13:20:00Z'
    updated_by: gpt-5-codex
- id: bigtask-doc-ops
  title: Документационный конвейер
  type: feature
  status: done
  priority: P1
  size_points: 8
  parent_epic: sdk-foundation
  scope_paths:
  - docs/**
  - templates/**
  spec: 'Given: manifest.yaml изменён.

    When: выполняется make architecture-sync.

    Then: центральный документ, ADR и RFC пересобраны детерминированно.

    '
  budgets:
    latency_ms: 0
    memory_mb: 0
    bundle_kb: 0
  risks:
  - Шаблоны могут устареть без тестов.
  dependencies:
  - bigtask-arch-sync
  progress_pct: 100
  health: green
  acceptance:
  - Генерация идемпотентна и полно покрывает архитектуру.
  tests_required:
  - make architecture-sync
  verify_commands:
  - make architecture-sync
  docs_updates:
  - docs/architecture/overview.md
  - docs/adr/index.md
  - docs/rfc/index.md
  artifacts:
  - templates/
  audit:
    created_at: '2025-09-29T18:00:00Z'
    created_by: gpt-5-codex
    updated_at: '2025-09-30T13:20:00Z'
    updated_by: gpt-5-codex
- id: bigtask-test-pytest
  title: Pytest в verify
  type: test
  status: done
  priority: P0
  size_points: 5
  parent_epic: sdk-foundation
  scope_paths:
  - config/commands.sh
  - requirements.txt
  - README.md
  - scripts/verify.sh
  spec: 'Intent: формализовать прогон pytest в CI.

    Given: чистый репозиторий.

    When: запускается make verify или make ship.

    Then: pytest выполняется через .venv и падает при ошибках тестов.'
  budgets:
    latency_ms: 0
    memory_mb: 0
    bundle_kb: 0
  risks:
  - Сбой установки зависимостей блокирует verify.
  dependencies: []
  progress_pct: 100
  health: green
  acceptance:
  - make verify создаёт .venv и запускает pytest -q.
  - README описывает шаги для локального прогона тестов.
  tests_required:
  - make verify
  verify_commands:
  - make verify
  docs_updates:
  - README.md
  artifacts:
  - config/commands.sh
  - requirements.txt
  audit:
    created_at: '2025-09-30T05:20:00Z'
    created_by: gpt-5-codex
    updated_at: '2025-09-30T06:05:00Z'
    updated_by: gpt-5-codex
- id: bigtask-doctor-ux
  title: Улучшенный вывод make doctor
  type: ops
  status: done
  priority: P1
  size_points: 5
  parent_epic: sdk-foundation
  scope_paths:
  - scripts/doctor.sh
  - scripts/lib/deps_checker.py
  spec: 'Intent: сделать make doctor читаемым.

    Given: оператор запускает make doctor.

    When: формируется вывод проверки окружения.

    Then: результаты отображаются таблицей с командами и ссылками.'
  budgets:
    latency_ms: 0
    memory_mb: 0
    bundle_kb: 0
  risks:
  - Ссылки могут устареть без ревизии.
  dependencies:
  - bigtask-arch-sync
  progress_pct: 100
  health: green
  acceptance:
  - make doctor печатает таблицу со статусами, деталями и ссылками.
  - reports/doctor.json остаётся совместимым.
  tests_required:
  - make doctor
  verify_commands:
  - make doctor || true
  docs_updates: []
  artifacts:
  - scripts/doctor.sh
  - scripts/lib/deps_checker.py
  audit:
    created_at: '2025-09-30T05:20:00Z'
    created_by: gpt-5-codex
    updated_at: '2025-09-30T06:05:00Z'
    updated_by: gpt-5-codex
```
