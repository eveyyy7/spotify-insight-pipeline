import os
import csv
import json
import time
import hashlib
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv


# =========================
# CONFIG
# =========================

load_dotenv()

API_KEY = os.getenv("TYPESAFE_API_KEY")
BASE_URL = "https://api.typesafe.ai"

CACHE_FILE = "cache.json"
CALL_LOG_FILE = "calls.jsonl"

MODEL = "jev-latest"
PROMPT_VERSION = "v1"
SCHEMA_VERSION = "v1"

MAX_RETRIES = 1

if not API_KEY:
    raise ValueError("TYPESAFE_API_KEY not found in .env")


HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}


# =========================
# JEV QUESTIONS
# =========================

QUESTIONS = {
    "topic": {
        "type": "choice",
        "instructions": (
            "Choose the primary Spotify product issue in this review. "
            "If multiple issues are present, choose the highest-severity "
            "specific problem; if tied, choose the first mentioned."
        ),
        "criteria": {
            "access": (
                "Login, account access, authentication, "
                "or inability to access the account."
            ),
            "usability": (
                "Controls, navigation, interface, ads, "
                "or general app usability."
            ),
            "playback": (
                "Playback failures, crashes, lag, stopping, "
                "skipping, or audio playback problems."
            ),
            "downloads": (
                "Offline listening, downloaded music, "
                "or saved music availability."
            ),
            "catalog": (
                "Content availability, search, recommendations, "
                "lyrics, artists, songs, or playlists."
            ),
            "billing": (
                "Price, charges, paywalls, subscriptions, "
                "Premium entitlement, or billing problems."
            ),
            "support": (
                "Customer support contact, support response, "
                "or inability to get help."
            ),
            "other": (
                "Anything that does not clearly fit "
                "the other product topics."
            ),
        },
    },

    "intent": {
        "type": "choice",
        "instructions": (
            "Choose the review intent. Apply precedence exactly: "
            "cancellation > complaint > request > praise > unclear."
        ),
        "criteria": {
            "cancellation": (
                "The reviewer explicitly says they are cancelling, "
                "leaving, uninstalling, or stopping use."
            ),
            "complaint": (
                "The reviewer reports dissatisfaction "
                "or a product problem."
            ),
            "request": (
                "The reviewer asks for a feature or change."
            ),
            "praise": (
                "The reviewer positively evaluates "
                "the product or a feature."
            ),
            "unclear": (
                "The intent cannot be determined reliably."
            ),
        },
    },

    "severity": {
        "type": "choice",
        "instructions": (
            "Choose severity using only the reported functional impact. "
            "Do not infer severity from star rating, angry language, "
            "or cancellation intent alone."
        ),
        "criteria": {
            "1": (
                "No reported problem, praise, unclear content, "
                "or a pure feature request."
            ),
            "2": (
                "Annoyance or generic criticism."
            ),
            "3": (
                "A function is degraded or restricted, "
                "but some use remains."
            ),
            "4": (
                "A core task is clearly blocked."
            ),
            "5": (
                "Explicit serious financial, privacy, or data harm."
            ),
        },
    },

    "sentiment": {
        "type": "score",
        "instructions": (
            "Rate the overall sentiment of this Spotify review."
        ),
        "criteria": [
            "Strongly negative",
            "Negative",
            "Neutral or unclear",
            "Positive",
            "Strongly positive",
        ],
    },
}


# =========================
# HELPERS
# =========================

def utc_now():
    return datetime.now(timezone.utc).isoformat()


def load_cache():
    if not os.path.exists(CACHE_FILE):
        return {}

    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        content = f.read().strip()

        if not content:
            return {}

        return json.loads(content)


def save_cache(cache):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(
            cache,
            f,
            ensure_ascii=False,
            indent=2
        )


def append_call_log(record):
    with open(CALL_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                record,
                ensure_ascii=False
            )
            + "\n"
        )


def make_cache_key(review_text):
    raw = "|".join([
        review_text,
        MODEL,
        PROMPT_VERSION,
        SCHEMA_VERSION,
    ])

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


