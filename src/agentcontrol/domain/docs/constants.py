"""Constants for the documentation bridge domain."""

from __future__ import annotations

ERROR_REMEDIATIONS = {
    "DOC_BRIDGE_INVALID_CONFIG": "Update .agentcontrol/config/docs.bridge.yaml to match schema and required sections.",
    "DOC_ROOT_MISSING": "Create the documentation root or adjust 'root' in docs.bridge.yaml.",
    "DOC_SECTION_MISSING_FILE": "Generate or restore the referenced documentation file before running sync.",
    "DOC_SECTION_MISSING_MARKER": "Ensure managed markers wrap the section or rerun agentcall docs repair (when available).",
    "DOC_SECTION_MISSING_DIRECTORY": "Create the expected directory or adjust target_template for this section.",
    "DOC_SECTION_MARKER_CORRUPTED": "Restore the managed marker pair or regenerate the section via agentcall docs repair.",
    "DOC_BRIDGE_STATUS_FAILURE": "Retry `agentcall docs diagnose --json` and inspect CLI logs.",
    "DOCS_PORTAL_MANIFEST_MISSING": "Generate architecture/manifest.yaml (or .agentcontrol equivalent) before running docs portal.",
    "DOCS_PORTAL_SIZE_BUDGET_EXCEEDED": "Increase --budget or reduce generated assets before regenerating the portal.",
    "DOCS_PORTAL_OUTPUT_NOT_EMPTY": "Pass an empty output directory or rerun with --force to overwrite existing files.",
}


def remediation_for(code: str) -> str | None:
    """Return default remediation text for a given error code."""

    return ERROR_REMEDIATIONS.get(code)
