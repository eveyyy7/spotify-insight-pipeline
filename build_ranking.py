import csv
import json
import argparse
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


INCLUDED_INTENTS = {"complaint", "cancellation"}


def round6(value):
    return Decimal(str(value)).quantize(
        Decimal("0.000001"),
        rounding=ROUND_HALF_UP,
    )


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "records_jsonl",
        help="Path to records.jsonl",
    )

    parser.add_argument(
        "--out",
        default="grading_smoke",
        help="Output directory",
    )

    args = parser.parse_args()

    records_path = Path(args.records_jsonl)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    membership_path = out_dir / "membership.csv"
    ranking_path = out_dir / "ranking.csv"
    claims_path = out_dir / "claims.csv"

    memberships = []
    issue_stats = defaultdict(
        lambda: {
            "complaint_count": 0,
            "severity_sum": 0,
        }
    )

    # ------------------------------------------------
    # READ RECORDS + BUILD MEMBERSHIP
    # ------------------------------------------------

    with records_path.open(
        encoding="utf-8"
    ) as f:

        for line in f:
            line = line.strip()

            if not line:
                continue

            record = json.loads(line)

            if record.get("status") != "completed":
                continue

            intent = record.get("intent")

            if intent not in INCLUDED_INTENTS:
                continue

            review_id = record["review_id"]
            topic = record["topic"]
            severity = int(record["severity"])

            issue_id = f"topic:{topic}"

            memberships.append(
                {
                    "review_id": review_id,
                    "issue_id": issue_id,
                }
            )

            issue_stats[
                issue_id
            ]["complaint_count"] += 1

            issue_stats[
                issue_id
            ]["severity_sum"] += severity

    # ------------------------------------------------
    # WRITE MEMBERSHIP.CSV
    # ------------------------------------------------

    with membership_path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=[
                "review_id",
                "issue_id",
            ],
        )

        writer.writeheader()
        writer.writerows(memberships)

    # ------------------------------------------------
    # BUILD RANKING
    # ------------------------------------------------

    ranking_rows = []

    for issue_id, stats in issue_stats.items():

        complaint_count = stats[
            "complaint_count"
        ]

        severity_sum = stats[
            "severity_sum"
        ]

        mean_severity = (
            Decimal(severity_sum)
            / Decimal(complaint_count)
        )

        mean_severity = mean_severity.quantize(
            Decimal("0.000001"),
            rounding=ROUND_HALF_UP,
        )

        priority_score = severity_sum

        ranking_rows.append(
            {
                "issue_id": issue_id,
                "complaint_count": complaint_count,
                "severity_sum": severity_sum,
                "mean_severity": str(mean_severity),
                "priority_score": priority_score,
            }
        )

    ranking_rows.sort(
        key=lambda r: (
            -int(r["priority_score"]),
            r["issue_id"],
        )
    )

    for rank, row in enumerate(ranking_rows, 1):
        row["rank"] = rank

    # ------------------------------------------------
    # WRITE RANKING.CSV
    # ------------------------------------------------

    with ranking_path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=[
                "rank",
                "issue_id",
                "complaint_count",
                "severity_sum",
                "mean_severity",
                "priority_score",
            ],
        )

        writer.writeheader()
        writer.writerows(ranking_rows)

    # ------------------------------------------------
    # BUILD CLAIMS.CSV
    # ------------------------------------------------

    claims = []

    claim_number = 1

    for row in ranking_rows:

        issue_id = row["issue_id"]

        for metric in [
            "complaint_count",
            "severity_sum",
            "mean_severity",
            "priority_score",
        ]:

            claims.append(
                {
                    "claim_id": f"C{claim_number:04d}",
                    "issue_id": issue_id,
                    "metric": metric,
                    "value": row[metric],
                }
            )

            claim_number += 1

    # ------------------------------------------------
    # WRITE CLAIMS.CSV
    # ------------------------------------------------

    with claims_path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=[
                "claim_id",
                "issue_id",
                "metric",
                "value",
            ],
        )

        writer.writeheader()
        writer.writerows(claims)

    # ------------------------------------------------
    # SUMMARY
    # ------------------------------------------------

    print("\n==============================")
    print("BASELINE RANKING DONE")
    print("==============================")

    print(
        "Membership rows:",
        len(memberships),
    )

    print(
        "Issues:",
        len(ranking_rows),
    )

    print("\nRanking:")

    for i, row in enumerate(
        ranking_rows,
        1,
    ):
        print(
            f"{i}. "
            f"{row['issue_id']} | "
            f"count={row['complaint_count']} | "
            f"severity_sum={row['severity_sum']} | "
            f"mean={row['mean_severity']} | "
            f"score={row['priority_score']}"
        )

    print("\nSaved:")
    print(membership_path)
    print(ranking_path)
    print(claims_path)


if __name__ == "__main__":
    main()