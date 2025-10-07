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
  - id: CORE-001
    title: Seal template integrity for capsules 0.5.x
    status: done
    priority: p0
    ac:
      - [Canonical template tree stored in `src/agentcontrol/templates/0.5.1`, legacy assets removed]
      - [Verify pipeline fails on checksum drift via `template-integrity` step]
    owner: sdk-core
  - id: CORE-002
    title: Ship agent digest + pipeline SLA telemetry
    status: done
    priority: p1
    ac:
      - [CLI produces compact agent digest into `.test_place/state/agent_digest.json`]
      - [All verify steps emit duration/timeout JSON in `reports/verify_steps.jsonl`]
    owner: sdk-core
  - id: CORE-003
    title: Extend updater/mission coverage
    status: done
    priority: p1
    ac:
      - [Updater unit tests cover network failure, cache fallback, dev guard]
      - [Mission service tests validate palette persistence + timeline ingest]
    owner: sdk-core
  - id: P5-001
    title: Legacy capsule auto-upgrade
    status: done
    priority: p0
    ac:
      - [`agentcall upgrade` migrates legacy `./agentcontrol/` layout to `.agentcontrol/` capsule with timestamped backup]
      - [Verify step asserts absence of legacy pipelines after upgrade]
  - id: P5-002
    title: Makefile / CLI alignment guard
    status: done
    priority: p0
    ac:
      - [`scripts/check-make-alignment.py` wired into verify]
      - [Mismatched Make targets vs CLI pipelines fail CI with actionable diff]
  - id: P7-001
    title: Extension CLI + schema
    status: done
    priority: p1
    ac:
      - [`agentcall extension init|add|list|remove` manage catalog entries]
      - [Schema validation + fixtures under `tests/extensions`]
  - id: P7-002
    title: Extension registry & documentation
    status: done
    priority: p1
    ac:
      - [`reports/extensions.json` enumerates installed extensions with metadata]
      - [`docs/tutorials/extensions.md` and sample projects published]
  - id: P8-001
    title: Mission dashboard UX (TUI/Web/Snapshot)
    status: done
    priority: p1
    ac:
      - [`agentcall mission dashboard` renders docs/quality/tasks/mcp/timeline panels with hotkeys]
      - [`agentcall mission dashboard --serve` streams SSE + secures `/playbooks/<id>` POST]
      - [`--snapshot` exports HTML to `reports/mission/`]
  - id: P9-001
    title: Mission watcher telemetry core
    status: done
    priority: p1
    ac:
      - [`agentcall mission watch` reacts to perf/docs events and logs actorId/origin/outcome/tags]
      - [Recent actions surface in `mission-actions.json` and analytics]
  - id: P9-002
    title: Notification adapters & SLA policies
    status: removed
    priority: p1
    ac:
      - [Removed per AI-only scope; communication adapters intentionally omitted]
  - id: P10-001
    title: Task sync core
    status: done
    priority: p0
    ac:
      - [`agentcall tasks sync` diffs `data/tasks.board.json` vs provider with create/update/close]
      - [Dry-run JSON output consumed by mission analytics]
  - id: P10-002
    title: External task connectors
    status: done
    priority: p0
    ac:
      - [Jira connector with encrypted credentials + pagination/retry tests]
      - [GitHub Issues connector respecting labels/assignees/milestones]
      - [Mission dashboard reflects external status backfeed]
  - id: P11-001
    title: Docs portal generator
    status: done
    priority: p1
    ac:
      - [`agentcall docs portal` emits static site ≤ size budget]
      - [Search + provenance for tutorials/examples]
  - id: P11-002
    title: Knowledge lint & coverage
    status: done
    priority: p1
    ac:
      - [`agentcall docs lint --knowledge` outputs `reports/docs_coverage.json`]
      - [Verify fails on stale links/orphan tutorials]
  - id: P11-003
    title: Automated release notes
    status: done
    priority: p1
    ac:
      - [`agentcall release notes` synthesises changelog from telemetry + git tags]
      - [Docs updated with workflow guidance]
  - id: P11-004
    title: Sample gallery
    status: done
    priority: p2
    ac:
      - [Curated gallery of mono/poly/meta repos packaged ≤30 MB]
      - [Quickstart docs link to gallery entries]
  - id: P12-001
    title: Workspace descriptor & aggregation
    status: todo
    priority: p1
    ac:
      - [`workspace.yaml` schema defined and validated]
      - [`agentcall mission summary --workspace` aggregates multi-repo status]
  - id: P12-002
    title: Distributed agent scheduler
    status: todo
    priority: p1
    ac:
      - [`agentcall mission assign` schedules tasks with optimistic locking & quotas]
      - [Telemetry records assignment outcomes/error rate]
  - id: P12-003
    title: Sharded performance harness
    status: todo
    priority: p2
    ac:
      - [Docs benchmark runs N shards in parallel ≤1.2× baseline runtime]
      - [History comparisons stored with shard metadata]
  - id: P12-004
    title: Stress & fuzz harness
    status: todo
    priority: p2
    ac:
      - [Nightly stress/fuzz jobs emit summary JSON + triage docs]
      - [Failures block release pipeline until acknowledged]
  - id: P13-001
    title: Bootstrap installer
    status: todo
    priority: p1
    ac:
      - [`agentcontrol-install.sh` provisions pipx/venv without sudo]
      - [CI matrix (Linux/macOS) passes smoke tests]
  - id: P13-002
    title: Cache doctor
    status: todo
    priority: p1
    ac:
      - [`agentcall cache doctor` reports template cache health & quotas]
      - [Verify fails on critical cache inconsistencies]
  - id: P13-003
    title: Binary bundle feasibility
    status: todo
    priority: p2
    ac:
      - [Document pros/cons of standalone bundle]
      - [Prototype (PyInstaller/rye/etc.) archived for experimentation]
  - id: P13-004
    title: Telemetry opt-in wizard
    status: todo
    priority: p2
    ac:
      - [Opt-in/out flow prompts on first run; persisted state respected globally]
      - [`agentcall telemetry status` reflects consent]

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
