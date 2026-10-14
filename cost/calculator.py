import csv
from pathlib import Path


COST_DIR = Path(__file__).resolve().parent

USAGE_FILE = COST_DIR / "usage.csv"
RATES_FILE = COST_DIR / "rates.csv"

FULL_ROWS = 660_622
NONEMPTY_ROWS = 660_609
EMPTY_ROWS = 13
DISTINCT_NONEMPTY_TEXTS = 484_189

# Measured pilot selection rates.
VERIFY_RATE = 24 / 100
GROUP_RATE = 53 / 100

# Conservative scenario assumptions.
CONSERVATIVE_VERIFY_RATE = 0.30
CONSERVATIVE_GROUP_RATE = 0.60
CONSERVATIVE_RETRY_MULTIPLIER = 1.05

BUDGET_PER_100K_USD = 10.00


def load_usage():
    rows = []

    with USAGE_FILE.open(
        newline="",
        encoding="utf-8",
    ) as f:
        for row in csv.DictReader(f):
            rows.append(row)

    return rows


def load_rates():
    rates = {}

    with RATES_FILE.open(
        newline="",
        encoding="utf-8",
    ) as f:
        for row in csv.DictReader(f):
            rates[row["billing_item"]] = float(
                row["price_per_unit"]
            )

    return rates


def measured_stage_rows(usage):
    return {
        row["role"]: row
        for row in usage
        if (
            row["run_id"] == "cold_100"
            and row["role"]
            in {"enrich", "verify", "group", "memo"}
        )
    }


def tokens_per_success(row, token_field):
    succeeded = int(row["succeeded"])

    if succeeded == 0:
        return 0.0

    return (
        int(row[token_field])
        / succeeded
    )


def stage_cost(
    calls,
    input_tokens_per_call,
    output_tokens_per_call,
    rates,
):
    input_tokens = (
        calls * input_tokens_per_call
    )

    output_tokens = (
        calls * output_tokens_per_call
    )

    cost = (
        input_tokens
        * rates.get("input_tokens", 0)
        + output_tokens
        * rates.get("output_tokens", 0)
    )

    return {
        "calls": calls,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost": cost,
    }


def money(value):
    return f"${value:,.4f}"


