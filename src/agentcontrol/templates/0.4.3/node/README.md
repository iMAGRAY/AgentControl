# AgentControl Node.js Template

## Stack
- Node.js ≥ 18 (ESM support)
- ESLint (standard config)
- Native `node --test`

## Quick Start
```bash
agentcall init --template node my-node-service
cd my-node-service
agentcall setup
agentcall verify
```

## Features
- npm lifecycle preconfigured (`lint`, `test`, `build`).
- ESLint Standard setup via `.eslintrc.json`.
- Sample module (`src/index.js`) with accompanying Node test (`tests/index.test.js`).
- AgentControl governance artefacts generated on init (architecture manifest, docs, task board).

## Pipelines
| Command | Action |
| --- | --- |
| `agentcall setup` | `npm install` to sync dependencies. |
| `agentcall verify` | Installs deps → runs lint → `node --test`. |
| `agentcall fix` | Executes ESLint autofix (configure as needed). |
| `agentcall ship` | Default `npm run build` (customise for release). |

## Customisation Tips
- Update `package.json` with additional scripts (type checking, bundling).
- Extend `config/commands.sh` with stack-specific tasks (Vitest, Playwright, etc.).
- Maintain DDD artefacts (`architecture/manifest.yaml`, docs/adr) to stay aligned with governance pipeline.
