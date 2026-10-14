# Spotify Product Priority Memo

## Recommendation

Prioritize **playback reliability** for the next product cycle. Playback has 8,683 complaint or cancellation-intent records [C0001], a cumulative severity of 30,985 [C0002], mean severity of 3.568467 [C0003], and the highest deterministic priority score, 30,985 [C0004]. The product response should focus on play-start failures, crash/stop loops, wrong-track substitution, and recovery after interrupted playback. Instrument these paths first, reproduce the highest-severity cases, then ship guarded fixes with rollback and before/after playback-success monitoring.

## Why Playback Ranks Above the Alternatives

**Usability** has the largest complaint/cancellation volume: 10,514 records [C0005], compared with playback's 8,683 [C0001]. However, its mean severity is substantially lower at 2.694217 [C0007], producing a cumulative severity and priority score of 28,327 [C0006][C0008]. Playback therefore leads usability by 2,658 severity-weighted points. This is why the recommendation is not based on raw complaint count alone. Usability should remain the secondary portfolio priority, especially where navigation friction contributes to playback failures.

**Access** has the highest mean severity, 3.931254 [C0023], but affects a narrower set of 1,731 records [C0021] and has a cumulative score of 6,805 [C0022][C0024]. Access failures warrant a targeted high-severity workstream, but the evidence does not support making them the broadest first investment.

**Billing** has 2,565 records [C0013], mean severity of 3.078363 [C0015], and a priority score of 7,896 [C0014][C0016]. These issues are consequential, but their combined burden is well below playback's. **Support** has 98 records [C0029], mean severity of 2.897959 [C0031], and a score of 284 [C0030][C0032]; it should be monitored and routed operationally rather than displacing the leading product priorities.

## Representative Playback Evidence

- `a6eee2f8-ce5b-4686-a1f4-2c90c159bdd2` — a severity-4 complaint describing crashes and playback stopping after one or two songs, requiring the listener to restart the playlist.
- `b3da207e-888d-40bd-bd5d-11f376f5eeda` — a severity-4 complaint in which requesting a favorite song results in a different track playing.
- `17f29b88-fc31-4e9f-b9ca-44cf26120617` — a severity-4 complaint reporting that selecting one song leads to several other songs and that skipping is unavailable.

All three records were classified as `playback` complaints and flagged `needs_review`; they are traceable by review ID in `records.jsonl.gz` and should be human-checked before being used as verbatim research evidence.

## Limitations

- The reviews are self-selected historical app-store feedback, not a representative sample of all Spotify listeners. The ranking describes this review corpus and does not establish causal impact.
- The submitted analysis covers the first 100,100 source rows, not the complete 660,622-row file. Results may shift if the remaining rows have a different topic or severity distribution.
- 22,365 of 100,100 scoped rows (22.34%) were flagged `needs_review`. Those ambiguous or high-risk classifications should be sampled and adjudicated before committing major product resources.
- A `cancellation` label captures expressed cancellation intent in review text; it is not evidence of observed subscription churn.
- The deterministic score measures cumulative complaint severity. It does not include engineering effort, revenue impact, customer lifetime value, or strategic dependencies, so those factors still belong in the final roadmap decision.

## Decision

Fund playback reliability as the primary product initiative, retain usability as the next broad improvement area, and run a smaller targeted access stream because of its unusually high mean severity. Validate the decision with human review of flagged records and with product telemetry for play-start success, unexpected stops, wrong-track events, and post-fix retention before expanding the intervention.
