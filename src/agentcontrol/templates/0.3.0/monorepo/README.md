# AgentControl Monorepo Template

## Layout
- `packages/backend` — Python service with pytest scaffolding.
- `packages/web` — Node.js frontend module with ESLint + native tests.
- Shared governance artefacts (architecture, task board, docs) managed by AgentControl.

## Quick Start
```bash
agentcall init --template monorepo my-platform
cd my-platform
agentcall setup
agentcall verify
```

`agentcall setup` bootstraps both environments (Python venv + npm install). `agentcall verify` runs pytest and Node lint/test.

## Customisation
- Extend `config/commands.sh` to add package-specific tooling (type checking, packaging, deployment).
- Add more packages under `packages/` and update workflows accordingly.
- Use `agentcall agents` commands to wire autonomous agents into multi-service delivery.

## Tips
- Configure per-package CI by invoking `agentcall verify -- packages/backend` or via custom command pipelines in `agentcontrol/agentcall.yaml`.
- Keep `architecture/manifest.yaml` authoritative to reflect all bounded contexts and their tasks.
