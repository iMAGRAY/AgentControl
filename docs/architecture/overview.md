# AgentControl Universal Agent SDK — Architecture Brief

## 1. Программный контур
- Program ID: agentcontrol-sdk
- Name: AgentControl Universal Agent SDK
- Version: 0.3.0
- Updated: 2025-10-04T09:50:00Z
- Health: green (progress 100%)

## 2. Системный ландшафт
| ID | Назначение | ADR | RFC | Статус | Зависимости | Фаза | Ключевые KPI |
| --- | --- | --- | --- | --- | --- | --- | --- |
| control-plane | Управление архитектурой, документацией и пайплайнами из единого манифеста. | ADR-0001 | RFC-0001 | active | — | m_q1 | quality_pct ≥ 95, cycle_hours ≤ 2 |
| doc-sync | Автосборка документации и индексов ADR/RFC из манифеста. | ADR-0002 | — | planned | control-plane | m_q1 | freshness_minutes ≤ 5 |
| task-ops | Генерация и поддержание задач в соответствии с архитектурой. | ADR-0003 | — | planned | control-plane, doc-sync | m_q1 | traceability_pct = 100 |

## 3. Трассировка задач
| Task ID | Заголовок | Статус | Owner | System | Big Task | Epic | Phase |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ARCH-001 | Manifest-driven sync engine | done | agentcontrol-core | control-plane | bigtask-arch-sync | sdk-foundation | m_q1 |
| ARCH-002 | Automated documentation synthesis | done | agentcontrol-core | doc-sync | bigtask-doc-ops | sdk-foundation | m_q1 |
| ARCH-003 | Task board governance | done | agentcontrol-core | task-ops | bigtask-arch-sync | sdk-foundation | m_q1 |
| TEST-001 | Pytest in agentcall verify | done | agentcontrol-core | control-plane | bigtask-test-pytest | sdk-foundation | m_q1 |
| OPS-001 | Doctor UX with tables and links | done | agentcontrol-core | control-plane | bigtask-doctor-ux | sdk-foundation | m_q1 |

## 4. Документы и артефакты
- Manifest: `architecture/manifest.yaml`
- ADR Index: `docs/adr/index.md`
- RFC Index: `docs/rfc/index.md`
- Change Log: `docs/changes.md`

## 5. Контроль изменений
- Любое отклонение от манифеста требует обновления `architecture/manifest.yaml` и сопутствующих ADR/RFC.
- После обновления запускать `agentcall status` (автосинхронизация) и при необходимости `agentcall review`.

---
Обновление осуществляется группой AgentControl Core. Запросы на изменения через `agentcall agents workflow --task=<ID>`.