def main():
    usage = load_usage()
    rates = load_rates()
    stages = measured_stage_rows(usage)
    cold_recheck = next(
        row for row in usage
        if row["run_id"] == "cold_recheck_100"
        and row["role"] == "end_to_end"
    )

    # -----------------------------------------
    # MEASURED 100-REVIEW COLD PILOT
    # -----------------------------------------

    measured_input = sum(
        int(stages[r]["input_tokens"])
        for r in stages
    )

    measured_output = sum(
        int(stages[r]["output_tokens"])
        for r in stages
    )

    measured_cost = (
        measured_input
        * rates.get("input_tokens", 0)
        + measured_output
        * rates.get("output_tokens", 0)
    )

    # -----------------------------------------
    # PER-CALL MEASUREMENTS
    # -----------------------------------------

    enrich_in = tokens_per_success(
        stages["enrich"],
        "input_tokens",
    )
    enrich_out = tokens_per_success(
        stages["enrich"],
        "output_tokens",
    )

    verify_in = tokens_per_success(
        stages["verify"],
        "input_tokens",
    )
    verify_out = tokens_per_success(
        stages["verify"],
        "output_tokens",
    )

    group_in = tokens_per_success(
        stages["group"],
        "input_tokens",
    )
    group_out = tokens_per_success(
        stages["group"],
        "output_tokens",
    )

    memo_in = tokens_per_success(
        stages["memo"],
        "input_tokens",
    )
    memo_out = tokens_per_success(
        stages["memo"],
        "output_tokens",
    )

    # -----------------------------------------
    # BASE CASE
    # -----------------------------------------
    #
    # Enrichment uses exact-text reuse.
    # Verification/grouping currently projected
    # from original-record selection rates.
    #
    # This is intentionally conservative about
    # downstream exact-text reuse because the
    # current full-run scripts do not yet prove
    # cross-ID text cache reuse for those stages.
    # -----------------------------------------

    base_enrich_calls = DISTINCT_NONEMPTY_TEXTS
    base_verify_calls = (
        NONEMPTY_ROWS * VERIFY_RATE
    )
    base_group_calls = (
        NONEMPTY_ROWS * GROUP_RATE
    )
    base_memo_calls = 1

    base = {
        "enrich": stage_cost(
            base_enrich_calls,
            enrich_in,
            enrich_out,
            rates,
        ),
        "verify": stage_cost(
            base_verify_calls,
            verify_in,
            verify_out,
            rates,
        ),
        "group": stage_cost(
            base_group_calls,
            group_in,
            group_out,
            rates,
        ),
        "memo": stage_cost(
            base_memo_calls,
            memo_in,
            memo_out,
            rates,
        ),
    }

    base_total = sum(
        x["cost"]
        for x in base.values()
    )

    # -----------------------------------------
    # NO-REUSE COMPARISON
    # -----------------------------------------

    no_reuse_enrich = stage_cost(
        NONEMPTY_ROWS,
        enrich_in,
        enrich_out,
        rates,
    )

    no_reuse_total = (
        no_reuse_enrich["cost"]
        + base["verify"]["cost"]
        + base["group"]["cost"]
        + base["memo"]["cost"]
    )

    # -----------------------------------------
    # CONSERVATIVE CASE
    # -----------------------------------------

    conservative = {
        "enrich": stage_cost(
            DISTINCT_NONEMPTY_TEXTS
            * CONSERVATIVE_RETRY_MULTIPLIER,
            enrich_in,
            enrich_out,
            rates,
        ),
        "verify": stage_cost(
            NONEMPTY_ROWS
            * CONSERVATIVE_VERIFY_RATE
            * CONSERVATIVE_RETRY_MULTIPLIER,
            verify_in,
            verify_out,
            rates,
        ),
        "group": stage_cost(
            NONEMPTY_ROWS
            * CONSERVATIVE_GROUP_RATE
            * CONSERVATIVE_RETRY_MULTIPLIER,
            group_in,
            group_out,
            rates,
        ),
        "memo": stage_cost(
            1,
            memo_in,
            memo_out,
            rates,
        ),
    }

    conservative_total = sum(
        x["cost"]
        for x in conservative.values()
    )

    # -----------------------------------------
    # PRINT REPORT
    # -----------------------------------------

    print(
        "================================"
    )
    print(
        "100-REVIEW MEASURED PILOT"
    )
    print(
        "================================"
    )

    print(
        "Cold input tokens:",
        measured_input,
    )

    print(
        "Cold output tokens:",
        measured_output,
    )

    print(
        "Cold API cost:",
        money(measured_cost),
    )

    cold_recheck_cost = (
        int(cold_recheck["input_tokens"])
        * rates.get("input_tokens", 0)
        + int(cold_recheck["output_tokens"])
        * rates.get("output_tokens", 0)
    )

    print(
        "Fresh cold recheck wall clock:",
        f"{float(cold_recheck['wall_clock_seconds']):.2f} sec",
    )

    print(
        "Fresh cold recheck API cost:",
        money(cold_recheck_cost),
    )

    print(
        "Warm incremental API cost: $0.0000"
    )

    print(
        "Warm end-to-end wall clock: 0.79 sec"
    )

    print()

    print(
        "Measured avg input tokens/call:"
    )

    print(
        f"  enrich: {enrich_in:.2f}"
    )
    print(
        f"  verify: {verify_in:.2f}"
    )
    print(
        f"  group:  {group_in:.2f}"
    )
    print(
        f"  memo:   {memo_in:.2f}"
    )

    print()

    print(
        "================================"
    )
    print(
        "FULL-RUN BASE CASE"
    )
    print(
        "================================"
    )

    print(
        f"Rows accounted for: {FULL_ROWS:,}"
    )
    print(
        f"Nonempty: {NONEMPTY_ROWS:,}"
    )
    print(
        f"Quarantined empty: {EMPTY_ROWS:,}"
    )
    print(
        "Distinct nonempty texts:",
        f"{DISTINCT_NONEMPTY_TEXTS:,}",
    )

    for name in [
        "enrich",
        "verify",
        "group",
        "memo",
    ]:
        x = base[name]

        print(
            f"{name:>7}: "
            f"calls={x['calls']:,.0f} "
            f"cost={money(x['cost'])}"
        )

    print(
        "BASE TOTAL:",
        money(base_total),
    )

    print()

    print(
        "No exact-text enrichment reuse:",
        money(no_reuse_total),
    )

    print()

    print(
        "================================"
    )
    print(
        "CONSERVATIVE CASE"
    )
    print(
        "================================"
    )

    print(
        "Verification rate:",
        f"{CONSERVATIVE_VERIFY_RATE:.0%}",
    )
    print(
        "Grouping rate:",
        f"{CONSERVATIVE_GROUP_RATE:.0%}",
    )
    print(
        "Retry/work multiplier:",
        f"{CONSERVATIVE_RETRY_MULTIPLIER:.2f}x",
    )

    print(
        "CONSERVATIVE TOTAL:",
        money(conservative_total),
    )

    print()

    base_per_100k = base_total / FULL_ROWS * 100_000
    conservative_per_100k = conservative_total / FULL_ROWS * 100_000

    print(
        "Budget per 100k rows:",
        money(BUDGET_PER_100K_USD),
    )
    print(
        "Base cost per 100k rows:",
        money(base_per_100k),
    )
    print(
        "Conservative cost per 100k rows:",
        money(conservative_per_100k),
    )

    if base_per_100k > BUDGET_PER_100K_USD:
        print("WARNING: base case exceeds $10 per 100k.")
    else:
        print("Base case is within $10 per 100k.")

    if conservative_per_100k > BUDGET_PER_100K_USD:
        print("WARNING: conservative case exceeds $10 per 100k.")
    else:
        print("Conservative case is within $10 per 100k.")


if __name__ == "__main__":
    main()
