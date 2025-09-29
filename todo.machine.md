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
updated_at: '2025-09-29T18:00:00Z'
health: green
phase_progress:
  MVP: 19
  Q1: 19
  Q2: 19
  Q3: 19
  Q4: 19
  Q5: 19
  Q6: 19
  Q7: 19
progress_pct: 19
milestones:
- id: m_mvp
  title: MVP
  due: '2025-10-15T00:00:00Z'
  status: done
- id: m_q1
  title: Q1
  due: '2025-12-31T00:00:00Z'
  status: in_progress
- id: m_q2
  title: Q2
  due: '2026-03-31T00:00:00Z'
  status: planned
- id: m_q3
  title: Q3
  due: '2026-06-30T00:00:00Z'
  status: planned
- id: m_q4
  title: Q4
  due: '2026-09-30T00:00:00Z'
  status: planned
- id: m_q5
  title: Q5
  due: '2026-12-31T00:00:00Z'
  status: planned
- id: m_q6
  title: Q6
  due: '2027-03-31T00:00:00Z'
  status: planned
- id: m_q7
  title: Q7
  due: '2027-06-30T00:00:00Z'
  status: planned
```

## Epics
```yaml
- id: sdk-foundation
  title: SDK Foundation
  type: epic
  status: in_progress
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
  progress_pct: 19
  health: green
  tests_required:
  - make verify
  verify_commands:
  - make architecture-sync
  audit:
    created_at: '2025-09-29T18:00:00Z'
    created_by: gpt-5-codex
    updated_at: '2025-09-29T18:00:00Z'
    updated_by: gpt-5-codex
```

## Big Tasks
```yaml
- id: bigtask-arch-sync
  title: Централизация архитектуры
  type: feature
  status: in_progress
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
  progress_pct: 31
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
    updated_at: '2025-09-29T18:00:00Z'
    updated_by: gpt-5-codex
- id: bigtask-doc-ops
  title: Документационный конвейер
  type: feature
  status: planned
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
  progress_pct: 31
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
    updated_at: '2025-09-29T18:00:00Z'
    updated_by: gpt-5-codex
```
