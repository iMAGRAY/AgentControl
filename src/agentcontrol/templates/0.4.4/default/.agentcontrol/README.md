# AgentControl Universal Agent SDK

AgentControl is an enterprise-grade toolkit that standardises how autonomous engineers and human teams operate on any codebase. The SDK provisions a consistent command surface, deterministic governance assets, and ready-to-use agent runtimes, so delivery begins immediately without bespoke project bootstrapping.

## 1. Value Proposition
- **Single operational entrypoint.** The `agentcall` CLI aligns humans and agents on the same verified pipelines (`init`, `verify`, `ship`, `status`, and more).
- **Integrated governance.** Roadmaps, task boards, and architecture manifests remain in sync through automated status and progress commands.
- **Agent-first runtime.** Codex/Claude CLIs, supporting scripts install without manual steps, keeping cognitive load low for automated contributors.
- **Compliance by default.** Lockfiles, SBOM generation, audit artefacts, and release gates are embedded into the workflow.

## 2. Solution Architecture
| Layer | Responsibility | Key artefacts |
| --- | --- | --- |
| **CLI & Pipelines** | Lifecycle orchestration (`init`, `verify`, `ship`, `status`). | `src/agentcontrol/cli`, `src/agentcontrol/app` |
| **Domain & Governance** | Capsule, template, and command models with explicit invariants. | `src/agentcontrol/domain`, `src/agentcontrol/ports` |
| **Templates** | Project capsules (`default`, `python`, `node`, `monorepo`) fully contained inside `./agentcontrol/`. | `src/agentcontrol/templates/<version>/<template>` |
| **Plugin framework** | Extensible CLI via the `agentcontrol.plugins` entry point group. | `src/agentcontrol/plugins`, `examples/plugins/` |
| **Observability** | Telemetry, mission control, status artefacts. | `src/agentcontrol/utils/telemetry`, `reports/` |

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
   agentcall status ~/workspace/project        # auto-initialises default@stable
   # or explicitly
   agentcall init --template python ~/workspace/project
   ```
   All SDK artefacts live inside `project/agentcontrol/`; the host repository remains untouched.
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
   The pipeline runs formatting, tests, security checks, SBOM, architecture sync, mission control, and emits `reports/verify.json`.

## 4. Command Portfolio
| Command | Purpose | Notes |
| --- | --- | --- |
| `agentcall status [PATH]` | Dashboard plus capsule auto-bootstrap. | Controlled via `AGENTCONTROL_DEFAULT_TEMPLATE`, `AGENTCONTROL_DEFAULT_CHANNEL`, `AGENTCONTROL_NO_AUTO_INIT`. |
| `agentcall init / upgrade` | Template provisioning or migration. | Templates: `default`, `python`, `node`, `monorepo`. |
| `agentcall setup` | Install project dependencies and agent CLIs. | Respect `SKIP_AGENT_INSTALL`, `SKIP_HEART_SYNC`. |
| `agentcall verify` | Gold standard quality gate (fmt/lint/tests/coverage/security/docs/SBOM). | Options: `VERIFY_MODE`, `CHANGED_ONLY`, `JSON=1`. |
| `agentcall fix` | Execute safe autofixes from `config/commands.sh`. | Re-run `verify` afterwards. |
| `agentcall review` | Diff-focused review workflow with diff-cover support. | Options: `REVIEW_BASE_REF`, `REVIEW_SAVE`. |
| `agentcall ship` | Release gate (verify → release choreography). | Blocks on failing checks or open micro tasks. |
| `agentcall agents …` | Manage agent CLIs (`install`, `auth`, `status`, `logs`, `workflow`). | Configuration in `config/agents.json`. |
| `agentcall templates` | List installed templates. | Supports channels such as `stable`, `nightly`. |
| `agentcall telemetry …` | Inspect or clear local telemetry. | Subcommands: `report`, `tail --limit`, `clear`. |
| `agentcall plugins …` | Manage plugins (`list`, `install`, `remove`, `info`). | Entry point: `agentcontrol.plugins`. |

## 5. Capsule Templates
| Template | Use case | Highlights |
| --- | --- | --- |
| `default` | Full governance skeleton with architecture and documentation. | Turnkey `verify/fix/ship` scripts, mission control integration. |
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
- Mission control dashboard provides operational snapshots via `agentcall mission` (coming soon).
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
