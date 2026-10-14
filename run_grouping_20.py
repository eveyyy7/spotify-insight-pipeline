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

INPUT_FILE = "top4_complaints_10000.csv"
OUTPUT_FILE = "grouped_20_test.csv"

CACHE_FILE = "cache_grouping_20.json"
CALL_LOG_FILE = "calls_grouping_20.jsonl"

MODEL = "jev-latest"

PROMPT_VERSION = "issue_grouping_v1"
SCHEMA_VERSION = "issue_taxonomy_v1"

MAX_RETRIES = 1

if not API_KEY:
    raise ValueError(
        "TYPESAFE_API_KEY not found in .env"
    )


HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}


# =========================
# CLOSED ISSUE TAXONOMY
# =========================

ISSUE_CRITERIA = {

    # -------------------------
    # USABILITY
    # -------------------------

    "usability__playback_controls_restricted": (
        "User complains about inability or restrictions in selecting songs, "
        "skip, previous, replay, seek, shuffle, queue, or other playback controls, "
        "where the main framing is app usability/control behavior rather than "
        "explicit Premium pricing or paywall."
    ),

    "usability__ads_experience": (
        "Too many ads, disruptive ads, repeated ads, ads looping, "
        "or advertising that materially harms usability."
    ),

    "usability__navigation_ui_design": (
        "Problems with interface design, navigation, home screen layout, "
        "visual design, keyboard behavior, or general UI interaction."
    ),

    "usability__playlist_management": (
        "Difficulty adding, editing, organizing, or managing playlists, "
        "local songs, or playlist contents."
    ),

    "usability__feature_regression": (
        "A previously available usability feature disappeared or became "
        "materially worse after an update, and no more specific category fits."
    ),

    "usability__other_usability": (
        "Other clear usability complaint not covered above."
    ),


    # -------------------------
    # PLAYBACK
    # -------------------------

    "playback__playback_stops_randomly": (
        "Music or podcast playback randomly pauses, stops after one song, "
        "or stops unexpectedly during listening."
    ),

    "playback__cannot_start_playback": (
        "Song, playlist, or audio cannot start playing at all."
    ),

    "playback__wrong_unwanted_tracks": (
        "Spotify plays unwanted songs, songs outside the playlist, "
        "or otherwise plays the wrong content."
    ),

    "playback__skip_seek_restrictions": (
        "Playback-related inability to skip, seek, rewind, or move within tracks, "
        "where the complaint is primarily about playback behavior."
    ),

    "playback__crash_freeze_loading": (
        "Spotify crashes, freezes, hangs, or has severe playback loading delays."
    ),

    "playback__device_background_connection": (
        "Playback fails or stops when using another app, background mode, "
        "car audio, Bluetooth, or another connected device."
    ),

    "playback__other_playback": (
        "Other playback complaint not covered above."
    ),


    # -------------------------
    # BILLING
    # -------------------------

    "billing__premium_feature_paywall": (
        "A concrete feature such as selecting songs, previous track, seek, queue, "
        "timeline, lyrics, or another basic function is blocked behind Premium."
    ),

    "billing__premium_pressure_pricing": (
        "General complaint that Spotify is forcing users to buy Premium, "
        "is too expensive, or focuses too heavily on payment, without one "
        "specific blocked feature being the primary issue."
    ),

    "billing__discount_eligibility": (
        "Problems getting student or other subscription discounts "
        "or proving discount eligibility."
    ),

    "billing__subscription_entitlement": (
        "User paid or subscribed but Premium access or subscription entitlement "
        "is missing, incorrect, or not recognized."
    ),

    "billing__charge_payment_issue": (
        "Unexpected charge, payment problem, refund issue, duplicate charge, "
        "or other actual billing transaction problem."
    ),

    "billing__other_billing": (
        "Other billing or subscription complaint not covered above."
    ),


    # -------------------------
    # ACCESS
    # -------------------------

    "access__login_failure": (
        "User cannot log into Spotify or cannot access their account."
    ),

    "access__phone_number_login": (
        "Login specifically fails when using a phone number."
    ),

    "access__password_recovery": (
        "Password reset, account recovery, passwordless login, "
        "or retrieving login credentials fails."
    ),

    "access__unexpected_logout": (
        "Spotify unexpectedly or repeatedly logs the user out."
    ),

    "access__false_offline_connection": (
        "Spotify incorrectly says the device is offline or has no internet "
        "despite a working connection."
    ),

    "access__regional_availability": (
        "Spotify access fails because of country, geographic region, "
        "or location availability."
    ),

    "access__other_access": (
        "Other account access complaint not covered above."
    ),


    # -------------------------
    # OUTSIDE TOP 4 FALLBACKS
    # -------------------------

    "catalog__catalog_issue": (
        "The main complaint is actually about search, recommendations, lyrics, "
        "artists, songs, podcasts, content availability, or catalog discovery."
    ),

    "downloads__download_issue": (
        "The main complaint is actually about downloaded music "
        "or offline listening."
    ),

    "support__support_issue": (
        "The main complaint is actually about contacting support, "
        "support response, or inability to receive help."
    ),

    "other__other_issue": (
        "The complaint does not fit any of the defined issue groups."
    ),
}


