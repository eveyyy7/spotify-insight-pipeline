import os
import csv
import json
import time
import uuid
import argparse
import hashlib
from pathlib import Path

import requests
from dotenv import load_dotenv


MODEL = "jev-latest"
VERIFY_LABEL_CONFIG = "jev-latest+verify-prompt-v1+verify-schema-v1"


QUESTIONS = {
    "topic": {
        "type": "choice",
        "instructions": (
            "Independently classify the primary Spotify product issue. "
            "If multiple issues exist, choose the highest-supported-severity "
            "specific problem; tie = first specific issue."
        ),
        "criteria": {
            "access": "login/signup/password/account access",
            "usability": "UI/navigation/controls/queue/playlist/ads",
            "playback": "playback failure/crash/lag/stopping/audio",
            "downloads": "download/offline listening",
            "catalog": "content/search/recommendations/lyrics",
            "billing": "price/charges/subscription/paywall/Premium controls",
            "support": "customer support/help",
            "other": "no specific supported issue",
        },
    },

    "intent": {
        "type": "choice",
        "instructions": (
            "Use precedence: cancellation > complaint > request > praise > unclear."
        ),
        "criteria": {
            "cancellation": "explicit leaving/cancelling/uninstalling/stopping use",
            "complaint": "negative experience or reported product problem",
            "request": "desired change without reported failure",
            "praise": "positive evaluation",
            "unclear": "cannot determine",
        },
    },

    "severity": {
        "type": "choice",
        "instructions": (
            "Judge functional impact only. "
            "Do not infer severity from anger, rating, or cancellation."
        ),
        "criteria": {
            "1": "no problem/praise/unclear/pure request",
            "2": "minor annoyance/generic criticism/cosmetic",
            "3": "function degraded or restricted; some use remains",
            "4": "core task blocked",
            "5": "serious financial/privacy/data harm",
        },
    },
}


def append_jsonl(path, obj):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("source_csv")
    parser.add_argument("records_jsonl")
    parser.add_argument("--out", default="grading_smoke")
    parser.add_argument("--max-cases", type=int, default=50,
                        help="Deterministic cap on independent verification calls")

    args = parser.parse_args()

    load_dotenv()
    api_key = os.getenv("TYPESAFE_API_KEY")

    if not api_key:
        raise ValueError("TYPESAFE_API_KEY missing")

    out_dir = Path(args.out)
    calls_file = out_dir / "calls.jsonl"
    result_file = out_dir / "verification_results.jsonl"

    # Source text lookup
    source = {}

    with open(
        args.source_csv,
        newline="",
        encoding="utf-8",
    ) as f:
        for r in csv.DictReader(f):
            source[r["review_id"]] = r["review_text"]

    # Select a frozen deterministic sample of needs_review cases. Verification
    # is an audit sample, not a second full-corpus classification pass.
    selected = []

    with open(
        args.records_jsonl,
        encoding="utf-8",
    ) as f:
        for line in f:
            r = json.loads(line)

            if (
                r.get("status") == "completed"
                and r.get("needs_review") is True
            ):
                selected.append(r["review_id"])

    selected.sort(key=lambda review_id: hashlib.sha256(
        ("verification-v1:" + review_id).encode("utf-8")
    ).hexdigest())
    selected = selected[:args.max_cases]

    # Resume/cache: do not verify IDs already saved successfully.
    existing = set()

    if result_file.exists():
        with open(result_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                if row.get("review_id"):
                    existing.add(row["review_id"])

    pending = [
        review_id
        for review_id in selected
        if review_id not in existing
    ]

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    completed = 0
    disagreements = 0

    for i, review_id in enumerate(pending, 1):

        review_text = source[review_id]

        payload = {
            "model": MODEL,
            "state": {
                "review_id": review_id,
                "review_text": review_text,
            },
            "questions": QUESTIONS,
        }

        request_id = str(uuid.uuid4())
        start = time.time()

        response = requests.post(
            "https://api.typesafe.ai/v1/systemone",
            headers=headers,
            json=payload,
            timeout=30,
        )

        elapsed = time.time() - start

        if response.status_code != 200:

            append_jsonl(
                calls_file,
                {
                    "request_id": request_id,
                    "role": "verify",
                    "review_ids": [review_id],
                    "model": MODEL,
                    "phase": "initial",
                    "outcome": "failed",
                    "label_config": VERIFY_LABEL_CONFIG,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "runtime_seconds": round(elapsed, 3),
                    "error": response.text,
                },
            )

            print("FAILED:", review_id)
            continue

        data = response.json()
        answers = data["answers"]
        usage = data.get("usage", {})

        verify = {
            "review_id": review_id,
            "topic": answers["topic"]["choice"],
            "intent": answers["intent"]["choice"],
            "severity": int(
                answers["severity"]["choice"]
            ),
            "label_config": VERIFY_LABEL_CONFIG,
        }

        append_jsonl(
            result_file,
            verify,
        )

        append_jsonl(
            calls_file,
            {
                "request_id": request_id,
                "role": "verify",
                "review_ids": [review_id],
                "model": data.get("model", MODEL),
                "phase": "initial",
                "outcome": "succeeded",
                "label_config": VERIFY_LABEL_CONFIG,
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
                "runtime_seconds": round(elapsed, 3),
            },
        )

        completed += 1

        print(
            f"{i}/{len(pending)} "
            f"{review_id} "
            f"{verify['topic']} "
            f"{verify['intent']} "
            f"{verify['severity']}"
        )

    print("\n==============================")
    print("VERIFICATION DONE")
    print("==============================")
    print("Selected:", len(selected))
    print("Already verified:", len(existing))
    print("Pending this run:", len(pending))
    print("Completed this run:", completed)
    print("New API calls:", completed)
    print("Saved:", result_file)


if __name__ == "__main__":
    main()
