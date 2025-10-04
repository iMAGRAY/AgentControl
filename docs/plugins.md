# AgentControl Plugin Guide

## Overview
- Entry point group: `agentcontrol.plugins`.
- Contract: expose `register(registrar, context)`.
- Use `registrar.add_subparser(name, help_text, builder)` to add top-level `agentcall` commands.
- The builder receives `(argparse_parser, PluginContext)` and must return a handler accepting `argparse.Namespace`.

## Minimal Example
Reference implementation: `examples/plugins/agentcontrol-hello-plugin`
```python
from agentcontrol.plugins import PluginRegistrar, PluginContext

def register(registrar: PluginRegistrar, context: PluginContext) -> None:
    def builder(parser, ctx):
        parser.add_argument("--name", default="Agent")
        def handler(args):
            print(f"Hello, {args.name}!")
            return 0
        return handler
    registrar.add_subparser("hello-plugin", "Greets the caller", builder)
```

## Usage Flow
```bash
pip install -e examples/plugins/agentcontrol-hello-plugin
agentcall plugins list
agentcall hello-plugin --name Agent
```

## Best Practices
- Keep commands idempotent; clearly document side effects.
- Emit telemetry via `record_event` when observability matters.
- Read configuration from `AGENTCONTROL_<PLUGIN>` environment variables.
- Provide automated tests and concise README documentation with every plugin.
