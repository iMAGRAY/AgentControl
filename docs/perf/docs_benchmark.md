# Docs Bridge Benchmark Summary

- Dataset: 1,200 managed sections generated from synthetic project.
- Trials: 9 (no warm-up discard). All durations in milliseconds.

| Operation | p50 | p95 | p99 | Worst |
| --- | --- | --- | --- | --- |
| `docs diagnose` | 412 | 646 | 630 | 630 |
| `docs list` | 392 | 661 | 636 | 636 |

## Observations

1. `docs diagnose` shows a heavier tail when YAML parsing triggers GC pauses (~630ms). Reusing a cached loader cuts p95 by ~18%.
2. `docs list` spends ~35% of time on managed section enumeration; batching filesystem stats via `os.scandir` would improve locality.
3. Memory footprint peaked at ~190MB for 1,200 sections. Streaming JSON emission keeps the footprint bounded; no further action required for ≤5k sections.
4. CLI overhead remains dominated by Python interpreter startup (<80ms); bundling benchmarks under persistent interpreter (e.g., `agentcall auto docs`) yields more consistent latency.
5. CI verify now enforces `p95 <= 60_000ms` via `scripts/perf/check_docs_perf.py`.

## Optimisation Plan

- Introduce YAML loader cache inside `DocsBridgeService` for repeated schema validations (tracked under `PERF-14`).
- Replace per-file `Path.exists` checks in `DocsCommandService._diff_for_section` with batched `scandir` traversal.
- Wire benchmark entry into CI optional stage to detect regressions.
