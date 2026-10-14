# Archived single-worker implementation retained for audit history.
import os
import csv
import json
import time
import uuid
import sqlite3
import hashlib
import argparse
import random
import threading
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv


SOURCE_FIELDS = [
    "review_id",
    "review_text",
    "review_rating",
    "review_likes",
    "app_version",
    "review_timestamp",
]

MODEL = "jev-latest"
PROMPT_VERSION = "v1"
SCHEMA_VERSION = "v1"
LABEL_CONFIG = f"{MODEL}+prompt-{PROMPT_VERSION}+schema-{SCHEMA_VERSION}"

MAX_RETRIES = 1
REQUEST_TIMEOUT = 30
LOW_CONF_THRESHOLD = 0.50

# Provider request batches intentionally contain exactly one review.  A prior
# multi-state pilot returned one aggregate answer instead of one validated
# answer per review.  Keeping provider batches at one avoids silent ID loss;
# CSV/SQLite queueing and worker concurrency still operate in batches.
PROVIDER_REQUEST_BATCH_SIZE = 1
DEFAULT_WORKERS = 2
DEFAULT_REQUESTS_PER_MINUTE = 300
DEFAULT_TOKENS_PER_MINUTE = 120_000
DEFAULT_ESTIMATED_TOKENS_PER_REQUEST = 1_500
DEFAULT_WORST_CASE_COST_PER_REVIEW = 10.0 / 100_000

HIGH_RISK_TOPICS = {"billing", "access", "playback"}


QUESTIONS = {
    "topic": {
        "type": "choice",
        "instructions": (
            "Choose the primary Spotify product issue in this review. "
            "If multiple issues are present, choose the highest-severity "
            "specific problem; if tied, choose the first mentioned."
        ),
        "criteria": {
            "access": "Login, account access, authentication, or inability to access the account.",
            "usability": "Controls, navigation, interface, ads, or general app usability.",
            "playback": "Playback failures, crashes, lag, stopping, skipping, or audio playback problems.",
            "downloads": "Offline listening, downloaded music, or saved music availability.",
            "catalog": "Content availability, search, recommendations, lyrics, artists, songs, or playlists.",
            "billing": "Price, charges, paywalls, subscriptions, Premium entitlement, or billing problems.",
            "support": "Customer support contact, support response, or inability to get help.",
            "other": "Anything that does not clearly fit the other product topics.",
        },
    },
    "intent": {
        "type": "choice",
        "instructions": (
            "Choose the review intent. Apply precedence exactly: "
            "cancellation > complaint > request > praise > unclear."
        ),
        "criteria": {
            "cancellation": "The reviewer explicitly says they are cancelling, leaving, uninstalling, or stopping use.",
            "complaint": "The reviewer reports dissatisfaction or a product problem.",
            "request": "The reviewer asks for a feature or change.",
            "praise": "The reviewer positively evaluates the product or a feature.",
            "unclear": "The intent cannot be determined reliably.",
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
            "1": "No reported problem, praise, unclear content, or a pure feature request.",
            "2": "Annoyance or generic criticism.",
            "3": "A function is degraded or restricted, but some use remains.",
            "4": "A core task is clearly blocked.",
            "5": "Explicit serious financial, privacy, or data harm.",
        },
    },
    "sentiment": {
        "type": "score",
        "instructions": "Rate the overall sentiment of this Spotify review.",
        "criteria": [
            "Strongly negative",
            "Negative",
            "Neutral or unclear",
            "Positive",
            "Strongly positive",
        ],
    },
}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def sentiment_to_minus1_plus1(score):
    return round(score / 2 - 1, 3)


