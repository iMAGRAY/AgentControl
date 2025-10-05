# Sandbox Playground Example

Spin up a disposable workspace that mirrors the default AgentControl capsule while keeping the host project clean.

## Workflow
1. `agentcall sandbox start --template sandbox --json` — capture the `sandbox_id` and `workspace` path.
2. `cd <workspace>` and run `agentcall mission summary` to view the seeded twin.
3. Experiment freely (add docs, register MCP servers). When done, run:
   ```bash
   agentcall sandbox purge --id <sandbox_id>
   ```

## Files Included
- `.agentcontrol/` — minimal capsule with docs bridge config and automation commands.
- `docs/bench/` — sample managed sections seeded for experimentation.
- `README.md` — this file.

Automated agents can parse the JSON payload from step 1 to mount the workspace inside containerised runners.