QUESTIONS = {

    "issue_group": {
        "type": "choice",

        "instructions": (
            "Classify this Spotify complaint into exactly one issue group. "
            "Choose the most specific label supported by the review text. "
            "Do not rely on any previous classifier output. "
            "If multiple problems appear, choose the highest-severity specific "
            "problem; if severity is tied, choose the first mentioned. "
            "Distinguish Premium paywall complaints from usability complaints: "
            "when the user explicitly complains that a feature is blocked because "
            "Premium/payment is required, prefer a billing Premium label. "
            "Use the outside-top-4 fallback labels when the complaint is actually "
            "about catalog, downloads, support, or another issue."
        ),

        "criteria": ISSUE_CRITERIA,
    }
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
        encoding="utf-8"
    ) as f:

        content = f.read().strip()

        if not content:
            return {}

        return json.loads(content)


def save_cache(cache):

    with open(
        CACHE_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            cache,
            f,
            ensure_ascii=False,
            indent=2
        )


def append_call_log(record):

    with open(
        CALL_LOG_FILE,
        "a",
        encoding="utf-8"
    ) as f:

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


# =========================
# GROUPING API CALL
# =========================

def group_review(
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
        MAX_RETRIES + 2
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
                "stage": "group",
                "attempt": attempt,
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
                    {}
                )

                log_record[
                    "outcome"
                ] = "success"

                log_record[
                    "input_tokens"
                ] = usage.get(
                    "input_tokens",
                    0
                )

                log_record[
                    "output_tokens"
                ] = usage.get(
                    "output_tokens",
                    0
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

                "timestamp":
                    utc_now(),

                "review_id":
                    review_id,

                "stage":
                    "group",

                "attempt":
                    attempt,

                "model":
                    MODEL,

                "prompt_version":
                    PROMPT_VERSION,

                "schema_version":
                    SCHEMA_VERSION,

                "outcome":
                    "exception",

                "runtime_seconds":
                    round(elapsed, 3),

                "error":
                    str(e),
            })

            last_error = str(e)

        if attempt <= MAX_RETRIES:
            time.sleep(1)

    raise RuntimeError(
        "Grouping failed after retry: "
        f"{last_error}"
    )


