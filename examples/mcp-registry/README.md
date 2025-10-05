# MCP Registry Sample

This example shows how to predefine MCP server registrations so a project capsule starts with tool integrations in place.

## Structure
```
examples/mcp-registry/
├── .agentcontrol/
│   └── config/
│       └── mcp/
│           ├── design-system.yaml
│           └── incident-wiki.yaml
└── README.md
```

## Usage
1. Copy the `.agentcontrol/config/mcp` directory into your project capsule.
2. Run `agentcall mcp status` to confirm both servers are registered.
3. Use `agentcall mission summary --filter mcp` to verify the mission dashboard surfaces the registry.

Agents can template the YAML files to inject environment-specific endpoints automatically.
