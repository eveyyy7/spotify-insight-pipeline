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
GROUP_LABEL_CONFIG = "jev-latest+group-prompt-v1+group-schema-v1"

INCLUDED_INTENTS = {"complaint", "cancellation"}


ISSUES = {
    # usability
    "usability__playback_controls_restricted":
        "Playback controls restricted: skip, previous, seek, repeat, queue, song selection.",
    "usability__ads_experience":
        "Ads are excessive, intrusive, repetitive, disruptive, or too loud.",
    "usability__navigation_ui_design":
        "Navigation, layout, interface design, home screen, or usability problems.",
    "usability__playlist_management":
        "Creating, editing, organizing, or managing playlists or queues.",
    "usability__feature_regression":
        "A previously available feature or workflow became worse after an update.",
    "usability__other_usability":
        "Other usability problem not fitting the listed usability issues.",

    # playback
    "playback__playback_stops_randomly":
        "Playback unexpectedly stops, pauses, or interrupts during listening.",
    "playback__cannot_start_playback":
        "User cannot start or initiate playback.",
    "playback__wrong_unwanted_tracks":
        "Wrong, unwanted, or unexpected songs/tracks play.",
    "playback__skip_seek_restrictions":
        "Skipping, seeking, previous-track, or track-position controls malfunction or are restricted.",
    "playback__crash_freeze_loading":
        "App crashes, freezes, hangs, or remains stuck loading.",
    "playback__device_background_connection":
        "Playback problems involving devices, Bluetooth, background mode, or connectivity.",
    "playback__other_playback":
        "Other playback problem not fitting the listed playback issues.",

    # billing
    "billing__premium_feature_paywall":
        "Core feature is blocked or gated behind Premium.",
    "billing__premium_pressure_pricing":
        "Complaint about Premium upselling, pricing pressure, or perceived excessive cost.",
    "billing__discount_eligibility":
        "Student, family, regional, or other discount eligibility problem.",
    "billing__subscription_entitlement":
        "Paid subscription exists but Premium entitlement/features are missing or incorrect.",
    "billing__charge_payment_issue":
        "Unexpected charge, payment failure, duplicate charge, refund, or transaction problem.",
    "billing__other_billing":
        "Other billing/subscription problem.",

    # access
    "access__login_failure":
        "Cannot log in or authenticate.",
    "access__phone_number_login":
        "Problem specifically involving phone-number login or verification.",
    "access__password_recovery":
        "Password reset or account recovery problem.",
    "access__unexpected_logout":
        "Unexpectedly logged out or repeatedly signed out.",
    "access__false_offline_connection":
        "App incorrectly reports offline/no connection and blocks access.",
    "access__regional_availability":
        "Access is blocked or unavailable because of country or region.",
    "access__other_access":
        "Other account-access problem.",

    # fallback topics
    "catalog__catalog_issue":
        "Catalog, search, artist, song, recommendation, lyrics, or content issue.",
    "downloads__download_issue":
        "Download, offline listening, or saved-content issue.",
    "support__support_issue":
        "Customer support or help experience issue.",
    "other__other_issue":
        "Complaint that does not fit another listed issue.",
}


