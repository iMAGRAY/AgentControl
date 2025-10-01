# GPT-5 Codex SDK Toolkit

Enterprise-grade orchestration for autonomous coding agents. The toolkit ships a curated command surface, deterministic planning artefacts, and turnkey agent runtimes so GPT-class developers land in a predictable environment within seconds.

## Key Outcomes
- **Deterministic workflows** — one-command targets (`make setup/init/dev/verify/fix/review/ship`) enforce uniform pipelines on every machine and in CI.
- **Integrated governance** — roadmaps, task boards, and architectural manifests stay synchronized through `make progress`, `make status`, and `make architecture-sync`.
- **Agent-ready runtime** — Codex and Claude CLIs install, authenticate, and execute inside the project sandbox, delegating work or reviews with zero manual prep.
- **Knowledge fabric** — Memory Heart builds a local vector index of source and docs so agents and humans can query the entire codebase with millisecond latency.
- **Compliance guardrails** — lockfiles, SBOMs, quality gates, and audit logs keep delivery reproducible and verifiable.

## Quick Start
1. **Install prerequisites** (Bash ≥ 5.0, GNU Make ≥ 4.0, Python ≥ 3.10, Cargo ≥ 1.75, Node.js ≥ 18). Ensure `sudo` is available if system packages must be installed.
2. **Run the bootstrap:**
   ```bash
   make setup
   ```
   This installs system tooling (shellcheck, Go toolchain, etc.), provisions `.venv`, installs Python/Node requirements, synchronizes submodules, builds Codex CLI, installs Claude CLI, and primes Memory Heart (skip via `SKIP_AGENT_INSTALL=1` or `SKIP_HEART_SYNC=1`).
3. **Prime the workspace:**
   ```bash
   make init
   ```
   Generates default command hooks, roadmap/task board scaffolding, and status baselines.
4. **Authenticate agents once:**
   ```bash
   make agents auth
   ```
   Launches Codex and Claude login flows, stores credentials under `state/agents/`, and reports status. To rotate credentials run `make agents auth-logout` and invoke auth again.
5. **Verify the installation:**
   ```bash
   make verify
   ```
   Runs lint/test/security gates, validates roadmap & task board, performs Memory Heart freshness checks, and emits `reports/verify.json`.

## Command Portfolio
| Command | Purpose | Notes |
| --- | --- | --- |
| `make setup` | Install required system packages, Python/Node deps, and agent CLIs. | Use `SKIP_AGENT_INSTALL=1` or `SKIP_HEART_SYNC=1` to shorten bootstrap on air-gapped hosts. |
| `make init` | Generate command hooks, roadmap/task board baselines, and status reports. | Idempotent; safe to rerun after upgrades. |
| `make dev` | Print the quick reference (from `AGENTS.md`) and start configured dev commands. | Respects overrides in `config/commands.sh`. |
| `make verify` | Canonical quality gate (format, lint, tests, coverage, security, docs, roadmap/task board validation, Memory Heart check). | Supports `VERIFY_MODE=prepush|ci|full`, `CHANGED_ONLY=1`, `NET=0|1`, `TIMEOUT_MIN=<n>`, `QUIET=1`, `JSON=1`. |
| `make fix` | Execute safe autofixes defined in `SDK_FIX_COMMANDS`. | Follow with `make verify` before committing. |
| `make review` | Diff-focused review workflow (`SDK_REVIEW_LINTERS`, `SDK_TEST_COMMAND`, optional `diff-cover`). | Outputs `reports/review.json`; accepts `REVIEW_BASE_REF`, `REVIEW_SAVE`, `REVIEW_FORMAT`. |
| `make ship` | Release gate: runs verify in pre-push mode, bumps version (`BUMP=patch|minor|major`), updates changelog, tags and pushes. | Aborts if any gate fails or open micro tasks exist. |
| `make status` | Comprehensive dashboard (Program/Epics/Big Tasks, roadmap phases, task board summary, Memory Heart state). | Invokes `make progress` automatically before rendering tables. |
| `make roadmap` | Phase-focused report with formal progress tables and deltas. | Uses the same progress engine as `make progress`. |
| `make progress` | Parse `architecture/manifest.yaml` and `todo.machine.md`, recompute weighted progress, sync YAML blocks, and persist audit metadata. | Runs in dry-run mode with `DRY_RUN=1`. |
| `make agents-install` | Build Codex CLI from `vendor/codex` (Cargo) and install Claude CLI into `scripts/bin/`. | Falls back to system binaries when sandbox install fails. |
| `make agents auth` | Authenticate all configured agent CLIs and store credentials in the sandbox state directory. | Skips already authenticated agents and reminds about `make agents auth-logout`. |
| `make agents status` | Display health of agent binaries, credentials, and last activity. | Useful for CI smoke tests. |
| `make heart-sync` | Refresh the Memory Heart vector index. | Query with `make heart-query Q="…"` or expose an API via `make heart-serve`. |

