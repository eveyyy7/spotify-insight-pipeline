#!/usr/bin/env python3
"""Build a versioned D1 import snapshot from the final grading artifacts."""

import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path


EVIDENCE_IDS = [
    "a6eee2f8-ce5b-4686-a1f4-2c90c159bdd2",
    "b3da207e-888d-40bd-bd5d-11f376f5eeda",
    "17f29b88-fc31-4e9f-b9ca-44cf26120617",
]


def digest_files(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    digest.update(b"dashboard-import-v2-redacted-sample\0")
    for path in paths:
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ranking", required=True, type=Path)
    parser.add_argument("--claims", required=True, type=Path)
    parser.add_argument("--records", required=True, type=Path)
    parser.add_argument("--recommendation", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--sample-size", type=int, default=500)
    args = parser.parse_args()

    with args.ranking.open(newline="", encoding="utf-8") as handle:
        ranking_rows = list(csv.DictReader(handle))
    with args.claims.open(newline="", encoding="utf-8") as handle:
        claim_rows = list(csv.DictReader(handle))
    recommendation = json.loads(args.recommendation.read_text(encoding="utf-8"))

    status_counts: dict[str, int] = {}
    complaints = cancellations = needs_review = 0
    playback_rows = []
    evidence_by_id = {}
    with gzip.open(args.records, "rt", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            status = row.get("status", "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
            if status == "completed":
                complaints += int(row.get("intent") == "complaint")
                cancellations += int(row.get("intent") == "cancellation")
                needs_review += int(bool(row.get("needs_review")))
            if row.get("review_id") in EVIDENCE_IDS:
                evidence_by_id[row["review_id"]] = row
            if (
                status == "completed"
                and row.get("topic") == "playback"
                and row.get("intent") in {"complaint", "cancellation"}
            ):
                playback_rows.append(row)

    def sample_key(row: dict) -> str:
        return hashlib.sha256(("dashboard-sample-v1:" + row["review_id"]).encode()).hexdigest()

    required = [row for review_id in EVIDENCE_IDS if (row := evidence_by_id.get(review_id))]
    required_ids = {row["review_id"] for row in required}
    remaining = sorted(
        (row for row in playback_rows if row["review_id"] not in required_ids),
        key=sample_key,
    )
    sampled = (required + remaining)[: args.sample_size]

    def processed(row: dict, include_quote: bool = False) -> dict:
        return {
            "reviewId": row["review_id"],
            "sourceSha256": row["source_sha256"],
            "topic": row["topic"],
            "intent": row["intent"],
            "severity": int(row["severity"]),
            "sentiment": float(row["sentiment"]),
            "evidenceQuote": row.get("evidence_quote", "") if include_quote else "",
            "needsReview": bool(row.get("needs_review")),
            "labelConfig": row["label_config"],
        }

    digest = digest_files([args.ranking, args.claims, args.records, args.recommendation])
    import_id = "final-100100-" + digest[:12]
    artifact = {
        "importId": import_id,
        "sourceDigest": digest,
        "summary": {
            "id": import_id,
            "scopeLabel": "100,100-review final analysis scope",
            "analyzedReviews": sum(status_counts.values()),
            "complaints": complaints,
            "cancellations": cancellations,
            "needsReview": needs_review,
            "recommendation": recommendation["text"],
            "refreshedAt": recommendation["createdAt"],
        },
        "ranking": [
            {
                "issueId": row["issue_id"],
                "rank": int(row["rank"]),
                "label": row["issue_id"].split(":", 1)[-1].title(),
                "complaintCount": int(row["complaint_count"]),
                "meanSeverity": float(row["mean_severity"]),
                "severitySum": int(row["severity_sum"]),
                "priorityScore": int(row["priority_score"]),
            }
            for row in ranking_rows
        ],
        "claims": [
            {
                "claimId": row["claim_id"],
                "issueId": row["issue_id"],
                "metric": row["metric"],
                "value": row["value"],
            }
            for row in claim_rows
        ],
        "processedReviews": [processed(row) for row in sampled],
        "evidence": [processed(evidence_by_id[review_id], include_quote=True) for review_id in EVIDENCE_IDS],
        "recommendation": recommendation,
        "modelCall": {
            "requestId": recommendation["requestId"],
            "role": "memo",
            "model": recommendation["model"],
            "outcome": "succeeded",
            "labelConfig": recommendation["labelConfig"],
            "inputTokens": recommendation["inputTokens"],
            "outputTokens": recommendation["outputTokens"],
            "runtimeSeconds": recommendation["runtimeSeconds"],
            "stateSha256": recommendation["stateSha256"],
            "answer": recommendation["text"],
            "confidence": recommendation["confidence"],
            "createdAt": recommendation["createdAt"],
        },
        "stats": {
            "classifiedReviews": status_counts.get("completed", 0),
            "quarantinedReviews": status_counts.get("quarantined", 0),
            "playbackProblemRecords": len(playback_rows),
            "processedReviewSampleRows": len(sampled),
            "claimRows": len(claim_rows),
            "rankingRows": len(ranking_rows),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(artifact, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "importId": import_id, "stats": artifact["stats"]}, indent=2))


if __name__ == "__main__":
    main()
