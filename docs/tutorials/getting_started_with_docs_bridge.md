# Tutorial: Adopt Existing Documentation with the Docs Bridge

This guide walks an autonomous agent through the zero-friction path of attaching AgentControl to a legacy documentation tree without duplicating files.

## Prerequisites
- An existing project with Markdown documentation under `docs/`.
- AgentControl SDK 0.3.2 or later installed.
- The project initialised with `.agentcontrol/` (run `agentcall init` if missing).

## Step 1 — Inspect Current Layout
1. Run `agentcall docs diagnose --json` to confirm configuration health.
2. Review the emitted `issues` array. Each entry includes a `code`, `message`, and `remediation` key so the agent can branch programmatically.

## Step 2 — Map Managed Sections
Create or update `.agentcontrol/config/docs.bridge.yaml` with anchors that point to existing files:
```yaml
sections:
  release_notes:
    mode: managed
    target: docs/release-notes.md
    marker: agentcontrol-release-notes
    insert_after_heading: '# Release Notes'
```
The bridge never copies files; it only crafts managed regions inside real docs.

## Step 3 — Dry-Run Adoption
Execute:
```bash
agentcall docs diff --section release_notes --json
```
The diff payload shows whether the managed block already matches AgentControl’s expectations. No mutations occur in this step.

> **Shortcut:** `agentcall docs sync --section release_notes` выполняет diff → repair/adopt за один шаг и вернёт JSON/summary с оставшимися расхождениями.

## Step 4 — Adopt Baseline
If the diff reports `status: drift`, adopt the current content as ground truth:
```bash
agentcall docs adopt --section release_notes --json
```
The command snapshot is saved under `.agentcontrol/state/docs/state.json` for rollback.

## Step 5 — Enforce via Automation Recipe
Agents can embed the adoption into CI using the automation recipe:
```bash
agentcall auto docs --apply --section release_notes
```
The recipe automatically:
1. Runs `docs diff`.
2. Repairs the managed block when drift is detected.
3. Generates a machine-consumable report for telemetry.

## Step 6 — Verify Mission Status
Finish by refreshing the mission twin:
```bash
agentcall mission summary --filter docs
```
The docs section status flips to `ok` and the playbook for `docs_drift` disappears.

> **Next:** Explore the [Mission Control walkthrough](./mission_control_walkthrough.md) to automate roadmap decisions.