# =========================
# RUN GROUPING
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
    encoding="utf-8"
) as f:

    reader = csv.DictReader(f)

    for i, row in enumerate(reader):

        if i >= 20:
            break

        review_id = row[
            "review_id"
        ]

        review_text = row[
            "review_text"
        ]

        enricher_topic = row[
            "topic"
        ]

        severity = row[
            "severity"
        ]

        sentiment = row[
            "sentiment"
        ]

        print(
            f"\n--- Group {i + 1} ---"
        )

        print(review_id)
        print(review_text)

        cache_key = make_cache_key(
            review_text
        )

        try:

            # -------------------------
            # CACHE
            # -------------------------

            if cache_key in cache:

                print(
                    "GROUP CACHE HIT"
                )

                data = cache[
                    cache_key
                ]

                cache_hits += 1
                from_cache = True
                attempts_used = 0

            else:

                print(
                    "GROUP API CALL"
                )

                (
                    data,
                    attempts_used
                ) = group_review(
                    review_id,
                    review_text
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


            # -------------------------
            # PARSE
            # -------------------------

            answer = data[
                "answers"
            ]["issue_group"]

            combined_issue = answer[
                "choice"
            ]

            group_confidence = answer[
                "confidence"
            ]

            if "__" not in combined_issue:

                raise ValueError(
                    "Unexpected issue label: "
                    f"{combined_issue}"
                )

            (
                group_topic,
                sub_issue
            ) = combined_issue.split(
                "__",
                1
            )


            # -------------------------
            # TOKEN USAGE
            # -------------------------

            usage = data.get(
                "usage",
                {}
            )

            if from_cache:

                input_tokens = 0
                output_tokens = 0

            else:

                input_tokens = (
                    usage.get(
                        "input_tokens",
                        0
                    )
                )

                output_tokens = (
                    usage.get(
                        "output_tokens",
                        0
                    )
                )

            total_input_tokens += (
                input_tokens
            )

            total_output_tokens += (
                output_tokens
            )


            # -------------------------
            # SAVE RESULT
            # -------------------------

            topic_changed = (
                enricher_topic
                != group_topic
            )

            results.append({

                "review_id":
                    review_id,

                "review_text":
                    review_text,

                "enricher_topic":
                    enricher_topic,

                "group_topic":
                    group_topic,

                "sub_issue":
                    sub_issue,

                "combined_issue":
                    combined_issue,

                "group_confidence":
                    group_confidence,

                "topic_changed":
                    topic_changed,

                "severity":
                    severity,

                "sentiment":
                    sentiment,

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
                f"group_topic="
                f"{group_topic} "
                f"sub_issue="
                f"{sub_issue} "
                f"confidence="
                f"{group_confidence:.3f} "
                f"topic_changed="
                f"{topic_changed}"
            )


        except Exception as e:

            print(
                "ERROR:",
                str(e)
            )

            results.append({

                "review_id":
                    review_id,

                "review_text":
                    review_text,

                "enricher_topic":
                    enricher_topic,

                "group_topic":
                    "",

                "sub_issue":
                    "",

                "combined_issue":
                    "",

                "group_confidence":
                    "",

                "topic_changed":
                    "",

                "severity":
                    severity,

                "sentiment":
                    sentiment,

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
# SAVE CSV
# =========================

fieldnames = [

    "review_id",
    "review_text",

    "enricher_topic",
    "group_topic",
    "sub_issue",
    "combined_issue",

    "group_confidence",
    "topic_changed",

    "severity",
    "sentiment",

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
    encoding="utf-8"
) as f:

    writer = csv.DictWriter(
        f,
        fieldnames=fieldnames
    )

    writer.writeheader()
    writer.writerows(
        results
    )


# =========================
# SUMMARY
# =========================

completed = sum(
    r["status"] == "completed"
    for r in results
)

failed = sum(
    r["status"] == "failed"
    for r in results
)

topic_changes = sum(
    r["topic_changed"] is True
    for r in results
)


print(
    "\n=============================="
)

print(
    "GROUPING DONE"
)

print(
    "=============================="
)

print(
    f"Saved to: "
    f"{OUTPUT_FILE}"
)

print(
    f"Completed: "
    f"{completed}"
)

print(
    f"Failed: "
    f"{failed}"
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
    f"Topic changes: "
    f"{topic_changes}"
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