# AgentControl Bootstrap Checklist

## 1. Purpose
This guide accelerates the first 15 minutes on a new repository: capture the delivery profile, validate the runtime, and point agents toward the next checkpoints. Run it whenever a project template is refreshed or a new team onboards.

## 2. Prerequisites
- Python interpreter meeting the profile minimum (Python ≥ 3.10 for the Python capsule).
- `agentcall` CLI 0.5.1 или новее (установите один раз: `pipx install agentcontrol`).
- В проекте уже выполнен `agentcall quickstart` (капсула лежит под `./.agentcontrol/`).

Verify the CLI version:
```bash
agentcall --version
```

## 3. Run the Bootstrap Wizard
Launch the wizard from the project root:
```bash
agentcall bootstrap
```
Key actions:
1. Select a default profile (Python Service, Polyglot Monorepo, or Meta-Workspace).
2. Answer six onboarding prompts covering stack, CI/CD, MCP usage, repository scale, automation focus, and constraints.
3. Review the generated artefacts:
   - `.agentcontrol/state/profile.json`
   - `reports/bootstrap_summary.json`

Use non-interactive capture when the profile id is known:
```bash
agentcall bootstrap --profile python
```
Add `--json` for machine-readable output (suitable for automation transcripts).

## 4. Validate Environment Readiness
Run the targeted doctor mode to confirm runtime and MCP connectivity:
```bash
agentcall doctor --bootstrap
```
The command checks Python version, packaged profile drift, and MCP server availability. For pipeline consumption:
```bash
agentcall doctor --bootstrap --json > reports/bootstrap_doctor.json
```

## 5. Typical Follow-Ups
- Register MCP servers if the profile requires them:
  ```bash
  agentcall mcp add --name staging --endpoint https://mcp.example.com
  ```
- Sync documentation markers after capturing the profile:
  ```bash
  agentcall docs diagnose --json
  ```
- Commit the refreshed artefacts (`profile.json`, `bootstrap_summary.json`, and any MCP configs).

## 6. Troubleshooting
| Symptom | Action |
| --- | --- |
| `Bootstrap profile missing` | Ensure the project was initialised and rerun `agentcall bootstrap`. |
| `Python version below required` | Upgrade the interpreter or adjust the default profile before agents run verify pipelines. |
| `MCP expected but no servers configured` | Populate `.agentcontrol/config/mcp/*.json` via `agentcall mcp add` or disable MCP usage in the wizard if not needed. |

## 7. Next Checkpoints
- Finish onboarding by running `agentcall verify` (ensures diff coverage, SBOM, docs sync).
- Schedule `agentcall telemetry report --recent 50` to confirm no bootstrap warnings remain.
- Document tenant-specific nuances in `docs/tutorials/` and link them from `reports/bootstrap_summary.json` metadata if required.