def append_jsonl(path, obj):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def load_existing_results(path):
    done = {}

    if not path.exists():
        return done

    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            if not line:
                continue

            row = json.loads(line)
            done[row["review_id"]] = row

    return done


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("source_csv")
    parser.add_argument("records_jsonl")

    parser.add_argument(
        "--out",
        default="grading_smoke",
    )
    parser.add_argument(
        "--max-cases",
        type=int,
        default=200,
        help="Deterministic cap for model-assisted sub-issue discovery; baseline membership still covers every complaint in build_ranking.py",
    )

    args = parser.parse_args()

    load_dotenv()

    api_key = os.getenv("TYPESAFE_API_KEY")

    if not api_key:
        raise ValueError("TYPESAFE_API_KEY missing")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    calls_file = out_dir / "calls.jsonl"
    result_file = out_dir / "grouping_results.jsonl"

    source_text = {}

    with open(
        args.source_csv,
        newline="",
        encoding="utf-8",
    ) as f:
        for row in csv.DictReader(f):
            source_text[row["review_id"]] = row["review_text"]

    selected = []

    with open(
        args.records_jsonl,
        encoding="utf-8",
    ) as f:
        for line in f:
            line = line.strip()

            if not line:
                continue

            row = json.loads(line)

            if (
                row.get("status") == "completed"
                and row.get("intent") in INCLUDED_INTENTS
            ):
                selected.append(
                    {
                        "review_id": row["review_id"],
                        "enricher_topic": row["topic"],
                    }
                )

    selected.sort(key=lambda row: hashlib.sha256(
        ("grouping-v1:" + row["review_id"]).encode("utf-8")
    ).hexdigest())
    selected = selected[:args.max_cases]

    existing = load_existing_results(result_file)

    pending = [
        row
        for row in selected
        if row["review_id"] not in existing
    ]

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    questions = {
        "issue": {
            "type": "choice",
            "instructions": (
                "Choose the single best specific Spotify issue represented "
                "by this complaint. Use only the review text. "
                "Choose the most specific supported issue."
            ),
            "criteria": ISSUES,
        }
    }

    completed = 0
    failed = 0

    for i, item in enumerate(pending, 1):

        review_id = item["review_id"]
        review_text = source_text[review_id]

        payload = {
            "model": MODEL,
            "state": {
                "review_id": review_id,
                "review_text": review_text,
            },
            "questions": questions,
        }

        request_id = str(uuid.uuid4())
        start = time.time()

        try:
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
                        "role": "group",
                        "review_ids": [review_id],
                        "model": MODEL,
                        "phase": "initial",
                        "outcome": "failed",
                        "label_config": GROUP_LABEL_CONFIG,
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "runtime_seconds": round(elapsed, 3),
                        "error": response.text,
                    },
                )

                failed += 1
                print("FAILED:", review_id)
                continue

            data = response.json()
            usage = data.get("usage", {})
            answer = data["answers"]["issue"]

            combined_issue = answer["choice"]
            confidence = float(answer["confidence"])

            group_topic, sub_issue = combined_issue.split("__", 1)

            result = {
                "review_id": review_id,
                "enricher_topic": item["enricher_topic"],
                "group_topic": group_topic,
                "sub_issue": sub_issue,
                "combined_issue": combined_issue,
                "group_confidence": confidence,
                "topic_changed":
                    group_topic != item["enricher_topic"],
                "label_config": GROUP_LABEL_CONFIG,
            }

            append_jsonl(
                result_file,
                result,
            )

            append_jsonl(
                calls_file,
                {
                    "request_id": request_id,
                    "role": "group",
                    "review_ids": [review_id],
                    "model": data.get("model", MODEL),
                    "phase": "initial",
                    "outcome": "succeeded",
                    "label_config": GROUP_LABEL_CONFIG,
                    "input_tokens": usage.get("input_tokens", 0),
                    "output_tokens": usage.get("output_tokens", 0),
                    "runtime_seconds": round(elapsed, 3),
                },
            )

            completed += 1

            print(
                f"{i}/{len(pending)} "
                f"{review_id} "
                f"{item['enricher_topic']} -> "
                f"{combined_issue} "
                f"conf={confidence:.2f}"
            )

        except Exception as e:

            elapsed = time.time() - start

            append_jsonl(
                calls_file,
                {
                    "request_id": request_id,
                    "role": "group",
                    "review_ids": [review_id],
                    "model": MODEL,
                    "phase": "initial",
                    "outcome": "failed",
                    "label_config": GROUP_LABEL_CONFIG,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "runtime_seconds": round(elapsed, 3),
                    "error": str(e),
                },
            )

            failed += 1
            print("FAILED:", review_id, str(e))

    print("\n==============================")
    print("GROUPING DONE")
    print("==============================")
    print("Selected:", len(selected))
    print("Already grouped:", len(existing))
    print("Pending this run:", len(pending))
    print("Completed this run:", completed)
    print("Failed:", failed)
    print("Saved:", result_file)


if __name__ == "__main__":
    main()
