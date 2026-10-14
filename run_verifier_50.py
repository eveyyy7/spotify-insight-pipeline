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

INPUT_FILE = "verification_50.csv"
OUTPUT_FILE = "verifier_50_results.csv"

CACHE_FILE = "cache_verifier_50.json"
CALL_LOG_FILE = "calls_verifier_50.jsonl"

MODEL = "jev-latest"

# Keep verifier version separate from enricher
PROMPT_VERSION = "verifier_v1"
SCHEMA_VERSION = "verifier_v1"

MAX_RETRIES = 1
VERIFY_N = 50

if not API_KEY:
    raise ValueError(
        "TYPESAFE_API_KEY not found in .env"
    )


HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}


# =========================
# INDEPENDENT VERIFIER QUESTIONS
# =========================

QUESTIONS = {

    "topic": {
        "type": "choice",
        "instructions": (
            "Independently classify the primary Spotify product "
            "issue described in this review. "
            "Use only the review text. "
            "If multiple specific problems appear, choose the "
            "highest-severity problem; if severity is tied, "
            "choose the first mentioned."
        ),
        "criteria": {

            "access": (
                "Login, authentication, account access, "
                "or inability to enter or use the account."
            ),

            "usability": (
                "Interface, navigation, controls, ads, "
                "or general usability."
            ),

            "playback": (
                "Audio playback failures, crashes, lag, "
                "stopping, skipping, or related playback problems."
            ),

            "downloads": (
                "Offline listening or downloaded/saved "
                "music availability."
            ),

            "catalog": (
                "Search, content availability, recommendations, "
                "lyrics, artists, songs, or playlists."
            ),

            "billing": (
                "Price, charges, subscriptions, Premium access, "
                "paywalls, or billing."
            ),

            "support": (
                "Customer support, inability to contact support, "
                "or poor support response."
            ),

            "other": (
                "No clear fit with the listed Spotify "
                "product topics."
            ),
        },
    },

    "intent": {
        "type": "choice",
        "instructions": (
            "Independently determine the reviewer's intent "
            "using only the review text. "
            "Apply this precedence exactly: "
            "cancellation > complaint > request > praise > unclear."
        ),
        "criteria": {

            "cancellation": (
                "Explicitly cancelling, uninstalling, leaving, "
                "or stopping use."
            ),

            "complaint": (
                "Reports dissatisfaction or a product problem."
            ),

            "request": (
                "Asks for a product feature or change."
            ),

            "praise": (
                "Positively evaluates Spotify or a feature."
            ),

            "unclear": (
                "Intent cannot be determined reliably."
            ),
        },
    },

    "severity": {
        "type": "choice",
        "instructions": (
            "Independently assess functional severity using "
            "only the review text. "
            "Do not use star rating, emotional intensity, "
            "or cancellation alone to increase severity."
        ),
        "criteria": {

            "1": (
                "No problem, praise, unclear content, "
                "or pure feature request."
            ),

            "2": (
                "Annoyance or generic criticism."
            ),

            "3": (
                "Function is degraded or restricted, "
                "but some use remains."
            ),

            "4": (
                "A core task is blocked."
            ),

            "5": (
                "Explicit serious financial, privacy, "
                "or data harm."
            ),
        },
    },
}


# =========================
# HELPERS
# =========================

def utc_now():
    return datetime.now(
        timezone.utc
    ).isoformat()


def load_cache():

    if not os.path.exists(CACHE_FILE):
        return {}

    with open(
        CACHE_FILE,
        "r",
        encoding="utf-8",
    ) as f:

        content = f.read().strip()

        if not content:
            return {}

        return json.loads(content)


def save_cache(cache):

    with open(
        CACHE_FILE,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            cache,
            f,
            ensure_ascii=False,
            indent=2,
        )


