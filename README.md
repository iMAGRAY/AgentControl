# AgentControl Universal Agent SDK

AgentControl is an enterprise-grade toolkit that standardises how autonomous engineers and human teams operate on any codebase. The SDK provisions a consistent command surface, deterministic governance assets, and ready-to-use agent runtimes, so delivery begins immediately without bespoke project bootstrapping.

## 1. Value Proposition
- **Single operational entrypoint.** The `agentcall` CLI aligns humans and agents on the same verified pipelines (`init`, `verify`, `ship`, `status`, and more).
- **Integrated governance.** Roadmaps, task boards, and architecture manifests remain in sync through automated status and progress commands.
- **Agent-first runtime.** Codex/Claude CLIs, Memory Heart, and supporting scripts install without manual steps, keeping cognitive load low for automated contributors.
- **Compliance by default.** Lockfiles, SBOM generation, audit artefacts, and release gates are embedded into the workflow.

## 2. Solution Architecture
| Layer | Responsibility | Key artefacts |
| --- | --- | --- |
| **CLI & Pipelines** | Lifecycle orchestration (`init`, `verify`, `ship`, `status`). | `src/agentcontrol/cli`, `src/agentcontrol/app` |
| **Domain & Governance** | Capsule, template, and command models with explicit invariants. | `src/agentcontrol/domain`, `src/agentcontrol/ports` |
| **Templates** | Project capsules (`default`, `python`, `node`, `monorepo`) fully contained inside `./agentcontrol/`. | `src/agentcontrol/templates/<version>/<template>` |
| **Plugin framework** | Extensible CLI via the `agentcontrol.plugins` entry point group. | `src/agentcontrol/plugins`, `examples/plugins/` |
| **Observability** | Telemetry, Memory Heart, status artefacts. | `src/agentcontrol/utils/telemetry`, `reports/` |

## 3. Quick Start (fresh machine)
1. **Prerequisites.** Bash ≥ 5.0, Python ≥ 3.10, Node.js ≥ 18, Cargo ≥ 1.75. Pin versions in CI for reproducibility.
2. **Install the SDK globally.**
   ```bash
   ./scripts/install_agentcontrol.sh
   pipx install agentcontrol  # alternatively: python3 -m pip install agentcontrol
   ```
   Templates are placed under `~/.agentcontrol/templates/<channel>/<version>` and `agentcall` is published to `PATH`.
3. **Bootstrap a project capsule.**
   ```bash
   agentcall init --template python ~/workspace/project
   ```
   All SDK artefacts live inside `project/agentcontrol/`; the host repository remains untouched.
   (Set `AGENTCONTROL_AUTO_INIT=1` if you prefer `agentcall status` to bootstrap automatically.)
4. **Authenticate agents.**
   ```bash
   cd ~/workspace/project
   agentcall agents auth
   agentcall agents status
   ```
   Credentials are stored beneath `~/.agentcontrol/state/`.
5. **Qualify the environment.**
   ```bash
   agentcall verify
   ```
   The pipeline runs formatting, tests, security checks, SBOM, architecture sync, Memory Heart, and emits `reports/verify.json`.

## 3.1 Automatic Updates
- `agentcall` checks PyPI for newer public releases on first invocation (default interval: 6h) and upgrades itself automatically before executing the command.
- Disable on air-gapped hosts via `AGENTCONTROL_DISABLE_AUTO_UPDATE=1` or `AGENTCONTROL_AUTO_UPDATE=0`.
- Choose the updater (`pip` default, `pipx` alternative) with `AGENTCONTROL_AUTO_UPDATE_MODE`.
- Provide an offline fallback by pointing `AGENTCONTROL_AUTO_UPDATE_CACHE` to a directory with cached wheels (e.g. `agentcontrol-<version>-py3-none-any.whl`); when PyPI is unreachable the newest cached version greater than the current install is applied and logged as a `fallback_*` telemetry event.
- For local development or testing you can bypass the dev-environment guard via `AGENTCONTROL_ALLOW_AUTO_UPDATE_IN_DEV=1` and simulate network failures with `AGENTCONTROL_FORCE_AUTO_UPDATE_FAILURE=1`.
- All update attempts are logged as telemetry events (`auto-update`) with mode, versions, and exit status; after a successful upgrade CLI exits so you can re-run the original command.

