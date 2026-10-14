# Cost and runtime report

Date: 2026-10-13 (America/Los_Angeles)

## Final 100,100-review run

The declared submission scope contains **100,100 original rows**: 100,099
completed classifications and one empty-text quarantine. Exact-text reuse
served 24,137 completed rows from direct saved originals. The complete call log
contains 76,231 attempts across all roles: 75,980 enrich, 50 verify, 200 group,
and one memo call. There were 76,213 successful attempts and 18 retained failed
attempts; every scoped source ID is nevertheless resolved in the final export.

Recorded usage was **71,507,762 input tokens** and **15,012,594 output tokens**.
At the saved rate of $0.000000042 per input token and $0 per output token, the
measured API cost is **$3.0033 total**, or **$2.9993 per 100,000 input rows**.
This is below the course budget of $10 per 100,000 rows. The persistent ledger's
$7.5967 figure is deliberately conservative reservation accounting, not the
provider-rate reconstruction.

The main enrichment phase ran from 2026-10-13 23:30:37 PDT to 2026-10-14
03:45:30 PDT, about **4 hours 15 minutes**. Verification, grouping, ranking,
memo generation, packaging, and the final checker completed by about 04:04 PDT.
The exact role totals are preserved in `final_usage.csv`; `calls.jsonl.gz` in
the grading package is the record-level source of truth.

## Measured 100-review pilot

The fixed 100-row input produced 100 completed and 0 failed records. The cold
run made 178 successful calls: 100 enrich, 24 independent verification, 53
issue-grouping, and one memo selection. Recorded usage was 177,874 input tokens
and 45,148 output tokens. At the editable rates in `rates.csv`, measured API
spend was **$0.0075**. This is **$0.075 per 1,000 input rows** and **$0.000075 per
completed record**. Local compute and infrastructure cost were not separately
metered and remain unknown, not zero.

The provider-call durations sum to 25.602 seconds. This is not represented as
end-to-end wall time because the original cold orchestrator did not preserve a
trustworthy stopwatch measurement. The warm replay was measured end to end at
0.79 seconds, with 100 cache hits, zero new enrichment calls, and **$0.0000**
incremental API spend.

On 2026-10-14, the same fixed 100-row input was rerun from a genuinely empty
state with one worker to close the wall-clock evidence gap. The complete
enrich → verify → group → rank → memo → package → check workflow took **21.94
seconds**, made 174 successful calls with no failed attempts, used 174,829
input and 44,427 output tokens, and cost **$0.0073** at the saved rate. Its
checkpoint counts were 0 before and 100 after. The separate saved warm replay
remains 0.79 seconds and zero incremental calls.

Configuration: Jev `jev-latest` (provider responses recorded model version
`jev-1.13.0`), prompt/schema v1, one review per provider request, one worker for
the measured cold pilot, no reasoning tier exposed by the provider, and one
bounded retry in the pilot implementation. Provider batching remained one
because an earlier multi-state experiment returned one aggregate response
rather than one validated response per review.

## Full-run estimate

The input contains 660,622 rows: 660,609 nonempty reviews to classify and 13
empty texts to quarantine. There are 484,189 distinct nonempty review texts.
Using exact-text reuse, measured per-stage token rates, the 24% pilot
verification rate, the 53% pilot grouping rate, and one fixed memo call, the
base estimate is **$42.0892 total / $6.3711 per 100k rows**. A conservative
scenario with 5% additional retry work, 30% verification, and 60% grouping is
**$48.0465 total / $7.2729 per 100k rows**. Both are below the declared $10 per
100k limit. Without exact-text enrichment reuse, the modeled total is $49.0290.

The final baseline membership/ranking can be computed deterministically from
saved enriched topics, avoiding unnecessary grouping calls; the estimates above
retain the measured pilot grouping rate so they do not understate the originally
tested architecture. The actual submitted-scope usage is reconciled above; the
full-corpus figures remain an optional scale projection rather than a claim of
660,622-row execution.

## Throughput and concurrency

The deterministic same-slice benchmark used identical reviews and empty-cache
conditions. One worker took 1.496 seconds and two workers took 0.817 seconds
(1.83× speedup), with identical outputs, eight calls in each case, zero
duplicate successful calls, and no leaked reservations. Production concurrency
is capped at two workers. Request/token limits are shared across workers.

Elapsed-time projections remain conditional on provider rate limits. Summed
request time is not wall time, and a short pilot cannot establish sustained
throughput. The full run therefore records real wall time and queue progress
rather than treating the benchmark speedup as a guarantee.

## Budget, caps, and fallbacks

- Declared budget: $10 per 100,000 input rows.
- Production maximum concurrency: 2.
- Enrichment output is bounded by a four-question fixed schema; every response
  is validated before commit.
- Transient retries: 2; malformed-output retries: 1; exponential backoff plus
  jitter.
- Automatic expensive-model fallback fraction: 0%. No stronger fallback is
  invoked automatically.
- Spend control: atomic in-flight reservation against a shared persistent cap.
- Crash recovery: uncertain in-flight work requires the explicit
  `--recover-in-flight` flag because a timed-out request may still be billed.

## Rate caveat

`rates.csv` records the rate used for this pilot and the source checked on the
run date. Provider invoices or account dashboards remain the authoritative
billing record. Missing billing detail is disclosed rather than inferred from
subscription access.

