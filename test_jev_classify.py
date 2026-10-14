import os
import csv
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("TYPESAFE_API_KEY")
BASE_URL = "https://api.typesafe.ai"

if not API_KEY:
    raise ValueError("TYPESAFE_API_KEY not found")

# 读取 checkpoint_500.csv 第一条 review
with open("checkpoint_500.csv", newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    row = next(reader)

review_id = row["review_id"]
review_text = row["review_text"]

print("review_id:", review_id)
print("review_text:", review_text)
print()

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}

payload = {
    "model": "jev-latest",
    "state": {
        "review_id": review_id,
        "review_text": review_text
    },
"questions": {
    "topic": {
        "type": "choice",
        "instructions": "Choose the primary Spotify product issue in this review.",
        "criteria": {
            "access": "Login, account access, authentication, or inability to access the account.",
            "usability": "Controls, navigation, interface, ads, or general app usability.",
            "playback": "Playback failures, crashes, lag, stopping, skipping, or audio playback problems.",
            "downloads": "Offline listening, downloaded music, or saved music availability.",
            "catalog": "Content availability, search, recommendations, lyrics, artists, songs, or playlists.",
            "billing": "Price, charges, paywalls, subscriptions, Premium entitlement, or billing problems.",
            "support": "Customer support contact, support response, or inability to get help.",
            "other": "Anything that does not clearly fit the other product topics."
        }
    },

    "intent": {
        "type": "choice",
        "instructions": "Choose the review intent. Apply precedence: cancellation > complaint > request > praise > unclear.",
        "criteria": {
            "cancellation": "The reviewer explicitly says they are cancelling, leaving, uninstalling, or stopping use.",
            "complaint": "The reviewer reports dissatisfaction or a product problem.",
            "request": "The reviewer asks for a feature or change.",
            "praise": "The reviewer positively evaluates the product.",
            "unclear": "The intent cannot be determined reliably."
        }
    },

    "severity": {
        "type": "choice",
        "instructions": "Choose severity. Do not infer severity from star rating or emotional language.",
        "criteria": {
            "1": "No reported problem, praise, unclear content, or pure feature request.",
            "2": "Annoyance or generic criticism.",
            "3": "Function is degraded or restricted, but some use remains.",
            "4": "A core task is clearly blocked.",
            "5": "Explicit serious financial, privacy, or data harm."
        }
    },

    "sentiment": {
        "type": "score",
        "instructions": "Rate the overall sentiment of this Spotify review.",
        "criteria": [
            "Strongly negative",
            "Negative",
            "Neutral or unclear",
            "Positive",
            "Strongly positive"
        ]
    }
}
}

response = requests.post(
    f"{BASE_URL}/v1/systemone",
    headers=headers,
    json=payload,
    timeout=30,
)

print("status:", response.status_code)
print(response.text)