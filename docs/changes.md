## 0.3.0 — 2025-10-04
- Rebranded to *AgentControl Universal Agent SDK* with corporate documentation (README, AGENTS charter, architecture brief).
- Auto-initialises the capsule on first `agentcall`, keeping all SDK assets inside `./agentcontrol/`.
- Refreshed 0.3.0 templates (dot files packaged, pipelines executed from the capsule, graceful handling of `pytest` exit code 5).

## 0.2.1 — 2025-10-04
- Improved project detection errors with guidance (`agentcall status` outside project).
- Added telemetry commands and plugin APIs to CLI.
- Hardened release pipeline and PyPI packaging flow.

## 0.2.0 — 2025-10-04T00:00:00Z
- Added template-aware bootstrap (`agentcall init --template`), packaged templates for Python/Node/Monorepo.
- Introduced plugin system with sample `hello-plugin` and CLI commands `agentcall plugins ...`.
- Added telemetry framework (`agentcall telemetry report|tail|clear`) with opt-out via `AGENTCONTROL_TELEMETRY`.
- Hardened release pipeline (`scripts/release.sh`, GitHub workflow) and changelog tooling.
