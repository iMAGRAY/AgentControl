CONTEXT_INDEX:
  - path: README.md                      # value proposition, quick start
  - path: architecture_plan.md           # strategic roadmap and phases
  - path: todo.machine.md                # program backlog (generated)
  - path: scripts/verify.sh              # canonical quality gate
  - path: scripts/test-place.sh          # sandbox quickstart/verify simulation
  - path: scripts/lib/quality_guard.py   # diff scanner and findings schema
  - path: src/agentcontrol/cli/main.py   # CLI entry point / quickstart logic
  - path: src/agentcontrol/app           # application services (bootstrap, mission, docs)
  - path: src/agentcontrol/utils         # telemetry, updater, helpers
  - path: src/agentcontrol/templates/0.5.1  # packaged capsule templates
  - path: tests/                         # pytest suite, property tests, integrations
  - path: reports/verify.json            # latest verify pipeline artefact
  - path: Makefile                       # proxy targets wrapping scripts/*.sh

TASKS:
  - id: SDK-001
    title: Seal template integrity for capsules 0.5.1
    status: done
    priority: p0
    ac:
      - [Canonical template tree stored in src/agentcontrol/templates/0.5.1, old 0.5.0 assets removed, git status clean]
      - [Verify pipeline fails on checksum drift via `template-integrity` step]
    owner: gpt-5-codex
  - id: SDK-002
    title: Ship agent digest + pipeline SLA telemetry
    status: done
    priority: p1
    ac:
      - [CLI produces compact agent digest (AGENTS, roadmap, verify summary) into `.test_place/state/agent_digest.json`]
      - [Every step in `scripts/verify.sh` logs JSON with duration/timeout metadata]
    owner: gpt-5-codex
  - id: SDK-003
    title: Extend updater/mission coverage
    status: done
    priority: p1
    ac:
      - [Unit tests for updater cover network failure, cache fallback, dev guard]
      - [Mission service tests validate timeline ingest and palette persistence]
    owner: gpt-5-codex

HEALTH:
  status: green
  progress_pct: 100
  risks: []
  next:
    - Keep `scripts/test-place.sh` and `template-integrity` up to date for future releases.
    - Refresh capsules/checksums/docs whenever a new SDK version ships.

SELF_TUNING:
  - rule: Run `agentcall verify` before ship and commit `reports/verify.json` with the change set.
    ttl: 2025-12-31
  - rule: Any governance artefact changes (AGENTS, architecture_plan, todo.machine) must be synchronized with verify reports.
    ttl: 2025-11-30
  - rule: Keep working drafts (e.g. AGENTS1.md) outside the release artefacts.
    ttl: 2025-11-30
  - rule: Use `scripts/test-place.sh` for integration checks; it creates/cleans `.test_place/` and bootstraps a sandbox project.
    ttl: 2025-12-31
  - rule: The authoritative todo list lives inside AGENTS.md; do not maintain standalone `todo.md`.
    ttl: 2026-01-01
  - rule: Before starting and after finishing work, reconcile AGENTS.md (todo section) and `architecture_plan.md` with the latest progress/decisions.
    ttl: 2026-01-01
  - rule: Never create `.agentcontrol/` or run `agentcall` inside this SDK repository; all simulations must go through `.test_place/`.
    ttl: 2026-01-01