def sentiment_to_minus1_plus1(score):
    return round(score / 2 - 1, 3)


# =========================
# JEV CALL WITH RETRY
# =========================

def classify_review(review_id, review_text):
    payload = {
        "model": MODEL,
        "state": {
            "review_id": review_id,
            "review_text": review_text,
        },
        "questions": QUESTIONS,
    }

    last_error = None

    # MAX_RETRIES = 1 means:
    # attempt 1 + at most one retry = 2 attempts total
    for attempt in range(1, MAX_RETRIES + 2):

        start = time.time()

        try:
            response = requests.post(
                f"{BASE_URL}/v1/systemone",
                headers=HEADERS,
                json=payload,
                timeout=30,
            )

            elapsed = time.time() - start

            log_record = {
                "timestamp": utc_now(),
                "review_id": review_id,
                "attempt": attempt,
                "model": MODEL,
                "prompt_version": PROMPT_VERSION,
                "schema_version": SCHEMA_VERSION,
                "status_code": response.status_code,
                "runtime_seconds": round(elapsed, 3),
            }

            if response.status_code == 200:

                data = response.json()
                usage = data.get("usage", {})

                log_record["outcome"] = "success"
                log_record["input_tokens"] = usage.get(
                    "input_tokens", 0
                )
                log_record["output_tokens"] = usage.get(
                    "output_tokens", 0
                )

                append_call_log(log_record)

                return data, attempt

            else:

                log_record["outcome"] = "failed"
                log_record["error"] = response.text

                append_call_log(log_record)

                last_error = (
                    f"HTTP {response.status_code}: "
                    f"{response.text}"
                )

        except Exception as e:

            elapsed = time.time() - start

            append_call_log({
                "timestamp": utc_now(),
                "review_id": review_id,
                "attempt": attempt,
                "model": MODEL,
                "prompt_version": PROMPT_VERSION,
                "schema_version": SCHEMA_VERSION,
                "outcome": "exception",
                "runtime_seconds": round(elapsed, 3),
                "error": str(e),
            })

            last_error = str(e)

        # retry only when another attempt remains
        if attempt <= MAX_RETRIES:
            time.sleep(1)

    raise RuntimeError(
        f"Jev failed after retry: {last_error}"
    )


# =========================
# RUN 10 REVIEWS
# =========================

cache = load_cache()

results = []

total_input_tokens = 0
total_output_tokens = 0

cache_hits = 0
api_attempts = 0
retry_count = 0