## Agent Operations
### Installing and Updating CLIs
- `make vendor-update` pulls upstream submodules (Codex CLI, Claude Code, Memory Heart).
- `make agents-install` compiles Codex (Rust) and installs Claude (Node). Artifacts land in `scripts/bin/`. Installation logs are stored in `reports/agents/install.timestamp`.

### Authenticating Agents
- Run `make agents auth` in the project root. Successful logins persist JSON credentials in `state/agents/<agent>/`. CLI prompts close automatically once tokens are captured.
- To rotate credentials: `make agents auth-logout` removes stored tokens and marks the status as `logged_out`.

### Delegating Work
- `make agent-assign TASK=T-123 [AGENT=codex] [ROLE="Implementation Lead"]` prepares contextual bundles (git diff, Memory Heart excerpts, roadmap slices) and streams them to the chosen CLI.
- `make agent-plan TASK=T-123` or `make agent-analysis` request planning or diagnostic summaries.
- Workflow pipelines combine assign + review steps via `make agents workflow pipeline --task=T-123 [--workflow=default]`. Configure defaults in `config/agents.json`.
- Inspect agent activity with `make agents logs [AGENT=claude] [LAST=20]` and verify readiness via `make agents status`.

### Sandbox Execution
Agent processes run through `scripts/agents/run.py`, which wraps binaries inside bubblewrap when available (fallback: direct execution). Adjust sandbox profiles in `config/agents.json` per agent if custom isolation is required.

## Memory Heart
- Configuration lives in `config/heart.json`; state is rooted at `state/heart/`.
- `make heart-sync` updates embeddings incrementally; use `SKIP_HEART_SYNC=1` during bootstrap to defer large syncs.
- `make heart-query Q="build pipeline"` prints top-matching chunks with file and line references.
- `make heart-serve` exposes the index via HTTP for real-time agent consumption.

## Planning and Governance
- `todo.machine.md` maintains Program → Epics → Big Tasks (no micro tasks). It is regenerated by `make progress` and `make architecture-sync`.
- `data/tasks.board.json`, `state/task_state.json`, and `journal/task_events.jsonl` capture the operational task board. Manage entries via `make task add/take/drop/done/status/conflicts/metrics/history`.
- `architecture/manifest.yaml` is the source of truth for program metadata, systems, tasks, ADR/RFC references, and roadmap phases. `make architecture-sync` regenerates docs/ADR/RFC/roadmap artefacts from this manifest.
- Micro tasks belong exclusively to the Update Plan Tool (UPT) inside the Codex CLI; ensure the queue is empty before running `make ship`.

## Customising Commands
Edit `config/commands.sh` to align the toolkit with the target stack:
```bash
SDK_VERIFY_COMMANDS=("npm run lint" "npm test")
SDK_FIX_COMMANDS=("npm run lint -- --fix")
SDK_SHIP_COMMANDS=("npm run build" "npm publish")
```
Commands execute sequentially; any non-zero exit aborts the current phase. All scripts use `set -Eeuo pipefail` for predictable failure handling.

## Continuous Integration
- GitHub Actions loads `.github/workflows/ci.yml`, which runs `make verify` on push/PR and nightly at 03:00 UTC. SARIF findings surface in GitHub Security alerts.
- `make status` and `make roadmap` are safe to publish as artefacts for leadership dashboards.
- Pre-push hooks should call `make verify VERIFY_MODE=prepush CHANGED_ONLY=1 JSON=1` to block regressions early.

## Troubleshooting
- **Permission denied inside `state/`** — ensure the project root is writable. When running inside restricted directories, export `AGENTCONTROL_STATE_DIR=/custom/path` before invoking commands.
- **Third-party installs are slow** — set `SKIP_AGENT_INSTALL=1` and run `make agents-install` later. Cache `~/.cache/pip` and `~/.cache/npm` in CI.
- **Memory Heart syncs are heavy** — run `make heart-sync DRY_RUN=1` to estimate impact, or configure path globs in `config/heart.json` to reduce scope.
- **Agents reuse global credentials** — verify that `make agents auth` created files under `state/agents/`. Run `make agents auth-logout` followed by `make agents auth` to regenerate sandboxed credentials.
- **Quality gates fail on placeholders** — update `config/commands.sh` with real commands; the SDK promotes safe defaults when placeholders remain.

## Support & Change Control
- Source of truth for governance: `AGENTS.md`, `architecture/manifest.yaml`, `todo.machine.md`, and `data/tasks.board.json`.
- Architectural decisions live in `docs/adr/`; RFC drafts in `docs/rfc/`; change log seeds in `docs/changes.md`.
- Submit pull requests with `make verify` output attached. For high-risk modifications, pair with an agent-driven review via `make agents workflow pipeline`.

For questions or escalations contact the owners listed in `AGENTS.md`.