## 4. Command Portfolio
| Command | Purpose | Notes |
| --- | --- | --- |
| `agentcall status [PATH]` | Dashboard (auto-bootstrap optional). | Enable auto-bootstrap with `AGENTCONTROL_AUTO_INIT=1`; also honour `AGENTCONTROL_DEFAULT_TEMPLATE`, `AGENTCONTROL_DEFAULT_CHANNEL`. |
| `agentcall init / upgrade` | Template provisioning or migration. | Templates: `default`, `python`, `node`, `monorepo`. |
| `agentcall setup` | Install project dependencies and agent CLIs. | Respect `SKIP_AGENT_INSTALL`, `SKIP_HEART_SYNC`. |
| `agentcall verify` | Gold standard quality gate (fmt/lint/tests/coverage/security/docs/SBOM). | Options: `VERIFY_MODE`, `CHANGED_ONLY`, `JSON=1`. |
| `agentcall fix` | Execute safe autofixes from `config/commands.sh`. | Re-run `verify` afterwards. |
| `agentcall review` | Diff-focused review workflow with diff-cover support. | Options: `REVIEW_BASE_REF`, `REVIEW_SAVE`. |
| `agentcall ship` | Release gate (verify → release choreography). | Blocks on failing checks or open micro tasks. |
| `agentcall agents …` | Manage agent CLIs (`install`, `auth`, `status`, `logs`, `workflow`). | Configuration in `config/agents.json`. |
| `agentcall heart …` | Memory Heart lifecycle (`sync`, `query`, `serve`). | Settings in `config/heart.json`. |
| `agentcall templates` | List installed templates. | Supports channels such as `stable`, `nightly`. |
| `agentcall telemetry …` | Inspect or clear local telemetry. | Subcommands: `report`, `tail --limit`, `clear`. |
| `agentcall plugins …` | Manage plugins (`list`, `install`, `remove`, `info`). | Entry point: `agentcontrol.plugins`. |
| `agentcall cache …` | Manage offline auto-update cache. | `list`, `add <wheel>`, `download <version>`, `verify`. |

## 5. Capsule Templates
| Template | Use case | Highlights |
| --- | --- | --- |
| `default` | Full governance skeleton with architecture and documentation. | Turnkey `verify/fix/ship` scripts, Memory Heart integration. |
| `python` | Python backend with pytest. | Isolated virtualenv inside `agentcontrol/.venv`, sample tests included. |
| `node` | Node.js service with ESLint and `node --test`. | npm workflows encapsulated within the capsule. |
| `monorepo` | Python backend + Node front-end. | Coordinated pipelines across both packages. |

Custom templates live under `src/agentcontrol/templates/<version>/<name>`; update `template.json` accordingly.

## 6. Release Procedure
1. Update version metadata (`src/agentcontrol/__init__.py`, `pyproject.toml`) and changelog.
2. Build artefacts with `./scripts/release.sh` (wheel, sdist, SHA256, manifest).
3. Optional publication via `python -m twine upload dist/*`.
4. Offline install: distribute the `.whl` and `agentcontrol.sha256`, then run `pipx install --force <wheel>`.

## 7. Observability
- Telemetry is local, stored in `~/.agentcontrol/logs/telemetry.jsonl`. Disable with `AGENTCONTROL_TELEMETRY=0`.
- Memory Heart resides in `agentcontrol/state/heart/`; query using `agentcall heart query` or serve via `agentcall heart serve`.
- Key artefacts: `reports/verify.json`, `reports/status.json`, `reports/review.json`, `reports/doctor.json`.

## 8. Service Model
- Product owner: AgentControl Core team (see `AGENTS.md`).
- Operational coverage: 24/7, with programme-level SLA for agent responses.
- Escalation: raise tasks via `agentcall agents workflow --task=<ID>` or contact the listed owner directly.

## 9. FAQ
**Q:** How do I disable automatic bootstrap?
**A:** Export `AGENTCONTROL_NO_AUTO_INIT=1` before running `agentcall`.

**Q:** How do I add a custom pipeline?
**A:** Extend `agentcontrol/agentcall.yaml` and `config/commands.sh`. The command will appear in `agentcall commands`.

**Q:** Where is state stored?
**A:** Project-level artefacts live in `agentcontrol/state/`; global state (registry, credentials) lives under `~/.agentcontrol/state/`.

---
© AgentControl — Universal Agent SDK.
