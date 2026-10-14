#!/usr/bin/env python3
"""Select one dashboard recommendation with Jev and retain call evidence."""

import argparse
import csv
import gzip
import hashlib
import json
import os
import time
import uuid
from pathlib import Path

import requests
from dotenv import load_dotenv


MODEL = "jev-latest"
LABEL_CONFIG = "jev-latest+dashboard-recommendation-v1"


def append_jsonl(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ranking", required=True, type=Path)
    parser.add_argument("--records", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--calls-log", required=True, type=Path)
    args = parser.parse_args()

    load_dotenv(Path.cwd() / ".env")
    api_key = os.getenv("TYPESAFE_API_KEY")
    if not api_key:
        raise ValueError("TYPESAFE_API_KEY missing")

    with args.ranking.open(newline="", encoding="utf-8") as handle:
        ranking = list(csv.DictReader(handle))

    evidence = []
    with gzip.open(args.records, "rt", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            if (
                row.get("status") == "completed"
                and row.get("topic") == "playback"
                and row.get("intent") in {"complaint", "cancellation"}
                and int(row.get("severity", 0)) >= 4
            ):
                evidence.append(
                    {
                        "review_id": row["review_id"],
                        "intent": row["intent"],
                        "severity": row["severity"],
                        "evidence_quote": row.get("evidence_quote", ""),
                    }
                )
                if len(evidence) == 8:
                    break

    recommendation_options = {
        (
            "Prioritize playback reliability in the next product cycle: reduce crashes "
            "and unexpected stops, prevent unwanted track substitution, and make "
            "failure-to-start states diagnosable and recoverable."
        ): "Playback is the candidate when cumulative severity and broad user impact dominate.",
        (
            "Prioritize usability in the next product cycle: simplify navigation, restore "
            "predictable controls, and remove friction in playlist and queue workflows."
        ): "Usability is the candidate when complaint volume dominates despite lower average severity.",
        (
            "Prioritize account access in the next product cycle: harden authentication, "
            "recovery, and false-offline paths for the highest-severity affected users."
        ): "Access is the candidate when mean severity dominates despite narrower reach.",
        (
            "Prioritize billing reliability in the next product cycle: resolve entitlement, "
            "charge, payment, and refund failures with clearer recovery paths."
        ): "Billing is the candidate when direct financial harm outweighs the broader issue ranking.",
    }

    state = {
        "task": "Recommend one next-cycle Spotify product priority from analyzed metrics and traceable evidence.",
        "ranking": ranking,
        "representative_playback_evidence": evidence,
        "decision_rule": (
            "Use priority_score (cumulative severity) as the primary signal. Use complaint "
            "count and mean severity to explain tradeoffs. Do not infer facts outside the evidence."
        ),
    }
    payload = {
        "model": MODEL,
        "state": state,
        "questions": {
            "recommendation": {
                "type": "choice",
                "instructions": (
                    "Choose the single recommendation best supported by the supplied ranking "
                    "and evidence. Return the recommendation text exactly as the choice."
                ),
                "criteria": recommendation_options,
            }
        },
    }

    request_id = str(uuid.uuid4())
    started = time.time()
    response = requests.post(
        "https://api.typesafe.ai/v1/systemone",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    runtime = round(time.time() - started, 3)

    state_sha256 = hashlib.sha256(
        json.dumps(state, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()

    if response.status_code != 200:
        call = {
            "request_id": request_id,
            "role": "memo",
            "review_ids": [item["review_id"] for item in evidence],
            "model": MODEL,
            "phase": "initial",
            "outcome": "failed",
            "label_config": LABEL_CONFIG,
            "input_tokens": 0,
            "output_tokens": 0,
            "runtime_seconds": runtime,
            "state_sha256": state_sha256,
            "error": response.text[:500],
        }
        append_jsonl(args.calls_log, call)
        raise RuntimeError(f"Jev recommendation failed with HTTP {response.status_code}")

    data = response.json()
    answer = data["answers"]["recommendation"]
    recommendation = answer["choice"]
    usage = data.get("usage", {})
    call = {
        "request_id": request_id,
        "role": "memo",
        "review_ids": [item["review_id"] for item in evidence],
        "model": data.get("model", MODEL),
        "phase": "initial",
        "outcome": "succeeded",
        "label_config": LABEL_CONFIG,
        "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
        "runtime_seconds": runtime,
        "state_sha256": state_sha256,
        "answer": recommendation,
        "confidence": answer.get("confidence"),
    }
    append_jsonl(args.calls_log, call)

    artifact = {
        "id": "jev-dashboard-recommendation-v1",
        "text": recommendation,
        "model": call["model"],
        "requestId": request_id,
        "confidence": answer.get("confidence"),
        "labelConfig": LABEL_CONFIG,
        "inputTokens": call["input_tokens"],
        "outputTokens": call["output_tokens"],
        "runtimeSeconds": runtime,
        "stateSha256": state_sha256,
        "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "evidenceReviewIds": call["review_ids"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(artifact, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(artifact, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