def source_row_sha(row):
    values = [row.get(field, "") for field in SOURCE_FIELDS]
    compact = json.dumps(
        values,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(compact.encode("utf-8")).hexdigest()


def text_cache_key(review_text):
    raw = "|".join([review_text, LABEL_CONFIG])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def calculate_needs_review(
    topic,
    intent,
    severity,
    topic_conf,
    intent_conf,
    severity_conf,
    sentiment_conf,
):
    reasons = []

    if min(
        topic_conf,
        intent_conf,
        severity_conf,
        sentiment_conf,
    ) < LOW_CONF_THRESHOLD:
        reasons.append("low_confidence")

    if severity >= 4 and topic in HIGH_RISK_TOPICS:
        reasons.append("high_risk_severity")

    if intent == "cancellation" and severity >= 3:
        reasons.append("high_risk_cancellation")

    return bool(reasons), reasons


def open_db(path):
    conn = sqlite3.connect(path)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS records (
            source_index INTEGER PRIMARY KEY,
            review_id TEXT UNIQUE NOT NULL,
            source_sha256 TEXT NOT NULL,
            review_text TEXT NOT NULL,
            status TEXT NOT NULL,
            reason TEXT,
            topic TEXT,
            intent TEXT,
            sentiment REAL,
            severity INTEGER,
            entities_json TEXT,
            evidence_quote TEXT,
            needs_review INTEGER,
            needs_review_reason TEXT,
            label_config TEXT,
            cache_source_id TEXT,
            topic_confidence REAL,
            intent_confidence REAL,
            severity_confidence REAL,
            sentiment_confidence REAL,
            created_at TEXT,
            updated_at TEXT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS result_cache (
            cache_key TEXT PRIMARY KEY,
            review_text TEXT NOT NULL,
            source_review_id TEXT NOT NULL,
            topic TEXT NOT NULL,
            intent TEXT NOT NULL,
            sentiment REAL NOT NULL,
            severity INTEGER NOT NULL,
            entities_json TEXT NOT NULL,
            evidence_quote TEXT NOT NULL,
            needs_review INTEGER NOT NULL,
            needs_review_reason TEXT,
            topic_confidence REAL,
            intent_confidence REAL,
            severity_confidence REAL,
            sentiment_confidence REAL,
            label_config TEXT NOT NULL
        )
    """)

    conn.commit()
    return conn


def get_existing_record(conn, review_id):
    return conn.execute(
        "SELECT status FROM records WHERE review_id = ?",
        (review_id,),
    ).fetchone()


def get_cached_result(conn, cache_key):
    row = conn.execute(
        """
        SELECT
            source_review_id,
            topic,
            intent,
            sentiment,
            severity,
            entities_json,
            evidence_quote,
            needs_review,
            needs_review_reason,
            topic_confidence,
            intent_confidence,
            severity_confidence,
            sentiment_confidence,
            label_config
        FROM result_cache
        WHERE cache_key = ?
        """,
        (cache_key,),
    ).fetchone()

    if not row:
        return None

    return {
        "source_review_id": row[0],
        "topic": row[1],
        "intent": row[2],
        "sentiment": row[3],
        "severity": row[4],
        "entities_json": row[5],
        "evidence_quote": row[6],
        "needs_review": row[7],
        "needs_review_reason": row[8],
        "topic_confidence": row[9],
        "intent_confidence": row[10],
        "severity_confidence": row[11],
        "sentiment_confidence": row[12],
        "label_config": row[13],
    }


def append_jsonl(path, record):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def classify_review(
    api_key,
    review_id,
    review_text,
    calls_file,
    phase,
):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": MODEL,
        "state": {
            "review_id": review_id,
            "review_text": review_text,
        },
        "questions": QUESTIONS,
    }

    last_error = None

    for attempt in range(1, MAX_RETRIES + 2):
        request_id = str(uuid.uuid4())
        start = time.time()

        try:
            response = requests.post(
                "https://api.typesafe.ai/v1/systemone",
                headers=headers,
                json=payload,
                timeout=REQUEST_TIMEOUT,
            )

            elapsed = time.time() - start

            if response.status_code == 200:
                data = response.json()
                usage = data.get("usage", {})

                append_jsonl(
                    calls_file,
                    {
                        "request_id": request_id,
                        "role": "enrich",
                        "review_ids": [review_id],
                        "model": data.get("model", MODEL),
                        "requested_model": MODEL,
                        "phase": phase,
                        "outcome": "succeeded",
                        "label_config": LABEL_CONFIG,
                        "attempt": attempt,
                        "input_tokens": usage.get("input_tokens", 0),
                        "output_tokens": usage.get("output_tokens", 0),
                        "runtime_seconds": round(elapsed, 3),
                        "timestamp": utc_now(),
                    },
                )
                return data

            last_error = f"HTTP {response.status_code}: {response.text}"

            append_jsonl(
                calls_file,
                {
                    "request_id": request_id,
                    "role": "enrich",
                    "review_ids": [review_id],
                    "model": MODEL,
                    "phase": phase,
                    "outcome": "failed",
                    "label_config": LABEL_CONFIG,
                    "attempt": attempt,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "runtime_seconds": round(elapsed, 3),
                    "error": last_error,
                    "timestamp": utc_now(),
                },
            )

        except Exception as e:
            elapsed = time.time() - start
            last_error = str(e)

            append_jsonl(
                calls_file,
                {
                    "request_id": request_id,
                    "role": "enrich",
                    "review_ids": [review_id],
                    "model": MODEL,
                    "phase": phase,
                    "outcome": "failed",
                    "label_config": LABEL_CONFIG,
                    "attempt": attempt,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "runtime_seconds": round(elapsed, 3),
                    "error": last_error,
                    "timestamp": utc_now(),
                },
            )

        if attempt <= MAX_RETRIES:
            time.sleep(1)

    raise RuntimeError(f"Jev failed after retry: {last_error}")


def process_row(
    conn,
    api_key,
    row,
    source_index,
    calls_file,
    phase,
):
    review_id = row["review_id"]
    review_text = row["review_text"]
    source_sha256 = source_row_sha(row)
    now = utc_now()

    if not review_text.strip():
        conn.execute(
            """
            INSERT OR REPLACE INTO records (
                source_index,
                review_id,
                source_sha256,
                review_text,
                status,
                reason,
                label_config,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_index,
                review_id,
                source_sha256,
                review_text,
                "quarantined",
                "empty_review_text",
                LABEL_CONFIG,
                now,
                now,
            ),
        )
        conn.commit()
        return "quarantined"

    cache_key = text_cache_key(review_text)
    cached = get_cached_result(conn, cache_key)

    if cached:
        conn.execute(
            """
            INSERT OR REPLACE INTO records (
                source_index,
                review_id,
                source_sha256,
                review_text,
                status,
                topic,
                intent,
                sentiment,
                severity,
                entities_json,
                evidence_quote,
                needs_review,
                needs_review_reason,
                label_config,
                cache_source_id,
                topic_confidence,
                intent_confidence,
                severity_confidence,
                sentiment_confidence,
                created_at,
                updated_at
            )
            VALUES (
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?,
                ?, ?,
                ?, ?,
                ?, ?, ?, ?,
                ?, ?
            )
            """,
            (
                source_index,
                review_id,
                source_sha256,
                review_text,
                "completed",
                cached["topic"],
                cached["intent"],
                cached["sentiment"],
                cached["severity"],
                cached["entities_json"],
                cached["evidence_quote"],
                cached["needs_review"],
                cached["needs_review_reason"],
                cached["label_config"],
                cached["source_review_id"],
                cached["topic_confidence"],
                cached["intent_confidence"],
                cached["severity_confidence"],
                cached["sentiment_confidence"],
                now,
                now,
            ),
        )
        conn.commit()
        return "cache_hit"

    data = classify_review(
        api_key=api_key,
        review_id=review_id,
        review_text=review_text,
        calls_file=calls_file,
        phase=phase,
    )

    answers = data["answers"]

    topic = answers["topic"]["choice"]
    topic_conf = float(answers["topic"]["confidence"])

    intent = answers["intent"]["choice"]
    intent_conf = float(answers["intent"]["confidence"])

    severity = int(answers["severity"]["choice"])
    severity_conf = float(answers["severity"]["confidence"])

    sentiment_score = float(answers["sentiment"]["score"])
    sentiment_conf = float(answers["sentiment"]["confidence"])
    sentiment = sentiment_to_minus1_plus1(sentiment_score)

    needs_review, reasons = calculate_needs_review(
        topic,
        intent,
        severity,
        topic_conf,
        intent_conf,
        severity_conf,
        sentiment_conf,
    )

    needs_review_reason = "|".join(reasons)

    entities_json = "[]"
    evidence_quote = review_text

    conn.execute(
        """
        INSERT OR REPLACE INTO records (
            source_index,
            review_id,
            source_sha256,
            review_text,
            status,
            topic,
            intent,
            sentiment,
            severity,
            entities_json,
            evidence_quote,
            needs_review,
            needs_review_reason,
            label_config,
            cache_source_id,
            topic_confidence,
            intent_confidence,
            severity_confidence,
            sentiment_confidence,
            created_at,
            updated_at
        )
        VALUES (
            ?, ?, ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?,
            ?, ?,
            ?, ?,
            ?, ?, ?, ?,
            ?, ?
        )
        """,
        (
            source_index,
            review_id,
            source_sha256,
            review_text,
            "completed",
            topic,
            intent,
            sentiment,
            severity,
            entities_json,
            evidence_quote,
            int(needs_review),
            needs_review_reason,
            LABEL_CONFIG,
            None,
            topic_conf,
            intent_conf,
            severity_conf,
            sentiment_conf,
            now,
            now,
        ),
    )

    conn.execute(
        """
        INSERT OR REPLACE INTO result_cache (
            cache_key,
            review_text,
            source_review_id,
            topic,
            intent,
            sentiment,
            severity,
            entities_json,
            evidence_quote,
            needs_review,
            needs_review_reason,
            topic_confidence,
            intent_confidence,
            severity_confidence,
            sentiment_confidence,
            label_config
        )
        VALUES (
            ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?,
            ?, ?,
            ?, ?, ?, ?,
            ?
        )
        """,
        (
            cache_key,
            review_text,
            review_id,
            topic,
            intent,
            sentiment,
            severity,
            entities_json,
            evidence_quote,
            int(needs_review),
            needs_review_reason,
            topic_conf,
            intent_conf,
            severity_conf,
            sentiment_conf,
            LABEL_CONFIG,
        ),
    )

    conn.commit()
    return "api_call"


def export_records(conn, output_file):
    cur = conn.execute(
        """
        SELECT
            review_id,
            source_sha256,
            status,
            reason,
            topic,
            intent,
            sentiment,
            severity,
            entities_json,
            evidence_quote,
            needs_review,
            label_config,
            cache_source_id
        FROM records
        ORDER BY source_index
        """
    )

    with open(output_file, "w", encoding="utf-8") as f:
        for row in cur:
            (
                review_id,
                source_sha256,
                status,
                reason,
                topic,
                intent,
                sentiment,
                severity,
                entities_json,
                evidence_quote,
                needs_review,
                label_config,
                cache_source_id,
            ) = row

            if status == "completed":
                record = {
                    "review_id": review_id,
                    "source_sha256": source_sha256,
                    "status": "completed",
                    "topic": topic,
                    "intent": intent,
                    "sentiment": sentiment,
                    "severity": severity,
                    "entities": json.loads(entities_json),
                    "evidence_quote": evidence_quote,
                    "needs_review": bool(needs_review),
                    "label_config": label_config,
                }

                if cache_source_id:
                    record["cache_source_id"] = cache_source_id

            else:
                record = {
                    "review_id": review_id,
                    "source_sha256": source_sha256,
                    "status": status,
                    "reason": reason,
                }

            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def save_checkpoint(conn, path):
    ids = [
        row[0]
        for row in conn.execute(
            """
            SELECT review_id
            FROM records
            WHERE status = 'completed'
            ORDER BY source_index
            """
        )
    ]

    payload = {
        "completed_ids": ids,
        "count": len(ids),
        "timestamp": utc_now(),
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            payload,
            f,
            ensure_ascii=False,
            indent=2,
        )


def save_run_json(input_csv, output_dir):
    file_sha = hashlib.sha256()

    with open(input_csv, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            file_sha.update(chunk)

    payload = {
        "version": "a5-audit-v1",
        "analysis_count": None,
        "analysis_sha256": file_sha.hexdigest(),
        "classification_input_fields": ["review_text"],
        "allow_multi_issue": False,
        "label_config": LABEL_CONFIG,
        "model": MODEL,
        "prompt_version": PROMPT_VERSION,
        "schema_version": SCHEMA_VERSION,
    }

    with open(
        output_dir / "run.json",
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            payload,
            f,
            ensure_ascii=False,
            indent=2,
        )


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "input_csv",
        help="Input Spotify CSV",
    )

    parser.add_argument(
        "--out",
        default="grading_work",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
    )

    parser.add_argument(
        "--max-new-calls",
        type=int,
        default=None,
    )

    args = parser.parse_args()

    load_dotenv()

    api_key = os.getenv("TYPESAFE_API_KEY")

    if not api_key:
        raise ValueError("TYPESAFE_API_KEY not found in .env")

    input_csv = Path(args.input_csv)
    out_dir = Path(args.out)

    out_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    db_file = out_dir / "pipeline_state.sqlite"
    calls_file = out_dir / "calls.jsonl"
    records_file = out_dir / "records.jsonl"

    existing_db = db_file.exists()
    phase = "resume" if existing_db else "initial"

    conn = open_db(db_file)

    save_run_json(
        input_csv,
        out_dir,
    )

    api_calls_this_run = 0
    cache_hits = 0
    quarantined = 0
    already_done = 0
    failures = 0

    start_time = time.time()

    with open(
        input_csv,
        newline="",
        encoding="utf-8",
    ) as f:
        reader = csv.DictReader(f)

        if reader.fieldnames != SOURCE_FIELDS:
            raise ValueError(
                f"Unexpected source fields. Got: {reader.fieldnames}"
            )

        for source_index, row in enumerate(reader):
            if args.limit is not None and source_index >= args.limit:
                break

            review_id = row["review_id"]

            existing = get_existing_record(
                conn,
                review_id,
            )

            if existing:
                already_done += 1
                continue

            if (
                args.max_new_calls is not None
                and api_calls_this_run >= args.max_new_calls
            ):
                print("\nSafety cap reached.")
                break

            try:
                result = process_row(
                    conn=conn,
                    api_key=api_key,
                    row=row,
                    source_index=source_index,
                    calls_file=calls_file,
                    phase=phase,
                )

                if result == "api_call":
                    api_calls_this_run += 1
                elif result == "cache_hit":
                    cache_hits += 1
                elif result == "quarantined":
                    quarantined += 1

            except Exception as e:
                failures += 1
                print("\nERROR")
                print("review_id:", review_id)
                print(str(e))

            processed_total = source_index + 1

            if processed_total % 100 == 0:
                elapsed = time.time() - start_time
                print(
                    f"Processed source rows: {processed_total} | "
                    f"New API calls: {api_calls_this_run} | "
                    f"Cache hits: {cache_hits} | "
                    f"Elapsed seconds: {elapsed:.1f}"
                )

    export_records(
        conn,
        records_file,
    )

    save_checkpoint(
        conn,
        out_dir / "checkpoint_current.json",
    )

    total_records = conn.execute(
        "SELECT COUNT(*) FROM records"
    ).fetchone()[0]

    completed = conn.execute(
        """
        SELECT COUNT(*)
        FROM records
        WHERE status = 'completed'
        """
    ).fetchone()[0]

    quarantine_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM records
        WHERE status = 'quarantined'
        """
    ).fetchone()[0]

    run_json_path = out_dir / "run.json"

    with open(run_json_path, encoding="utf-8") as f:
        run_meta = json.load(f)

    run_meta["analysis_count"] = total_records

    with open(
        run_json_path,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            run_meta,
            f,
            ensure_ascii=False,
            indent=2,
        )

    elapsed = time.time() - start_time

    print("\n==============================")
    print("PIPELINE PASS DONE")
    print("==============================")
    print("Phase:", phase)
    print("Records saved:", total_records)
    print("Completed:", completed)
    print("Quarantined:", quarantine_count)
    print("Already completed before run:", already_done)
    print("New API calls:", api_calls_this_run)
    print("Cache hits:", cache_hits)
    print("Unrecovered failures this invocation:", failures)
    print("Wall-clock seconds:", round(elapsed, 2))
    print("Records:", records_file)
    print("Calls:", calls_file)
    print("State DB:", db_file)

    conn.close()


if __name__ == "__main__":
    main()
