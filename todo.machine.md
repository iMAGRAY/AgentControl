## Program
```yaml
program: v1
program_id: agentcontrol-sdk
name: AgentControl Universal Agent SDK
objectives:
- Provide a turnkey control plane and pipelines for autonomous engineers.
- Keep architecture, docs, tasks, and telemetry in deterministic sync.
- Guarantee reproducible delivery workflows across any repository.
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
updated_at: '2025-10-06T05:00:00Z'
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
  spec: 'Deliver an unshakeable governance backbone for architecture and documentation.'
  budgets:
    latency_ms: 0
    memory_mb: 0
    bundle_kb: 0
  risks:
  - Manual edits bypassing manifest.
  - Concurrent updates without guardrails.
  dependencies: []
  docs_updates:
  - README.md
  - AGENTS.md
  - docs/architecture/overview.md
  artifacts:
  - scripts/
  - architecture/
  big_tasks_planned:
  - bigtask-template-wall
  - bigtask-agent-digest
  - bigtask-coverage-shield
  progress_pct: 100
  health: green
  tests_required:
  - agentcall verify
  verify_commands:
  - agentcall run architecture-sync
  audit:
    created_at: '2025-09-29T18:00:00Z'
    created_by: agentcontrol-core
    updated_at: '2025-10-06T05:00:00Z'
    updated_by: agentcontrol-core
```

## Big Tasks
```yaml
- id: bigtask-template-wall
  title: Template integrity guard
  type: feature
  status: done
  priority: P0
  size_points: 8
  parent_epic: sdk-foundation
  scope_paths:
  - src/agentcontrol/templates/**
  - scripts/check-template-integrity.py
  - scripts/verify.sh
  spec: 'Ensure packaged templates stay deterministic; fail verify on checksum drift.'
  budgets:
    latency_ms: 0
    memory_mb: 0
    bundle_kb: 0
  risks: []
  dependencies: []
  progress_pct: 100
  health: green
  acceptance:
  - `scripts/verify.sh` includes `template-integrity` step.
  - Git status is clean after template sync.
- id: bigtask-agent-digest
  title: Agent digest & SLA logging
  type: feature
  status: done
  priority: P1
  size_points: 5
  parent_epic: sdk-foundation
  scope_paths:
  - scripts/generate-agent-digest.py
  - scripts/verify.sh
  - scripts/test-place.sh
  spec: 'Provide compact context for agents and structured verify telemetry.'
  budgets:
    latency_ms: 0
    memory_mb: 0
    bundle_kb: 0
  risks: []
  dependencies:
  - bigtask-template-wall
  progress_pct: 100
  health: green
  acceptance:
  - `.test_place/state/agent_digest.json` created during quickstart tests.
  - Verify writes `reports/verify_steps.jsonl` with timeout metadata.
- id: bigtask-coverage-shield
  title: Updater & mission coverage shield
  type: test
  status: done
  priority: P1
  size_points: 5
  parent_epic: sdk-foundation
  scope_paths:
  - tests/updater/**
  - tests/mission/**
  - src/agentcontrol/utils/updater.py
  - src/agentcontrol/app/mission/service.py
  spec: 'Cover cache fallback, dev guard, mission palette and timeline ingestion.'
  budgets:
    latency_ms: 0
    memory_mb: 0
    bundle_kb: 0
  risks: []
  dependencies:
  - bigtask-template-wall
  progress_pct: 100
  health: green
  acceptance:
  - `python -m pytest` runs the new tests.
  - `scripts/verify.sh` triggers the sandbox smoke via `test-place`.
```
