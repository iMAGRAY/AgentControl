## Program
```yaml
program: v1
program_id: agentcontrol-sdk
name: AgentControl Universal Agent SDK
objectives:
- Centralize architectural decisions and roadmaps in a single source of truth.
- Automate generation of documentation, ADR/RFC indices, and the task board from the architecture manifest.
- Guarantee reproducible agent decision and delivery cycles end to end.
kpis:
  uptime_pct: 99.9
  tti_ms: 1200
  error_rate_pct: 0.1
owners:
- vibe-coder
- agentcontrol-core
policies:
  task_min_points: 5
teach: true
updated_at: '2025-10-01T05:17:22Z'
health: green
progress_pct: 100
phase_progress:
  Phase 0 – Feasibility: 100
  Phase 1 – Foundation: 100
  Phase 2 – Core Build: 100
  Phase 3 – Beta: 100
  Phase 4 – GA: 100
  Phase 5 – Ops & Scaling: 100
  Phase 6 – Optimization: 100
  Phase 7 – Sustain & Innovate: 100
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
  spec: 'Intent: deliver an unshakeable governance backbone for architecture and documentation.


    Given: a clean repository with the SDK installed.


    When: an agent runs agentcall init/verify/fix/ship/status.


    Then: every artefact regenerates from manifest.yaml and stays consistent.

    '
  budgets:
    latency_ms: 0
    memory_mb: 0
    bundle_kb: 0
  risks:
  - Insufficient manifest coverage forces manual edits.
  - Concurrent edits may corrupt state without guardrails.
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
  - agentcall verify
  verify_commands:
  - agentcall run architecture-sync
  audit:
    created_at: '2025-09-29T18:00:00Z'
    created_by: agentcontrol-core
    updated_at: '2025-09-30T13:20:00Z'
    updated_by: agentcontrol-core
```

## Big Tasks
```yaml
- id: bigtask-arch-sync
  title: Architecture centralisation
  type: feature
  status: done
  priority: P0
  size_points: 13
  parent_epic: sdk-foundation
  scope_paths:
  - architecture/**
  - scripts/sync-architecture.sh
  - scripts/lib/architecture_tool.py
  spec: 'Given: manifest.yaml describes the system.


    When: agentcall run architecture-sync runs.


    Then: documentation, todo.machine.md, and the task board are synchronised automatically.

    '
  budgets:
    latency_ms: 0
    memory_mb: 0
    bundle_kb: 0
  risks:
  - Schema mistakes propagate across every generated artefact.
  dependencies: []
  progress_pct: 100
  health: green
  acceptance:
  - All derivative documents depend solely on manifest.yaml.
  - agentcall verify fails when inconsistencies are detected.
  tests_required:
  - agentcall run architecture-sync
  verify_commands:
  - agentcall run architecture-sync
  docs_updates:
  - docs/architecture/overview.md
  - docs/adr/index.md
  artifacts:
  - scripts/lib/architecture_tool.py
  audit:
    created_at: '2025-09-29T18:00:00Z'
    created_by: agentcontrol-core
    updated_at: '2025-09-30T13:20:00Z'
    updated_by: agentcontrol-core
- id: bigtask-doc-ops
  title: Documentation delivery pipeline
  type: feature
  status: done
  priority: P1
  size_points: 8
  parent_epic: sdk-foundation
  scope_paths:
  - docs/**
  - templates/**
  spec: 'Given: manifest.yaml changes.


    When: agentcall run architecture-sync executes.


    Then: the central overview, ADR index, and RFC index rebuild deterministically.

    '
  budgets:
    latency_ms: 0
    memory_mb: 0
    bundle_kb: 0
  risks:
  - Templates may drift without automated tests.
  dependencies:
  - bigtask-arch-sync
  progress_pct: 100
  health: green
  acceptance:
  - Generation is idempotent and covers the entire architecture scope.
  tests_required:
  - agentcall run architecture-sync
  verify_commands:
  - agentcall run architecture-sync
  docs_updates:
  - docs/architecture/overview.md
  - docs/adr/index.md
  - docs/rfc/index.md
  artifacts:
  - templates/
  audit:
    created_at: '2025-09-29T18:00:00Z'
    created_by: agentcontrol-core
    updated_at: '2025-09-30T13:20:00Z'
    updated_by: agentcontrol-core
- id: bigtask-test-pytest
  title: Pytest in verify pipeline
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
  spec: 'Intent: enforce pytest execution in CI.


    Given: a clean repository.


    When: agentcall verify or agentcall ship runs.


    Then: pytest executes from .venv and fails the build on test errors.

    '
  budgets:
    latency_ms: 0
    memory_mb: 0
    bundle_kb: 0
  risks:
  - Dependency installation failures block the verify pipeline.
  dependencies: []
  progress_pct: 100
  health: green
  acceptance:
  - agentcall verify creates .venv and runs pytest -q.
  - README documents local test execution steps.
  tests_required:
  - agentcall verify
  verify_commands:
  - agentcall verify
  docs_updates:
  - README.md
  artifacts:
  - config/commands.sh
  - requirements.txt
  audit:
    created_at: '2025-09-30T05:20:00Z'
    created_by: agentcontrol-core
    updated_at: '2025-09-30T06:05:00Z'
    updated_by: agentcontrol-core
- id: bigtask-doctor-ux
  title: Improved agentcall doctor output
  type: ops
  status: done
  priority: P1
  size_points: 5
  parent_epic: sdk-foundation
  scope_paths:
  - scripts/doctor.sh
  - scripts/lib/deps_checker.py
  spec: 'Intent: agentcall doctor reports easy to scan.


    Given: an operator runs agentcall doctor.


    When: the environment checks complete.


    Then: results render as a table with commands and support links.

    '
  budgets:
    latency_ms: 0
    memory_mb: 0
    bundle_kb: 0
  risks:
  - Linked resources may age without periodic review.
  dependencies:
  - bigtask-arch-sync
  progress_pct: 100
  health: green
  acceptance:
  - agentcall doctor prints a status table with details and links.
  - reports/doctor.json remains backward compatible.
  tests_required:
  - agentcall doctor
  verify_commands:
  - agentcall doctor || true
  docs_updates: []
  artifacts:
  - scripts/doctor.sh
  - scripts/lib/deps_checker.py
  audit:
    created_at: '2025-09-30T05:20:00Z'
    created_by: agentcontrol-core
    updated_at: '2025-09-30T06:05:00Z'
    updated_by: agentcontrol-core
```
