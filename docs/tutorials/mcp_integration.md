# Tutorial: Wire MCP Servers into AgentControl

This recipe teaches an autonomous agent how to register and manage Model Context Protocol (MCP) servers so that mission control can surface tool availability instantly.

## Step 1 — Describe the Server
Decide on the identifier and endpoint. Example configuration:
- Name: `design-system`
- Endpoint: `https://mcp.example.com/design`
- Metadata: `tier=prod`, `owner=design-system`

## Step 2 — Register via CLI
```bash
agentcall mcp add --name design-system \
  --endpoint https://mcp.example.com/design \
  --description "Design system knowledge base" \
  --meta tier=prod --meta owner=design-system --json
```
The command drops a YAML file under `.agentcontrol/config/mcp/design-system.yaml` and emits a JSON payload for logging.

## Step 3 — Verify Registry State
```bash
agentcall mcp status --json
```
Typical response:
```json
{
  "servers": [
    {
      "name": "design-system",
      "endpoint": "https://mcp.example.com/design",
      "description": "Design system knowledge base",
      "metadata": {
        "owner": "design-system",
        "tier": "prod"
      }
    }
  ]
}
```

## Step 4 — Surface in Mission Control
Run `agentcall mission summary --filter mcp`. The dashboard now prints the server list and flags missing registrations with the `mcp_servers_missing` playbook.

## Step 5 — Automate Lifecycle
- Use `agentcall mcp remove --name design-system --json` when a server retires.
- Orchestrate registrations by storing server definitions in source control and running the `mcp add` command during project bootstrap scripts.

## Step 6 — Integrate with MCP Clients
Agents can pass `.agentcontrol/config/mcp/*.yaml` directly to MCP-compatible runtimes. Each file follows a minimal schema:
```yaml
name: design-system
endpoint: https://mcp.example.com/design
description: Design system knowledge base
metadata:
  tier: prod
  owner: design-system
```

> **Tip:** In playground scenarios, generate a disposable workspace via `agentcall sandbox start --template sandbox` and experiment with MCP registrations without touching production capsules.
