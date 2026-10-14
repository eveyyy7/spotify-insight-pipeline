import os
import csv
import json
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("TYPESAFE_API_KEY")
URL = "https://api.typesafe.ai/v1/systemone"

if not API_KEY:
    raise ValueError("TYPESAFE_API_KEY not found in .env")

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}

MODEL = "jev-latest"


QUESTIONS = {
    "topic": {
        "type": "choice",
        "instructions": (
            "Classify the primary issue. "
            "Highest supported severity wins; tie = first specific issue."
        ),
        "criteria": {
            "access": "login/signup/password/account access",
            "usability": "UI/navigation/controls/queue/playlist/ads",
            "playback": "play failure/crash/lag/connection/audio",
            "downloads": "download/offline/saved music",
            "catalog": "songs/artists/search/recs/lyrics/content",
            "billing": "price/charge/subscription/paywall/Premium-only controls",
            "support": "customer support/help response",
            "other": "general praise/criticism/unrelated/no specific issue",
        },
    },

    "intent": {
        "type": "choice",
        "instructions": (
            "Intent precedence: cancellation > complaint > request > praise > unclear."
        ),
        "criteria": {
            "cancellation": "explicit leaving/cancelling/uninstalling/stopping",
            "complaint": "negative experience or product problem",
            "request": "desired change without reported failure",
            "praise": "positive evaluation",
            "unclear": "cannot determine",
        },
    },

    "severity": {
        "type": "choice",
        "instructions": (
            "Functional impact only. Do not use anger, stars, or cancellation alone."
        ),
        "criteria": {
            "1": "no problem/praise/unclear/pure request",
            "2": "annoyance/generic criticism/cosmetic",
            "3": "function degraded/restricted but some use remains",
            "4": "core task blocked",
            "5": "serious financial/privacy/data harm",
        },
    },

    "sentiment": {
        "type": "score",
        "instructions": "Overall review sentiment.",
        "criteria": [
            "Strongly negative",
            "Negative",
            "Neutral or unclear",
            "Positive",
            "Strongly positive",
        ],
    },
}


def sentiment_to_minus1_plus1(score):
    return round(score / 2 - 1, 3)


with open(
    "cost_100.csv",
    newline="",
    encoding="utf-8"
) as f:
    rows = list(csv.DictReader(f))[:20]


results = []

total_input = 0
total_output = 0


for i, row in enumerate(rows, 1):

    review_id = row["review_id"]
    review_text = row["review_text"]

    payload = {
        "model": MODEL,
        "state": {
            "review_id": review_id,
            "review_text": review_text,
        },
        "questions": QUESTIONS,
    }

    print(f"\n--- {i}/20 ---")
    print(review_text)

    response = requests.post(
        URL,
        headers=HEADERS,
        json=payload,
        timeout=30,
    )

    print("status:", response.status_code)

    if response.status_code != 200:
        print("ERROR:", response.text)
        continue

    data = response.json()
    answers = data["answers"]
    usage = data.get("usage", {})

    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)

    total_input += input_tokens
    total_output += output_tokens

    topic = answers["topic"]["choice"]
    intent = answers["intent"]["choice"]
    severity = int(answers["severity"]["choice"])
    sentiment = sentiment_to_minus1_plus1(
        answers["sentiment"]["score"]
    )

    results.append({
        "review_id": review_id,
        "review_text": review_text,
        "topic": topic,
        "intent": intent,
        "severity": severity,
        "sentiment": sentiment,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    })

    print(
        f"topic={topic} "
        f"intent={intent} "
        f"severity={severity} "
        f"sentiment={sentiment} "
        f"input={input_tokens}"
    )


with open(
    "compact_20_results.csv",
    "w",
    newline="",
    encoding="utf-8"
) as f:

    fieldnames = [
        "review_id",
        "review_text",
        "topic",
        "intent",
        "severity",
        "sentiment",
        "input_tokens",
        "output_tokens",
    ]

    writer = csv.DictWriter(
        f,
        fieldnames=fieldnames
    )

    writer.writeheader()
    writer.writerows(results)


print("\n==============================")
print("COMPACT TEST DONE")
print("==============================")

print("Completed:", len(results))
print("Total input tokens:", total_input)
print("Total output tokens:", total_output)

if results:
    print(
        "Average input tokens/review:",
        round(total_input / len(results), 1)
    )

print("Saved: compact_20_results.csv")