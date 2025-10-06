# AgentControl Universal Agent SDK — Node.js Capsule

This template bundles the AgentControl SDK capsule for Node.js projects. The SDK infrastructure is contained within `agentcontrol/`, while the rest of the repository remains untouched.

## Quick Start
1. Install global prerequisites and `agentcall` (see the top-level README).
2. Bootstrap the capsule:
   ```bash
   agentcall status /path/to/project
   agentcall init --template node /path/to/project
   ```
3. Install dependencies and prepare the workspace:
   ```bash
   cd /path/to/project
   agentcall setup
   ```
4. Execute the verification pipeline:
   ```bash
   agentcall verify
   ```

## Node.js specifics
- Commands operate from `agentcontrol/` and rely on npm scripts.
- Verification runs `npm install`, `npm run lint`, and `npm test`.
- Fix pipeline applies `npm run lint -- --fix`.
- Release pipeline runs `npm run build` (customise as required).

Refer to the root documentation for the full command reference and operational policies.
