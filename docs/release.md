# AgentControl Release Playbook

1. **Pre-flight checks**
   ```bash
   .venv/bin/python -m pytest
   ```
   Ensure a clean working tree and a fully green test suite.
2. **Version bump**: update `src/agentcontrol/__init__.py`, `pyproject.toml`, and add a changelog entry.
3. **Build artefacts**
   ```bash
   ./scripts/release.sh
   ```
   Produces wheel + sdist in `dist/`, generates `agentcontrol.sha256`, and writes `release-manifest.json`.
4. **Changelog tooling (optional)**
   ```bash
   ./scripts/changelog.py "Short summary"
   git add docs/changes.md
   ```
5. **Publish to PyPI (optional)**
   ```bash
   python -m twine upload dist/*
   ```
6. **Tag and push**
   ```bash
   git tag -s vX.Y.Z -m "agentcontrol vX.Y.Z"
   git push origin main --tags
   ```
7. **Communications**: refresh README quick-start and circulate release notes.
8. **Post-release validation**
   ```bash
   pipx install agentcontrol==X.Y.Z
   agentcall init ~/tmp/demo
   agentcall verify
   ```
   Capture results in `reports/release-validation.json` if required.