def append_call_log(record):

    with open(
        CALL_LOG_FILE,
        "a",
        encoding="utf-8",
    ) as f:

        f.write(
            json.dumps(
                record,
                ensure_ascii=False,
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


# =========================
# VERIFIER API CALL
# =========================

def verify_review(
    review_id,
    review_text,
):

    payload = {
        "model": MODEL,

        "state": {
            "review_id": review_id,
            "review_text": review_text,
        },

        "questions": QUESTIONS,
    }

    last_error = None

    for attempt in range(
        1,
        MAX_RETRIES + 2,
    ):

        start = time.time()

        try:

            response = requests.post(
                f"{BASE_URL}/v1/systemone",
                headers=HEADERS,
                json=payload,
                timeout=30,
            )

            elapsed = (
                time.time() - start
            )

            log_record = {
                "timestamp": utc_now(),
                "review_id": review_id,
                "attempt": attempt,
                "stage": "verify",
                "model": MODEL,
                "prompt_version":
                    PROMPT_VERSION,
                "schema_version":
                    SCHEMA_VERSION,
                "status_code":
                    response.status_code,
                "runtime_seconds":
                    round(elapsed, 3),
            }

            if response.status_code == 200:

                data = response.json()

                usage = data.get(
                    "usage",
                    {},
                )

                log_record[
                    "outcome"
                ] = "success"

                log_record[
                    "input_tokens"
                ] = usage.get(
                    "input_tokens",
                    0,
                )

                log_record[
                    "output_tokens"
                ] = usage.get(
                    "output_tokens",
                    0,
                )

                append_call_log(
                    log_record
                )

                return data, attempt

            log_record[
                "outcome"
            ] = "failed"

            log_record[
                "error"
            ] = response.text

            append_call_log(
                log_record
            )

            last_error = (
                f"HTTP "
                f"{response.status_code}: "
                f"{response.text}"
            )

        except Exception as e:

            elapsed = (
                time.time() - start
            )

            append_call_log({
                "timestamp": utc_now(),
                "review_id": review_id,
                "attempt": attempt,
                "stage": "verify",
                "model": MODEL,
                "prompt_version":
                    PROMPT_VERSION,
                "schema_version":
                    SCHEMA_VERSION,
                "outcome": "exception",
                "runtime_seconds":
                    round(elapsed, 3),
                "error": str(e),
            })

            last_error = str(e)

        if attempt <= MAX_RETRIES:
            time.sleep(1)

    raise RuntimeError(
        "Verifier failed after retry: "
        f"{last_error}"
    )


# =========================
# RUN VERIFIER SAMPLE
# =========================

cache = load_cache()

results = []

cache_hits = 0
api_attempts = 0
retry_count = 0

total_input_tokens = 0
total_output_tokens = 0


with open(
    INPUT_FILE,
    newline="",
    encoding="utf-8",
) as f:

    reader = csv.DictReader(f)

    for i, row in enumerate(reader):

        if i >= VERIFY_N:
            break

        review_id = row[
            "review_id"
        ]

        review_text = row[
            "review_text"
        ]

        print(
            f"\n--- Verify {i + 1} ---"
        )

        print(review_id)
        print(review_text)

        cache_key = make_cache_key(
            review_text
        )

        try:

            if cache_key in cache:

                print("VERIFIER CACHE HIT")

                data = cache[
                    cache_key
                ]

                from_cache = True
                attempts_used = 0

                cache_hits += 1

            else:

                print(
                    "VERIFIER API CALL"
                )

                (
                    data,
                    attempts_used,
                ) = verify_review(
                    review_id,
                    review_text,
                )

                api_attempts += (
                    attempts_used
                )

                if attempts_used > 1:
                    retry_count += (
                        attempts_used - 1
                    )

                cache[
                    cache_key
                ] = data

                save_cache(cache)

                from_cache = False

            answers = data[
                "answers"
            ]

            topic = answers[
                "topic"
            ]["choice"]

            topic_conf = answers[
                "topic"
            ]["confidence"]

            intent = answers[
                "intent"
            ]["choice"]

            intent_conf = answers[
                "intent"
            ]["confidence"]

            severity = int(
                answers[
                    "severity"
                ]["choice"]
            )

            severity_conf = answers[
                "severity"
            ]["confidence"]

            usage = data.get(
                "usage",
                {},
            )

            if from_cache:

                input_tokens = 0
                output_tokens = 0

            else:

                input_tokens = (
                    usage.get(
                        "input_tokens",
                        0,
                    )
                )

                output_tokens = (
                    usage.get(
                        "output_tokens",
                        0,
                    )
                )

            total_input_tokens += (
                input_tokens
            )

            total_output_tokens += (
                output_tokens
            )

            results.append({

                "review_id":
                    review_id,

                "review_text":
                    review_text,

                "verifier_topic":
                    topic,

                "verifier_topic_confidence":
                    topic_conf,

                "verifier_intent":
                    intent,

                "verifier_intent_confidence":
                    intent_conf,

                "verifier_severity":
                    severity,

                "verifier_severity_confidence":
                    severity_conf,

                "cache_hit":
                    from_cache,

                "attempts":
                    attempts_used,

                "input_tokens":
                    input_tokens,

                "output_tokens":
                    output_tokens,

                "status":
                    "completed",
            })

            print(
                f"topic={topic} "
                f"intent={intent} "
                f"severity={severity} "
                f"attempts={attempts_used}"
            )

        except Exception as e:

            print(
                "ERROR:",
                str(e),
            )

            results.append({

                "review_id":
                    review_id,

                "review_text":
                    review_text,

                "verifier_topic":
                    "",

                "verifier_topic_confidence":
                    "",

                "verifier_intent":
                    "",

                "verifier_intent_confidence":
                    "",

                "verifier_severity":
                    "",

                "verifier_severity_confidence":
                    "",

                "cache_hit":
                    False,

                "attempts":
                    MAX_RETRIES + 1,

                "input_tokens":
                    0,

                "output_tokens":
                    0,

                "status":
                    "failed",
            })


# =========================
# SAVE
# =========================

fieldnames = [

    "review_id",
    "review_text",

    "verifier_topic",
    "verifier_topic_confidence",

    "verifier_intent",
    "verifier_intent_confidence",

    "verifier_severity",
    "verifier_severity_confidence",

    "cache_hit",
    "attempts",

    "input_tokens",
    "output_tokens",

    "status",
]


with open(
    OUTPUT_FILE,
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

print(
    "\n=============================="
)
print("VERIFIER DONE")
print(
    "=============================="
)

print(
    f"Saved to: {OUTPUT_FILE}"
)

print(
    "Completed:",
    sum(
        r["status"]
        == "completed"
        for r in results
    ),
)

print(
    "Failed:",
    sum(
        r["status"]
        == "failed"
        for r in results
    ),
)

print(
    f"Cache hits: "
    f"{cache_hits}"
)

print(
    f"API attempts: "
    f"{api_attempts}"
)

print(
    f"Retries: "
    f"{retry_count}"
)

print(
    f"Total input tokens: "
    f"{total_input_tokens}"
)

print(
    f"Total output tokens: "
    f"{total_output_tokens}"
)

print(
    f"Call log: "
    f"{CALL_LOG_FILE}"
)