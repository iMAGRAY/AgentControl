# Tutorial: Building Project Extensions

AgentControl extensions let agents package custom playbooks, automation hooks, and MCP connectors without touching the core capsule. Every extension lives under `extensions/<name>` and is catalogued for discovery.

## 1. Scaffold a New Extension
```bash
agentcall extension init auto_docs
```
The command creates:
```
extensions/auto_docs/
  manifest.json
  README.md
  playbooks/
  hooks/
  mcp/
```
`manifest.json` includes metadata and compatibility requirements. Update the description and register playbooks/hooks as they are added.

## 2. Register Existing Extensions
If you clone or pull an extension directory, register it in the catalog:
```bash
agentcall extension add auto_docs
```
Use `agentcall extension list` to view registered extensions. Add `--json` for machine output.

## 3. Lint and Publish
Validate manifests against the official schema at any time:
```bash
agentcall extension lint --json
```
The lint command applies `extension_manifest.schema.json`, so missing compatibility ranges or malformed entry points are flagged immediately. Export the catalog for sharing or automation:
```bash
agentcall extension publish --dry-run --json
```
The export generates `reports/extensions.json` with the extension metadata, including source hints and versions. Omit `--dry-run` to mark a production publish.

## 4. Directory Conventions
- `playbooks/`: declarative recipes (`*.yaml`) callable via `agentcall mission exec` or automation watch.
- `hooks/`: executable scripts (`*.sh`, `*.py`) referenced from `manifest.json`.
- `mcp/`: connector descriptors (`*.json`) for MCP servers.

Keep manifests concise (≤4 KB) so agents can ingest them quickly.

## 5. Cleanup
Remove an extension from the catalog:
```bash
agentcall extension remove auto_docs
```
The directory remains for auditing; delete manually if desired.

See `examples/extensions/` for ready-to-use reference implementations (SHA256-protected).
