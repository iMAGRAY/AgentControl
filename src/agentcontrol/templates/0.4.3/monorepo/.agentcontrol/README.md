# AgentControl Universal Agent SDK — Monorepo Capsule

This template provisions the AgentControl capsule for a mixed Python + Node.js monorepo. All SDK artefacts are stored in `agentcontrol/` while individual packages live under `packages/`.

## Structure
- `packages/backend/` — Python service managed via a local virtualenv (`.venv`).
- `packages/web/` — Node.js front-end managed via npm.

## Quick Start
1. Install global prerequisites and `agentcall`.
2. Bootstrap the capsule:
   ```bash
   agentcall status /path/to/project
   agentcall init --template monorepo /path/to/project
   ```
3. Prepare environments:
   ```bash
   cd /path/to/project
   agentcall setup
   ```
4. Run the verification pipeline:
   ```bash
   agentcall verify
   ```

## Verification Pipeline
- Backend: installs requirements and runs pytest (exit code 5 tolerated).
- Web: installs npm dependencies, runs lint and tests.
- Ship pipeline builds both components (`python -m build`, `npm run build`).

Refer to the root documentation for broader governance and operational guidelines.
