# Tutorial: Nightly Documentation Performance Guard

Nightly benchmarks ensure that managed documentation operations (`agentcall docs …`) stay within the 60 s p95 budget on large projects.

## 1. Configure History Storage
- Benchmarks write to `reports/perf/docs_benchmark.json` (already part of `agentcall verify`).
- Historical diffs live under `reports/perf/history/` as defined in `scripts/perf/compare_history.py`.
- Set the following environment variables when the history should be updated:
  - `PERF_HISTORY_UPDATE=1`
  - `PERF_HISTORY_KEEP=<N>` (optional, default 30 entries)
  - `PERF_HISTORY_MAX_PCT=<pct>` / `PERF_HISTORY_MAX_MS=<ms>` for regression guards.

## 2. GitHub Actions Template
Create `.github/workflows/perf-nightly.yaml` in the target project:

```yaml
name: Perf Nightly

on:
  schedule:
    - cron: '0 3 * * *'
  workflow_dispatch: {}

jobs:
  docs-perf:
    runs-on: ubuntu-latest
    timeout-minutes: 45
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install AgentControl dependencies
        run: |
          python -m venv .venv
          . .venv/bin/activate
          pip install --upgrade pip
          pip install -r requirements.txt
      - name: Run documentation benchmarks
        env:
          PERF_HISTORY_UPDATE: "1"
          PERF_HISTORY_KEEP: "60"
          PERF_HISTORY_MAX_PCT: "12"
          PERF_HISTORY_MAX_MS: "2500"
        run: |
          . .venv/bin/activate
          agentcall verify --json
      - name: Upload perf history
        uses: actions/upload-artifact@v4
        with:
          name: docs-perf-history
          path: reports/perf/history
```

The job:
1. Executes `agentcall verify` (which triggers `scripts/perf/docs_benchmark.py` and `check_docs_perf.py`).
2. Invokes `scripts/perf/compare_history.py` via the new `perf-history` verify step.
3. Updates history (`PERF_HISTORY_UPDATE=1`) and fails if regressions exceed thresholds.

## 3. Local Nightly Runner
For environments without GitHub Actions, schedule the command below via cron/systemd:

```bash
PERF_HISTORY_UPDATE=1 PERF_HISTORY_KEEP=30 \
PERF_HISTORY_MAX_PCT=12 PERF_HISTORY_MAX_MS=2500 \
agentcall verify --json
```

Store the resulting `reports/perf/history/diff.json` artefact to surface regressions in mission control or dashboards.

## 4. Surfacing Results to Agents
- Mission palette now records `reports/perf/history/diff.json` under `mission_palette.json` allowing automations to fetch the latest regression report.
- Add a mission timeline event (`perf.regression`) when `perf-history` fails; automation recipes can respond by opening an incident or triggering `agentcall docs sync` across affected sections.

## 5. Checklist
- [ ] Workflow committed and scheduled.
- [ ] History artefacts retained (≥30 runs recommended).
- [ ] Mission dashboard surfaces perf status (see `mission summary --filter quality`).
- [ ] Regression thresholds align with AC::PERF-2 (`≤60 s` for 1000 sections).
