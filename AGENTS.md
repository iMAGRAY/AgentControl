CONTEXT_INDEX:
  - path: README.md                      # value prop, quick start
  - path: architecture_plan.md           # strategic roadmap & phases
  - path: todo.machine.md                # program backlog (generated)
  - path: scripts/verify.sh              # canonical quality gate
  - path: scripts/test-place.sh          # симуляция установки SDK в .test_place
  - path: scripts/lib/quality_guard.py   # diff scanner & findings schema
  - path: src/agentcontrol/cli/main.py   # CLI entrypoint / auto-bootstrap logic
  - path: src/agentcontrol/app           # application services (bootstrap, mission, docs)
  - path: src/agentcontrol/utils         # telemetry, updater, helpers
  - path: src/agentcontrol/templates/0.5.1  # packaged capsule templates
  - path: tests/                         # pytest suite, property tests, integrations
  - path: reports/verify.json            # latest verify pipeline artefact
  - path: Makefile                       # proxy targets wrapping scripts/*.sh

TASKS:
  - id: SDK-001
    title: Восстановить и зафиксировать шаблоны капсулы 0.5.1
    status: wip
    priority: p0
    ac:
      - [Определить эталонный набор файлов .agentcontrol/, src/agentcontrol/templates/0.5.1, и убрать дубли/устаревшие директории, git status чистый]
      - [Добавить авто-проверку checksum для packaged templates в verify, падение при расхождении]
    owner: gpt-5-codex
  - id: SDK-002
    title: Автогенерация agent-digest и SLA шагов пайплайна
    status: done
    priority: p1
    ac:
      - [CLI формирует компактный контекстный digest (AGENTS, roadmap, verify summary) и сохраняет в .agentcontrol/state/agent_digest.json]
      - [Каждый шаг scripts/verify.sh имеет configurable timeout и structured log события]
    owner: gpt-5-codex
  - id: SDK-003
    title: Расширить тестовое покрытие updater/mission сервисов
    status: done
    priority: p1
    ac:
      - [Добавить unit tests для updater (network failure, cache fallback, dev guard) с >85% diff-cov]
      - [Добавить mission service tests, проверяющие timeline ingest и palette persist]
    owner: gpt-5-codex

HEALTH:
  status: yellow
  progress_pct: 65
  risks:
    - Исторические удаления `.agentcontrol/` и шаблонов 0.5.0 всё ещё висят в git status — ship заблокирован до синхронизации.
    - Новые checksum'ы 0.5.1 пока локальны; без upstream фикса авто-bootstrap на других машинах разъедется.
  next:
    - Определить эталонное дерево `.agentcontrol/` и привести рабочее состояние к нему (либо зафиксировать новую версию в git).
    - Финализировать перенос обновлённых шаблонов 0.5.1 (checksum, run.py, quality_guard) в release-пайплайн/документацию.
    - Прогнать полный `python -m pytest` (после конвергенции git) и включить новые тесты в CI.

SELF_TUNING:
  - rule: Перед ship обязательно запускать `agentcall verify` и фиксировать `reports/verify.json` в git.
    ttl: 2025-12-31
  - rule: Все изменения governance-артефактов (AGENTS, architecture_plan, todo.machine) сопровождаем синхронным обновлением verify/reportов.
    ttl: 2025-11-30
  - rule: Рабочие инструкции/временные файлы (например AGENTS1.md) не включаем в выпускаемый SDK; держим их вне артефактов agentclient.
    ttl: 2025-11-30
  - rule: Для интеграционных проверок используем `scripts/test-place.sh`, который создаёт/чистит `.test_place/` и разворачивает капсулу в изолированной среде.
    ttl: 2025-12-31
  - rule: Внутри репозитория SDK запрещено создавать/использовать `.agentcontrol/` и вызывать `agentcall` — сам SDK нельзя запускать на себе; все симуляции и тесты выполняем только через `scripts/test-place.sh` в `.test_place/`.
    ttl: 2026-01-01
