## 0.3.0 — 2025-10-04
- Перезапуск под брендом *AgentControl Universal Agent SDK* с корпоративной документацией (README, AGENTS, architecture brief).
- Автоинициализация капсулы при первом `agentcall` и изоляция всех артефактов в `./agentcontrol/`.
- Обновлённые шаблоны 0.3.0 (dot-файлы, пайплайны внутри капсулы, корректная обработка `pytest` exit code 5).

## 0.2.1 — 2025-10-04
- Improved project detection errors with guidance (`agentcall status` outside project).
- Added telemetry commands and plugin APIs to CLI.
- Hardened release pipeline and PyPI packaging flow.

## 0.2.0 — 2025-10-04T00:00:00Z
- Added template-aware bootstrap (`agentcall init --template`), packaged templates for Python/Node/Monorepo.
- Introduced plugin system with sample `hello-plugin` and CLI commands `agentcall plugins ...`.
- Added telemetry framework (`agentcall telemetry report|tail|clear`) with opt-out via `AGENTCONTROL_TELEMETRY`.
- Hardened release pipeline (`scripts/release.sh`, GitHub workflow) and changelog tooling.
