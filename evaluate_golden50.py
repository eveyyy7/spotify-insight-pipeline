import csv
from collections import Counter

GOLD_FILE = "evals/golden_50_labeled.csv"
PRED_FILE = "jev_golden50_results.csv"
ERROR_FILE = "golden50_errors.csv"


def to_float(x):
    try:
        return float(x)
    except Exception:
        return None


def to_int(x):
    try:
        return int(float(x))
    except Exception:
        return None


# =========================
# LOAD
# =========================

with open(
    GOLD_FILE,
    newline="",
    encoding="utf-8",
) as f:
    gold_rows = list(csv.DictReader(f))

with open(
    PRED_FILE,
    newline="",
    encoding="utf-8",
) as f:
    pred_rows = list(csv.DictReader(f))


gold_by_id = {
    r["review_id"]: r
    for r in gold_rows
}

pred_by_id = {
    r["review_id"]: r
    for r in pred_rows
}


# =========================
# MATCH
# =========================

matched_ids = sorted(
    set(gold_by_id) & set(pred_by_id)
)

print("Golden rows:", len(gold_rows))
print("Prediction rows:", len(pred_rows))
print("Matched rows:", len(matched_ids))


# =========================
# METRICS
# =========================

topic_correct = 0
intent_correct = 0
severity_correct = 0

severity_abs_errors = []

sentiment_abs_errors = []

needs_review_correct = 0

errors = []


for review_id in matched_ids:

    gold = gold_by_id[review_id]
    pred = pred_by_id[review_id]

    gold_topic = gold["topic"].strip()
    pred_topic = pred["topic"].strip()

    gold_intent = gold["intent"].strip()
    pred_intent = pred["intent"].strip()

    gold_severity = to_int(
        gold["severity"]
    )
    pred_severity = to_int(
        pred["severity"]
    )

    gold_sentiment = to_float(
        gold["sentiment"]
    )
    pred_sentiment = to_float(
        pred["sentiment"]
    )

    gold_needs_review = (
        gold["needs_review"]
        .strip()
        .lower()
        in {"true", "1", "yes"}
    )

    pred_needs_review = (
        pred["needs_review"]
        .strip()
        .lower()
        in {"true", "1", "yes"}
    )

    topic_ok = (
        gold_topic == pred_topic
    )

    intent_ok = (
        gold_intent == pred_intent
    )

    severity_ok = (
        gold_severity == pred_severity
    )

    needs_review_ok = (
        gold_needs_review
        == pred_needs_review
    )

    if topic_ok:
        topic_correct += 1

    if intent_ok:
        intent_correct += 1

    if severity_ok:
        severity_correct += 1

    if needs_review_ok:
        needs_review_correct += 1

    if (
        gold_severity is not None
        and pred_severity is not None
    ):
        severity_abs_errors.append(
            abs(
                gold_severity
                - pred_severity
            )
        )

    if (
        gold_sentiment is not None
        and pred_sentiment is not None
    ):
        sentiment_abs_errors.append(
            abs(
                gold_sentiment
                - pred_sentiment
            )
        )

    if not (
        topic_ok
        and intent_ok
        and severity_ok
    ):

        errors.append({
            "review_id": review_id,
            "review_text": gold[
                "review_text"
            ],

            "gold_topic": gold_topic,
            "pred_topic": pred_topic,

            "gold_intent": gold_intent,
            "pred_intent": pred_intent,

            "gold_severity": (
                gold_severity
            ),
            "pred_severity": (
                pred_severity
            ),

            "gold_sentiment": (
                gold_sentiment
            ),
            "pred_sentiment": (
                pred_sentiment
            ),

            "pred_topic_confidence":
                pred.get(
                    "topic_confidence",
                    ""
                ),

            "pred_intent_confidence":
                pred.get(
                    "intent_confidence",
                    ""
                ),

            "pred_severity_confidence":
                pred.get(
                    "severity_confidence",
                    ""
                ),

            "needs_review":
                pred.get(
                    "needs_review",
                    ""
                ),

            "needs_review_reason":
                pred.get(
                    "needs_review_reason",
                    ""
                ),
        })


