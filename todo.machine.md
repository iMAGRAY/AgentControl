## Program
```yaml
program: v1
updated_at: 2025-09-29T00:00:00Z
program_id: codex-sdk
name: GPT-5 Codex SDK Toolkit
objectives:
  - Унифицировать управление качеством для проектов агента GPT-5 Codex.
  - Обеспечить повторяемость процессов dev/verify/fix/ship.
  - Минимизировать когнитивную нагрузку оператора.
kpis: { uptime_pct: 99.9, tti_ms: 1500, error_rate_pct: 0.3 }
progress_pct: 50
health: green
phase_progress:
  MVP: 50
  Q1: 50
  Q2: 50
  Q3: 50
  Q4: 50
  Q5: 50
  Q6: 50
  Q7: 50
milestones:
  - { id: m_mvp, title: "MVP", due: 2025-10-15T00:00:00Z, status: done }
  - { id: m_q1, title: "Q1", due: 2025-12-31T00:00:00Z, status: in_progress }
  - { id: m_q2, title: "Q2", due: 2026-03-31T00:00:00Z, status: planned }
  - { id: m_q3, title: "Q3", due: 2026-06-30T00:00:00Z, status: planned }
  - { id: m_q4, title: "Q4", due: 2026-09-30T00:00:00Z, status: planned }
  - { id: m_q5, title: "Q5", due: 2026-12-31T00:00:00Z, status: planned }
  - { id: m_q6, title: "Q6", due: 2027-03-31T00:00:00Z, status: planned }
  - { id: m_q7, title: "Q7", due: 2027-06-30T00:00:00Z, status: planned }
policies:
  task_min_points: 5
```

## Epics
```yaml
id: sdk-foundation
title: "SDK Foundation"
type: epic
status: in_progress
priority: P0
size_points: 13
scope_paths:
  - scripts/**
  - config/**
  - AGENTS.md
  - todo.machine.md
spec: |
  Intent: предоставить базовый каркас SDK.
  Given: чистый репозиторий.
  When: агент инициализирует проект через Make команды.
  Then: настроены проверки, документация и единые процессы.
budgets: { latency_ms: 0, memory_mb: 0, bundle_kb: 0 }
risks:
  - Недостаточная адаптация под все стеки.
dependencies: []
big_tasks_planned:
  - bigtask-core-automation
progress_pct: 57
health: green
tests_required:
  - make verify
verify_commands:
  - make verify
docs_updates:
  - README.md
  - AGENTS.md
artifacts:
  - scripts/
audit:
  created_at: 2025-09-29T00:00:00Z
  created_by: gpt-5-codex
  updated_at: 2025-09-29T00:00:00Z
  updated_by: gpt-5-codex
```

## Big Tasks
```yaml
id: bigtask-core-automation
title: "Базовая автоматизация и контроль качества"
type: feature
status: in_progress
priority: P0
size_points: 8
parent_epic: sdk-foundation
scope_paths:
  - Makefile
  - scripts/**
  - config/**
spec: |
  Given: каталог проекта с установленным SDK.
  When: выполняются команды make dev/verify/fix/ship/status/task.
  Then: проверки проходят, пользователь получает понятный фидбек.
budgets: { latency_ms: 0, memory_mb: 0, bundle_kb: 0 }
risks:
  - Проверки могут потребовать доработки под конкретные стеки.
dependencies: []
progress_pct: 50
health: green
acceptance:
  - make status печатает дорожную карту и фокус-задачи.
  - make task grab/assign/validate работают без вручную редактировать JSON.
  - shell-скрипты проходят shellcheck, если он доступен.
tests_required:
  - make verify
verify_commands:
  - make verify
docs_updates:
  - README.md
  - AGENTS.md
artifacts:
  - scripts/
audit:
  created_at: 2025-09-29T00:00:00Z
  created_by: gpt-5-codex
  updated_at: 2025-09-29T00:00:00Z
  updated_by: gpt-5-codex
```
