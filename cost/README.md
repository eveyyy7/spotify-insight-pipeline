# Offline cost and runtime calculator

This folder is self-contained evidence for the required 100-review pilot. The
calculator reads only `usage.csv` and `rates.csv`; it does not load `.env`, use
an API key, or make a network request.

Run the replay from the project root:

```sh
python3 cost/calculator.py
```

## Saved evidence

- `pilot_records.jsonl`: 100 completed records corresponding to the fixed
  `cost_100.csv` input (SHA-256
  `c884ac3b9be5066995d5063f96ad9af6e5e082975788c1684c4f6b6ea661dd0e`).
- `pilot_calls.jsonl`: 178 real successful cold-run calls: 100 enrich, 24
  verify, 53 group, and one memo call. Each row preserves role, exact model,
  configuration, usage, and request duration.
- `usage.csv`: independently summarized units and timings. The original cold
  orchestrator did not save one trustworthy end-to-end stopwatch value, so its
  original cell remains blank. A fresh empty-state reproducibility run is saved
  as `cold_recheck_100`: 174 successful calls, 21.94 seconds end to end, and
  $0.0073 at the saved rate. The saved warm replay took 0.79 seconds with zero
  incremental API calls.
- `rates.csv`: editable dated rates in per-token units. Output tokens were
  billed at zero in the measured Jev configuration; changing either rate
  changes the replayed subtotal without changing recorded usage.
- `final_usage.csv`: actual role-level attempts, outcomes, tokens, summed
  request time, and wall-clock measurements for the submitted 100,100-row run.
- `report.md`: interpretation, controls, assumptions, and scale estimate.

## Cold versus warm

The cold run began with an empty result cache and completed 100/100 inputs with
zero failed final records. The warm replay used the same input and unchanged
label configuration; it returned all 100 records from saved state with zero
new enrichment calls and $0 incremental API spend. Downstream pilot artifacts
were also reused during the saved warm replay. The October 14 cold recheck also
proved the fresh-run packaging path after an empty `checkpoint_before.json`
fix: before count 0, after count 100, complete grading export produced.

## Safety controls

The production runner uses a persistent SQLite queue, atomic `pending` →
`in_flight` claims, direct-original exact-text cache provenance, two workers,
a shared request/token limiter, bounded transient and malformed-output retries,
exponential backoff with jitter, and a shared spend ledger that reserves the
worst-case amount before dispatch. `test_parallel_pipeline.py` and
`test_system_pipeline.py` exercise these controls without external calls.

