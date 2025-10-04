# AgentControl Universal Agent SDK — Architecture Overview

## Program Snapshot
- Program ID: agentcontrol-sdk
- Name: AgentControl Universal Agent SDK
- Version: 0.3.0
- Updated: 2025-10-04T10:05:00Z
- Status: green (progress 100%)

## Systems
| ID | Purpose | ADR | RFC | Status | Dependencies | Roadmap Phase | Key Metrics |
| --- | --- | --- | --- | --- | --- | --- | --- |
| control-plane | Govern architecture, documentation, and tasks from a single manifest-driven pipeline. | ADR-0001 | RFC-0001 | active | — | m_q1 | quality_pct ≥ 95, cycle_hours ≤ 2 |
| doc-sync | Auto-generate documentation and ADR/RFC indices from the manifest. | ADR-0002 | — | planned | control-plane | m_q1 | freshness_minutes ≤ 5 |
| task-ops | Maintain task board alignment with architecture intent. | ADR-0003 | — | planned | control-plane, doc-sync | m_q1 | traceability_pct = 100 |

## Traceability
| Task ID | Title | Status | Owner | System | Big Task | Epic | Phase |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ARCH-001 | Manifest-driven sync engine | done | agentcontrol-core | control-plane | bigtask-arch-sync | sdk-foundation | m_q1 |
| ARCH-002 | Automated documentation synthesis | done | agentcontrol-core | doc-sync | bigtask-doc-ops | sdk-foundation | m_q1 |
| ARCH-003 | Task board governance | done | agentcontrol-core | task-ops | bigtask-arch-sync | sdk-foundation | m_q1 |
| TEST-001 | Pytest in agentcall verify | done | agentcontrol-core | control-plane | bigtask-test-pytest | sdk-foundation | m_q1 |
| OPS-001 | Doctor UX with tables and links | done | agentcontrol-core | control-plane | bigtask-doctor-ux | sdk-foundation | m_q1 |

## Documentation Set
- Manifest: `architecture/manifest.yaml`
- ADR index: `docs/adr/index.md`
- RFC index: `docs/rfc/index.md`
- Change log: `docs/changes.md`

## Change Management
- Update `architecture/manifest.yaml` and relevant ADR/RFC files before altering governance processes.
- After manifest updates, run `agentcall status` (auto-sync) and, if required, `agentcall review`.

Maintained by AgentControl Core. Submit change requests via `agentcall agents workflow --task=<ID>`.
