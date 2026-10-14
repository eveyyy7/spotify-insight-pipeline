import os
import json
import time
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("TYPESAFE_API_KEY")

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}

MAX_RETRIES = 1

# 故意写错 endpoint，制造 temporary failure
BAD_URL = "https://api.typesafe.ai/v1/systemone-bad-endpoint"

payload = {
    "model": "jev-latest",
    "state": {
        "review_id": "retry-test",
        "review_text": "Great app"
    },
    "questions": {
        "topic": {
            "type": "choice",
            "instructions": "Choose the primary Spotify product issue.",
            "criteria": {
                "other": "No specific product issue."
            }
        }
    }
}

for attempt in range(1, MAX_RETRIES + 2):

    print(f"Attempt {attempt}")

    try:
        response = requests.post(
            BAD_URL,
            headers=HEADERS,
            json=payload,
            timeout=10,
        )

        print("status:", response.status_code)

        if response.status_code == 200:
            print("SUCCESS")
            break

        print("FAILED:", response.text)

    except Exception as e:
        print("EXCEPTION:", str(e))

    if attempt <= MAX_RETRIES:
        print("Retrying in 1 second...")
        time.sleep(1)
    