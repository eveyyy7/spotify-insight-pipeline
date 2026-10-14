import os
import csv
import json
import time
import uuid
import hashlib
from pathlib import Path

import requests
from dotenv import load_dotenv


MODEL = "jev-latest"
LABEL_CONFIG = "jev-latest+memo-choice-v1"


def append_jsonl(path, obj):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="grading_smoke")
    args = parser.parse_args()

    load_dotenv()

    api_key = os.getenv("TYPESAFE_API_KEY")
    if not api_key:
        raise ValueError("TYPESAFE_API_KEY missing")

    out_dir = Path(args.out)
    ranking_file = out_dir / "ranking.csv"
    claims_file = out_dir / "claims.csv"
    calls_file = out_dir / "calls.jsonl"
    memo_file = out_dir / "memo.md"

    cache_file = out_dir / "memo_cache.json"
    input_digest = hashlib.sha256(
        ranking_file.read_bytes() + b"\0" + claims_file.read_bytes() + b"\0" + LABEL_CONFIG.encode()
    ).hexdigest()

    # Warm replay only when both the aggregate inputs and configuration match.
    if memo_file.exists() and cache_file.exists() and json.loads(
        cache_file.read_text(encoding="utf-8")
    ).get("input_sha256") == input_digest:
        print("\n==============================")
        print("MEMO DONE")
        print("==============================")
        print("Cache hit: yes")
        print("New API calls: 0")
        print("Saved:", memo_file)
        return

    with open(ranking_file, newline="", encoding="utf-8") as f:
        ranking = list(csv.DictReader(f))

    with open(claims_file, newline="", encoding="utf-8") as f:
        claims = list(csv.DictReader(f))

    if not ranking:
        raise ValueError("ranking.csv is empty")

    # Build claim lookup
    claim_lookup = {}
    for c in claims:
        claim_lookup[(c["issue_id"], c["metric"])] = c

    # Give Jev the bounded ranked evidence.
    state = {
        "instruction": (
            "Select the strongest next-quarter Spotify product priority "
            "from these already-computed issue rankings. "
            "Use the quantitative ranking as the primary evidence."
        ),
        "issues": ranking,
    }

    # One choice per ranked issue.
    criteria = {}

    for row in ranking:
        iid = row["issue_id"]
        criteria[iid] = (
            f"rank={row['rank']}; "
            f"complaint_count={row['complaint_count']}; "
            f"severity_sum={row['severity_sum']}; "
            f"mean_severity={row['mean_severity']}; "
            f"priority_score={row['priority_score']}"
        )

    questions = {
        "priority": {
            "type": "choice",
            "instructions": (
                "Choose the single strongest next-quarter priority. "
                "Prefer the issue with the strongest quantitative "
                "priority evidence unless another listed issue has a "
                "clearly stronger severity case."
            ),
            "criteria": criteria,
        }
    }

    payload = {
        "model": MODEL,
        "state": state,
        "questions": questions,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    request_id = str(uuid.uuid4())
    start = time.time()

    response = requests.post(
        "https://api.typesafe.ai/v1/systemone",
        headers=headers,
        json=payload,
        timeout=60,
    )

    elapsed = time.time() - start

    if response.status_code != 200:
        append_jsonl(
            calls_file,
            {
                "request_id": request_id,
                "role": "memo",
                "review_ids": [],
                "model": MODEL,
                "phase": "initial",
                "outcome": "failed",
                "label_config": LABEL_CONFIG,
                "input_tokens": 0,
                "output_tokens": 0,
                "runtime_seconds": round(elapsed, 3),
                "error": response.text,
            },
        )
        raise RuntimeError(
            f"Memo decision failed: {response.status_code} {response.text}"
        )

    data = response.json()
    usage = data.get("usage", {})

    chosen = data["answers"]["priority"]["choice"]
    confidence = data["answers"]["priority"]["confidence"]

    append_jsonl(
        calls_file,
        {
            "request_id": request_id,
            "role": "memo",
            "review_ids": [],
            "model": data.get("model", MODEL),
            "phase": "initial",
            "outcome": "succeeded",
            "label_config": LABEL_CONFIG,
            "input_tokens": usage.get("input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
            "runtime_seconds": round(elapsed, 3),
        },
    )

    by_issue = {r["issue_id"]: r for r in ranking}

    selected = by_issue[chosen]

    comparison = next(
        (r for r in ranking if r["issue_id"] != chosen),
        None,
    )

    def claim(issue, metric):
        return claim_lookup[(issue, metric)]["claim_id"]

    memo = []

    memo.append("# Spotify Product Priority Memo")
    memo.append("")
    memo.append("## Recommendation")
    memo.append("")
    memo.append(
        f"Prioritize **{chosen}** for the next product cycle."
    )
    memo.append("")
    memo.append(
        f"It has {selected['complaint_count']} complaint/cancellation "
        f"records [{claim(chosen, 'complaint_count')}], "
        f"a severity sum of {selected['severity_sum']} "
        f"[{claim(chosen, 'severity_sum')}], and a baseline priority "
        f"score of {selected['priority_score']} "
        f"[{claim(chosen, 'priority_score')}]."
    )

    if comparison:
        memo.append("")
        memo.append(
            f"The next-ranked issue is **{comparison['issue_id']}**, "
            f"with a priority score of {comparison['priority_score']} "
            f"[{claim(comparison['issue_id'], 'priority_score')}]."
        )

    memo.append("")
    memo.append(
        f"Jev selected {chosen} as the recommendation candidate "
        f"with confidence {confidence:.2f}. "
        "The prose above is generated deterministically from saved "
        "ranking and claim artifacts."
    )

    with open(memo_file, "w", encoding="utf-8") as f:
        f.write("\n".join(memo) + "\n")
    cache_file.write_text(
        json.dumps({"input_sha256": input_digest, "label_config": LABEL_CONFIG}, indent=2) + "\n",
        encoding="utf-8",
    )

    print("\n==============================")
    print("MEMO DONE")
    print("==============================")
    print("Chosen issue:", chosen)
    print("Confidence:", round(confidence, 3))
    print("Input tokens:", usage.get("input_tokens", 0))
    print("Output tokens:", usage.get("output_tokens", 0))
    print("Saved:", memo_file)


if __name__ == "__main__":
    main()
