# AgentControl Universal Agent SDK — Python Capsule

This template provisions the AgentControl SDK capsule for Python services. All SDK artefacts live inside `agentcontrol/`, while the host repository remains untouched.

## Quick Start
1. Install global prerequisites and the AgentControl CLI (see top-level README).
2. Initialise the capsule:
   ```bash
   agentcall status /path/to/project   # auto-bootstrap default@stable
   agentcall init --template python /path/to/project
   ```
3. Create and seed the local virtualenv within the capsule:
   ```bash
   cd /path/to/project
   agentcall setup
   ```
4. Run the verification pipeline:
   ```bash
   agentcall verify
   ```

## Python specifics
- Virtual environment resides in `agentcontrol/.venv`.
- Dependencies are pinned via `agentcontrol/requirements.txt` and `requirements.lock`.
- `SDK_VERIFY_COMMANDS` executes pytest; exit code 5 (no tests collected) is treated as success.

Refer to the root documentation for the full command surface, governance model, and operations charter.
