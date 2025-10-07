# Tutorial: Automation Hooks with `SDK_VERIFY_COMMANDS`

AgentControl lets you extend `agentcall verify` and other pipelines without touching the system scripts. Set the environment variable `SDK_VERIFY_COMMANDS` with the commands you want to run.

## Quick Start
1. Create a script for the desired check, for example a local linter:
   ```bash
   cat > scripts/custom/lint.sh <<'SH'
   #!/usr/bin/env bash
   set -Eeuo pipefail
   poetry run ruff check .
   SH
   chmod +x scripts/custom/lint.sh
   ```
2. Run verify with `SDK_VERIFY_COMMANDS` defined:
   ```bash
   SDK_VERIFY_COMMANDS=("scripts/custom/lint.sh") agentcall verify
   ```
   Each command executes at the end of the pipeline and appears in `reports/verify.json`.

## JSON-Friendly Mode
All commands run in the project context. When agents need structured output, add `--json` or serialise manually—the verify step records the log tail and exit status.

## Composite Pipelines
Provide multiple commands when needed:
```bash
SDK_VERIFY_COMMANDS=(
  "agentcall docs sync --json"
  "pytest --maxfail=1 --disable-warnings"
) agentcall verify --json
```
Commands execute sequentially. Failures are recorded with `status=fail`, but the main verify continues unless `EXIT_ON_FAIL=1` is set.

## CI Automation
In CI, export the variable in the verify step:
```yaml
env:
  SDK_VERIFY_COMMANDS: |
    agentcall docs sync --json
    pytest --maxfail=1
run: agentcall verify --json
```
Use `SDK_VERIFY_COMMANDS+=(...)` in shell scripts when multiple modules need to append entries.

> **Tip:** store the shared list in `.agentcontrol/config/automation.sh` and source the file in CI so every agent mounts the same commands automatically.

## Managed Automation Hooks
- Every project initialised by the SDK includes `.agentcontrol/config/automation.sh`.
- The script is sourced during `sdk::load_commands` and appends three defaults:
  1. `agentcall docs diff --json` → `reports/automation/docs-diff.json`.
  2. `agentcall mission summary --json --timeline-limit 20` → `reports/automation/mission-summary.json`.
  3. `agentcall mcp status --json` → `reports/automation/mcp-status.json` (tolerant to missing MCP servers, exits with `|| true`).
- Use helpers such as `sdk::ensure_array_value` to add or replace commands without duplicates.

> The automation script is idempotent: successive calls to `sdk::load_commands` do not duplicate entries in `SDK_VERIFY_COMMANDS`, and `reports/automation` is created automatically.