with open(
    "checkpoint_500.csv",
    newline="",
    encoding="utf-8",
) as f:

    reader = csv.DictReader(f)

    for i, row in enumerate(reader):

        if i >= 10:
            break

        review_id = row["review_id"]
        review_text = row["review_text"]

        print(f"\n--- Review {i + 1} ---")
        print(review_id)
        print(review_text)

        cache_key = make_cache_key(review_text)

        try:

            # -------------------------
            # CACHE HIT
            # -------------------------

            if cache_key in cache:

                print("CACHE HIT")

                data = cache[cache_key]

                cache_hits += 1
                from_cache = True
                attempts_used = 0

            # -------------------------
            # NEW API CALL
            # -------------------------

            else:

                print("API CALL")

                data, attempts_used = classify_review(
                    review_id,
                    review_text,
                )

                api_attempts += attempts_used

                if attempts_used > 1:
                    retry_count += (
                        attempts_used - 1
                    )

                cache[cache_key] = data
                save_cache(cache)

                from_cache = False

            # -------------------------
            # PARSE ANSWERS
            # -------------------------

            answers = data["answers"]

            topic = answers["topic"]["choice"]
            topic_conf = answers[
                "topic"
            ]["confidence"]

            intent = answers["intent"]["choice"]
            intent_conf = answers[
                "intent"
            ]["confidence"]

            severity = int(
                answers["severity"]["choice"]
            )
            severity_conf = answers[
                "severity"
            ]["confidence"]

            sentiment_score = answers[
                "sentiment"
            ]["score"]

            sentiment = (
                sentiment_to_minus1_plus1(
                    sentiment_score
                )
            )

            sentiment_conf = answers[
                "sentiment"
            ]["confidence"]

            # -------------------------
            # USAGE
            # -------------------------

            usage = data.get("usage", {})

            if from_cache:
                input_tokens = 0
                output_tokens = 0
            else:
                input_tokens = usage.get(
                    "input_tokens", 0
                )
                output_tokens = usage.get(
                    "output_tokens", 0
                )

            total_input_tokens += input_tokens
            total_output_tokens += output_tokens

            # -------------------------
            # NEEDS REVIEW
            # temporary development rule
            # -------------------------

            min_conf = min(
                topic_conf,
                intent_conf,
                severity_conf,
                sentiment_conf,
            )

            needs_review = min_conf < 0.60

            needs_review_reason = (
                "low_confidence"
                if needs_review
                else ""
            )

            # -------------------------
            # RESULT
            # -------------------------

            result = {
                "review_id": review_id,
                "review_text": review_text,

                "topic": topic,
                "topic_confidence": topic_conf,

                "intent": intent,
                "intent_confidence": intent_conf,

                "severity": severity,
                "severity_confidence": severity_conf,

                "sentiment": sentiment,
                "sentiment_raw_score": (
                    sentiment_score
                ),
                "sentiment_confidence": (
                    sentiment_conf
                ),

                # temporary placeholder
                "entities": [],

                # valid exact substring
                "evidence_quote": review_text,

                "needs_review": needs_review,
                "needs_review_reason": (
                    needs_review_reason
                ),

                "cache_hit": from_cache,
                "attempts": attempts_used,

                "input_tokens": input_tokens,
                "output_tokens": output_tokens,

                "status": "completed",
            }

            results.append(result)

            print(
                f"topic={topic} "
                f"intent={intent} "
                f"severity={severity} "
                f"sentiment={sentiment} "
                f"needs_review={needs_review} "
                f"attempts={attempts_used}"
            )

        except Exception as e:

            print("ERROR:", str(e))

            results.append({
                "review_id": review_id,
                "review_text": review_text,

                "topic": "",
                "topic_confidence": "",

                "intent": "",
                "intent_confidence": "",

                "severity": "",
                "severity_confidence": "",

                "sentiment": "",
                "sentiment_raw_score": "",
                "sentiment_confidence": "",

                "entities": [],
                "evidence_quote": review_text,

                "needs_review": True,
                "needs_review_reason": (
                    "processing_error"
                ),

                "cache_hit": False,
                "attempts": MAX_RETRIES + 1,

                "input_tokens": 0,
                "output_tokens": 0,

                "status": "failed",
            })


# =========================
# SAVE RESULTS
# =========================

output_file = "jev_10_results.csv"

fieldnames = [
    "review_id",
    "review_text",

    "topic",
    "topic_confidence",

    "intent",
    "intent_confidence",

    "severity",
    "severity_confidence",

    "sentiment",
    "sentiment_raw_score",
    "sentiment_confidence",

    "entities",
    "evidence_quote",

    "needs_review",
    "needs_review_reason",

    "cache_hit",
    "attempts",

    "input_tokens",
    "output_tokens",

    "status",
]


with open(
    output_file,
    "w",
    newline="",
    encoding="utf-8",
) as f:

    writer = csv.DictWriter(
        f,
        fieldnames=fieldnames,
    )

    writer.writeheader()
    writer.writerows(results)


# =========================
# SUMMARY
# =========================

print("\n==============================")
print("DONE")
print("==============================")

print(f"Saved to: {output_file}")

print(
    "Completed:",
    sum(
        r["status"] == "completed"
        for r in results
    ),
)

print(
    "Failed:",
    sum(
        r["status"] == "failed"
        for r in results
    ),
)

print(f"Cache hits: {cache_hits}")
print(f"API attempts: {api_attempts}")
print(f"Retries: {retry_count}")

print(
    f"Total input tokens: "
    f"{total_input_tokens}"
)

print(
    f"Total output tokens: "
    f"{total_output_tokens}"
)

print(f"Call log: {CALL_LOG_FILE}")