# =========================
# PRINT SUMMARY
# =========================

n = len(matched_ids)

print("\n==============================")
print("GOLDEN 50 EVALUATION")
print("==============================")

if n == 0:
    raise ValueError(
        "No matching review_ids found."
    )

topic_accuracy = (
    topic_correct / n
)

intent_accuracy = (
    intent_correct / n
)

severity_accuracy = (
    severity_correct / n
)

needs_review_accuracy = (
    needs_review_correct / n
)

severity_mae = (
    sum(severity_abs_errors)
    / len(severity_abs_errors)
    if severity_abs_errors
    else None
)

sentiment_mae = (
    sum(sentiment_abs_errors)
    / len(sentiment_abs_errors)
    if sentiment_abs_errors
    else None
)


print(
    f"Topic accuracy: "
    f"{topic_accuracy:.1%} "
    f"({topic_correct}/{n})"
)

print(
    f"Intent accuracy: "
    f"{intent_accuracy:.1%} "
    f"({intent_correct}/{n})"
)

print(
    f"Severity exact accuracy: "
    f"{severity_accuracy:.1%} "
    f"({severity_correct}/{n})"
)

print(
    f"Severity MAE: "
    f"{severity_mae:.3f}"
)

print(
    f"Sentiment MAE: "
    f"{sentiment_mae:.3f}"
)

print(
    f"Needs-review agreement: "
    f"{needs_review_accuracy:.1%} "
    f"({needs_review_correct}/{n})"
)

print(
    f"Rows with topic/intent/"
    f"severity error: "
    f"{len(errors)}"
)


# =========================
# ERROR COUNTS
# =========================

topic_confusions = Counter()
intent_confusions = Counter()
severity_confusions = Counter()

for review_id in matched_ids:

    gold = gold_by_id[review_id]
    pred = pred_by_id[review_id]

    if (
        gold["topic"].strip()
        != pred["topic"].strip()
    ):
        topic_confusions[
            (
                gold["topic"].strip(),
                pred["topic"].strip(),
            )
        ] += 1

    if (
        gold["intent"].strip()
        != pred["intent"].strip()
    ):
        intent_confusions[
            (
                gold["intent"].strip(),
                pred["intent"].strip(),
            )
        ] += 1

    gs = to_int(
        gold["severity"]
    )
    ps = to_int(
        pred["severity"]
    )

    if gs != ps:
        severity_confusions[
            (gs, ps)
        ] += 1


print("\nTop topic confusions:")
for pair, count in (
    topic_confusions
    .most_common(10)
):
    print(
        f"  {pair[0]} -> "
        f"{pair[1]}: "
        f"{count}"
    )


print("\nTop intent confusions:")
for pair, count in (
    intent_confusions
    .most_common(10)
):
    print(
        f"  {pair[0]} -> "
        f"{pair[1]}: "
        f"{count}"
    )


print("\nSeverity confusions:")
for pair, count in (
    severity_confusions
    .most_common()
):
    print(
        f"  {pair[0]} -> "
        f"{pair[1]}: "
        f"{count}"
    )


# =========================
# SAVE ERROR FILE
# =========================

fieldnames = [
    "review_id",
    "review_text",

    "gold_topic",
    "pred_topic",

    "gold_intent",
    "pred_intent",

    "gold_severity",
    "pred_severity",

    "gold_sentiment",
    "pred_sentiment",

    "pred_topic_confidence",
    "pred_intent_confidence",
    "pred_severity_confidence",

    "needs_review",
    "needs_review_reason",
]


with open(
    ERROR_FILE,
    "w",
    newline="",
    encoding="utf-8",
) as f:

    writer = csv.DictWriter(
        f,
        fieldnames=fieldnames,
    )

    writer.writeheader()
    writer.writerows(errors)


print(
    f"\nSaved error analysis to: "
    f"{ERROR_FILE}"
)