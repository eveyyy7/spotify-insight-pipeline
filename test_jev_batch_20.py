import os
import csv
import json
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("TYPESAFE_API_KEY")

if not API_KEY:
    raise ValueError("TYPESAFE_API_KEY not found in .env")

URL = "https://api.typesafe.ai/v1/systemone"

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}

MODEL = "jev-latest"


QUESTIONS = {
    "topic": {
        "type": "choice",
        "instructions": (
            "Choose the primary Spotify product issue. "
            "If multiple issues are present, choose the highest-severity "
            "specific problem; if tied, choose the first mentioned."
        ),
        "criteria": {
            "access": "Login, signup, password, authentication, or account access.",
            "usability": "Navigation, controls, layout, queue or playlist management, or ad interruptions.",
            "playback": "Playback failure, crashes, lag, connection failures, or audio problems.",
            "downloads": "Downloading, saved music, or offline listening.",
            "catalog": "Missing content, search, discovery, recommendations, or lyrics.",
            "billing": "Price, charges, subscriptions, paywalls, Premium entitlement, or Premium-only controls.",
            "support": "Contacting support or support response.",
            "other": "General praise or criticism, unrelated content, or no supported specific topic.",
        },
    },

    "intent": {
        "type": "choice",
        "instructions": (
            "Choose intent using precedence: "
            "cancellation > complaint > request > praise > unclear."
        ),
        "criteria": {
            "cancellation": "Explicitly leaving, uninstalling, cancelling, or stopping use.",
            "complaint": "Negative experience or reported product problem.",
            "request": "Desired product change without a reported failure.",
            "praise": "Positive evaluation.",
            "unclear": "Intent cannot be reliably determined.",
        },
    },

    "severity": {
        "type": "choice",
        "instructions": (
            "Choose severity based only on supported functional impact. "
            "Do not raise severity because of anger, rating, or cancellation alone."
        ),
        "criteria": {
            "1": "No problem, praise, unclear content, or pure feature request.",
            "2": "Dislike, generic criticism, minor annoyance, or cosmetic issue.",
            "3": "Function degraded or restricted, but some use or workaround remains.",
            "4": "A clearly blocked core task.",
            "5": "Explicit serious financial, privacy, or data harm.",
        },
    },

    "sentiment": {
        "type": "score",
        "instructions": "Rate overall sentiment of the Spotify review.",
        "criteria": [
            "Strongly negative",
            "Negative",
            "Neutral or unclear",
            "Positive",
            "Strongly positive",
        ],
    },
}


# Read first 20 reviews
with open(
    "cost_100.csv",
    newline="",
    encoding="utf-8"
) as f:
    rows = list(csv.DictReader(f))[:20]


states = [
    {
        "review_id": r["review_id"],
        "review_text": r["review_text"],
    }
    for r in rows
]


payload = {
    "model": MODEL,
    "state": states,
    "questions": QUESTIONS,
}


print("Sending batch with reviews:", len(states))

response = requests.post(
    URL,
    headers=HEADERS,
    json=payload,
    timeout=120,
)

print("Status:", response.status_code)

if response.status_code != 200:
    print(response.text)
    raise SystemExit(1)


data = response.json()

print("\n==============================")
print("RAW RESPONSE KEYS")
print("==============================")
print(list(data.keys()))


print("\n==============================")
print("USAGE")
print("==============================")
print(json.dumps(
    data.get("usage", {}),
    indent=2
))


print("\n==============================")
print("ANSWERS TYPE")
print("==============================")

answers = data.get("answers")

print("type:", type(answers).__name__)


print("\n==============================")
print("RAW ANSWERS")
print("==============================")

print(
    json.dumps(
        answers,
        ensure_ascii=False,
        indent=2
    )[:12000]
)


with open(
    "jev_batch_20_raw.json",
    "w",
    encoding="utf-8"
) as f:
    json.dump(
        data,
        f,
        ensure_ascii=False,
        indent=2
    )


print("\nSaved: jev_batch_20_raw.json")