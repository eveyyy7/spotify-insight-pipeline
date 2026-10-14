"""Crash-safe, budget-capped parallel enrichment pipeline.

Provider request batch size is intentionally one: a measured multi-state pilot
returned one aggregate answer instead of one answer per review. Local queueing
and worker concurrency provide parallelism without losing ID-level validation.
"""
import argparse
import csv
import hashlib
import json
import os
import random
import sqlite3
import threading
import time
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

from run_pipeline_legacy import (
    LABEL_CONFIG, MODEL, PROMPT_VERSION, QUESTIONS, SCHEMA_VERSION,
    SOURCE_FIELDS, calculate_needs_review, source_row_sha, text_cache_key,
)

PROVIDER_REQUEST_BATCH_SIZE = 1
DEFAULT_WORST_CASE_COST = 10.0 / 100_000


def now():
    return datetime.now(timezone.utc).isoformat()


def connect(path):
    db = sqlite3.connect(path, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout=30000")
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=FULL")
    return db


def open_db(path):
    db = connect(path)
    # The first two tables exactly match the existing grading_full schema.
    db.executescript("""
    CREATE TABLE IF NOT EXISTS records (
      source_index INTEGER PRIMARY KEY, review_id TEXT UNIQUE NOT NULL,
      source_sha256 TEXT NOT NULL, review_text TEXT NOT NULL, status TEXT NOT NULL,
      reason TEXT, topic TEXT, intent TEXT, sentiment REAL, severity INTEGER,
      entities_json TEXT, evidence_quote TEXT, needs_review INTEGER,
      needs_review_reason TEXT, label_config TEXT, cache_source_id TEXT,
      topic_confidence REAL, intent_confidence REAL, severity_confidence REAL,
      sentiment_confidence REAL, created_at TEXT, updated_at TEXT);
    CREATE TABLE IF NOT EXISTS result_cache (
      cache_key TEXT PRIMARY KEY, review_text TEXT NOT NULL,
      source_review_id TEXT NOT NULL, topic TEXT NOT NULL, intent TEXT NOT NULL,
      sentiment REAL NOT NULL, severity INTEGER NOT NULL, entities_json TEXT NOT NULL,
      evidence_quote TEXT NOT NULL, needs_review INTEGER NOT NULL,
      needs_review_reason TEXT, topic_confidence REAL, intent_confidence REAL,
      severity_confidence REAL, sentiment_confidence REAL, label_config TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS work_queue (
      source_index INTEGER PRIMARY KEY, review_id TEXT UNIQUE NOT NULL,
      source_sha256 TEXT NOT NULL, review_text TEXT NOT NULL, cache_key TEXT,
      status TEXT NOT NULL CHECK(status IN
        ('pending','in_flight','completed','quarantined','failed')),
      claimed_by TEXT, reserved_usd REAL NOT NULL DEFAULT 0,
      attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT,
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS idx_queue_status ON work_queue(status,source_index);
    CREATE INDEX IF NOT EXISTS idx_queue_cache ON work_queue(cache_key,status);
    CREATE TABLE IF NOT EXISTS spend_ledger (
      singleton INTEGER PRIMARY KEY CHECK(singleton=1), cap_usd REAL NOT NULL,
      spent_estimated_usd REAL NOT NULL DEFAULT 0,
      reserved_usd REAL NOT NULL DEFAULT 0, historical_attempts INTEGER NOT NULL DEFAULT 0,
      basis TEXT NOT NULL, updated_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS api_call_attempts (
      request_id TEXT PRIMARY KEY, review_id TEXT NOT NULL, worker_id TEXT NOT NULL,
      phase TEXT NOT NULL, attempt INTEGER NOT NULL, outcome TEXT NOT NULL,
      error_kind TEXT, input_tokens INTEGER NOT NULL DEFAULT 0,
      output_tokens INTEGER NOT NULL DEFAULT 0, runtime_seconds REAL NOT NULL,
      timestamp TEXT NOT NULL);
    """)
    # Backward-compatible migration: only mirror old rows into the new queue.
    for row in db.execute("SELECT * FROM records"):
        key = text_cache_key(row["review_text"]) if row["review_text"].strip() else None
        status = "completed" if row["status"] == "completed" else "quarantined"
        db.execute(
            """INSERT OR IGNORE INTO work_queue
            (source_index,review_id,source_sha256,review_text,cache_key,status,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?)""",
            (row["source_index"], row["review_id"], row["source_sha256"],
             row["review_text"], key, status, row["created_at"] or now(), row["updated_at"] or now()),
        )
    db.commit()
    return db


def old_attempt_count(path):
    if not path.exists():
        return 0
    total = 0
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                total += json.loads(line).get("role") == "enrich"
            except (json.JSONDecodeError, AttributeError):
                pass
    return total


def init_ledger(db, calls_file, cap, reservation):
    ledger = db.execute("SELECT * FROM spend_ledger WHERE singleton=1").fetchone()
    if ledger is None:
        historical = old_attempt_count(calls_file)
        db.execute(
            "INSERT INTO spend_ledger VALUES(1,?,?,?,?,?,?)",
            (cap, historical * reservation, 0.0, historical,
             "$10/100k-row conservative estimate; one reservation includes bounded retries", now()),
        )
    elif cap + 1e-12 < ledger["spent_estimated_usd"] + ledger["reserved_usd"]:
        raise ValueError("Spend cap is below already spent plus reserved ledger value")
    else:
        db.execute("UPDATE spend_ledger SET cap_usd=?,updated_at=? WHERE singleton=1", (cap, now()))
    db.commit()


def seed(db, input_csv, start, end):
    with input_csv.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != SOURCE_FIELDS:
            raise ValueError(f"Unexpected source fields: {reader.fieldnames}")
        for index, row in enumerate(reader):
            if index < start:
                continue
            if end is not None and index >= end:
                break
            text = row["review_text"]
            stamp = now()
            status = "pending" if text.strip() else "quarantined"
            sha = source_row_sha(row)
            db.execute(
                """INSERT OR IGNORE INTO work_queue
                (source_index,review_id,source_sha256,review_text,cache_key,status,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?)""",
                (index, row["review_id"], sha, text,
                 text_cache_key(text) if text.strip() else None, status, stamp, stamp),
            )
            if not text.strip():
                db.execute(
                    """INSERT OR IGNORE INTO records
                    (source_index,review_id,source_sha256,review_text,status,reason,label_config,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?)""",
                    (index, row["review_id"], sha, text, "quarantined",
                     "empty_review_text", LABEL_CONFIG, stamp, stamp),
                )
            if index % 1000 == 999:
                db.commit()
    db.commit()


def recover_in_flight(db):
    rows = db.execute("SELECT * FROM work_queue WHERE status='in_flight'").fetchall()
    if not rows:
        return 0
    reserved = sum(row["reserved_usd"] for row in rows)
    db.execute("BEGIN IMMEDIATE")
    db.execute("""UPDATE work_queue SET status='pending',claimed_by=NULL,reserved_usd=0,
               last_error='explicit recovery of uncertain in-flight work',updated_at=?
               WHERE status='in_flight'""", (now(),))
    db.execute("""UPDATE spend_ledger SET reserved_usd=MAX(0,reserved_usd-?),updated_at=?
               WHERE singleton=1""", (reserved, now()))
    db.commit()
    return len(rows)


class RateLimiter:
    def __init__(self, rpm, tpm):
        self.rpm, self.tpm, self.events = rpm, tpm, deque()
        self.cv = threading.Condition()

    def acquire(self, tokens):
        with self.cv:
            while True:
                current = time.monotonic()
                while self.events and current - self.events[0][0] >= 60:
                    self.events.popleft()
                request_ok = self.rpm <= 0 or len(self.events) < self.rpm
                token_ok = self.tpm <= 0 or sum(x[1] for x in self.events) + tokens <= self.tpm
                if request_ok and token_ok:
                    self.events.append((current, tokens))
                    return
                delay = 60 - (current - self.events[0][0]) if self.events else 0.05
                self.cv.wait(max(0.01, min(delay, 1.0)))


class Logger:
    def __init__(self, db_path, calls_file):
        self.db_path, self.calls_file, self.lock = db_path, calls_file, threading.Lock()

    def write(self, item):
        with self.lock:
            db = connect(self.db_path)
            db.execute(
                """INSERT OR IGNORE INTO api_call_attempts VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (item["request_id"], item["review_ids"][0], item["worker_id"], item["phase"],
                 item["attempt"], item["outcome"], item.get("error_kind"), item["input_tokens"],
                 item["output_tokens"], item["runtime_seconds"], item["timestamp"]),
            )
            db.commit()
            db.close()
            with self.calls_file.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(item, ensure_ascii=False) + "\n")
                handle.flush()
                os.fsync(handle.fileno())


def cache_values(row):
    names = ("topic", "intent", "sentiment", "severity", "entities_json", "evidence_quote",
             "needs_review", "needs_review_reason", "topic_confidence", "intent_confidence",
             "severity_confidence", "sentiment_confidence")
    return {name: row[name] for name in names}


def save_record(db, job, values, source_id=None):
    stamp = now()
    db.execute(
        """INSERT OR REPLACE INTO records
        (source_index,review_id,source_sha256,review_text,status,topic,intent,sentiment,severity,
         entities_json,evidence_quote,needs_review,needs_review_reason,label_config,cache_source_id,
         topic_confidence,intent_confidence,severity_confidence,sentiment_confidence,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (job["source_index"], job["review_id"], job["source_sha256"], job["review_text"],
         "completed", values["topic"], values["intent"], values["sentiment"], values["severity"],
         values["entities_json"], values["evidence_quote"], values["needs_review"],
         values["needs_review_reason"], LABEL_CONFIG, source_id, values["topic_confidence"],
         values["intent_confidence"], values["severity_confidence"],
         values["sentiment_confidence"], stamp, stamp),
    )


def claim(db, worker, reservation, start_index=0, end_index=None):
    while True:
        db.execute("BEGIN IMMEDIATE")
        job = db.execute("""SELECT q.* FROM work_queue q WHERE q.status='pending'
          AND q.source_index >= ? AND (? IS NULL OR q.source_index < ?)
          AND NOT EXISTS(SELECT 1 FROM work_queue x
                         WHERE x.cache_key=q.cache_key AND x.status='in_flight')
          ORDER BY q.source_index LIMIT 1""",
          (start_index, end_index, end_index)).fetchone()
        if job is None:
            pending = db.execute(
                """SELECT COUNT(*) FROM work_queue WHERE status='pending'
                   AND source_index >= ? AND (? IS NULL OR source_index < ?)""",
                (start_index, end_index, end_index),
            ).fetchone()[0]
            db.commit()
            return ("wait" if pending else "done"), None
        cached = db.execute("SELECT * FROM result_cache WHERE cache_key=?", (job["cache_key"],)).fetchone()
        if cached:
            save_record(db, job, cache_values(cached), cached["source_review_id"])
            db.execute("UPDATE work_queue SET status='completed',updated_at=? WHERE source_index=?",
                       (now(), job["source_index"]))
            db.commit()
            return "cache", dict(job)
        ledger = db.execute("SELECT * FROM spend_ledger WHERE singleton=1").fetchone()
        if ledger["spent_estimated_usd"] + ledger["reserved_usd"] + reservation > ledger["cap_usd"] + 1e-12:
            db.commit()
            return "budget", None
        db.execute("""UPDATE work_queue SET status='in_flight',claimed_by=?,reserved_usd=?,
                   attempts=attempts+1,updated_at=? WHERE source_index=?""",
                   (worker, reservation, now(), job["source_index"]))
        db.execute("UPDATE spend_ledger SET reserved_usd=reserved_usd+?,updated_at=? WHERE singleton=1",
                   (reservation, now()))
        db.commit()
        return "claimed", dict(job)


def validate(data, text):
    try:
        answers = data["answers"]
        topic, intent = answers["topic"]["choice"], answers["intent"]["choice"]
        severity = int(answers["severity"]["choice"])
        score = float(answers["sentiment"]["score"])
        conf = [float(answers[x]["confidence"]) for x in ("topic", "intent", "severity", "sentiment")]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"malformed answers: {exc}") from exc
    if topic not in QUESTIONS["topic"]["criteria"] or intent not in QUESTIONS["intent"]["criteria"]:
        raise ValueError("unknown topic or intent")
    if severity not in range(1, 6) or not 0 <= score <= 4 or any(not 0 <= x <= 1 for x in conf):
        raise ValueError("answer value out of range")
    needs, reasons = calculate_needs_review(topic, intent, severity, *conf)
    return dict(topic=topic, intent=intent, sentiment=round(score / 2 - 1, 3), severity=severity,
                entities_json="[]", evidence_quote=text, needs_review=int(needs),
                needs_review_reason="|".join(reasons), topic_confidence=conf[0],
                intent_confidence=conf[1], severity_confidence=conf[2], sentiment_confidence=conf[3])


def classify(job, args, worker, phase, limiter, logger):
    payload = {"model": MODEL, "state": {"review_id": job["review_id"],
               "review_text": job["review_text"]}, "questions": QUESTIONS}
    headers = {"Authorization": f"Bearer {args.api_key}", "Content-Type": "application/json"}
    transient = invalid = attempt = 0
    while True:
        attempt += 1
        limiter.acquire(args.estimated_tokens_per_request)
        request_id, started = str(uuid.uuid4()), time.monotonic()
        data, error, kind, input_tokens, output_tokens = None, None, None, 0, 0
        try:
            response = requests.post(args.api_url, headers=headers, json=payload, timeout=args.request_timeout)
            if response.status_code != 200:
                error = f"HTTP {response.status_code}: {response.text[:500]}"
                kind = "transient_http" if response.status_code in {408, 409, 425, 429} or response.status_code >= 500 else "http"
            else:
                data = response.json()
                usage = data.get("usage", {})
                input_tokens = int(usage.get("input_tokens", 0) or 0)
                output_tokens = int(usage.get("output_tokens", 0) or 0)
                try:
                    result = validate(data, job["review_text"])
                except ValueError as exc:
                    error, kind = str(exc), "invalid_output"
        except requests.RequestException as exc:
            error, kind = str(exc), "transport"
        except (ValueError, json.JSONDecodeError) as exc:
            error, kind = str(exc), "invalid_output"
        elapsed = time.monotonic() - started
        logger.write(dict(request_id=request_id, role="enrich", review_ids=[job["review_id"]],
            worker_id=worker, model=data.get("model", MODEL) if data else MODEL,
            requested_model=MODEL, provider_batch_size=1, phase=phase,
            outcome="succeeded" if error is None else "failed", label_config=LABEL_CONFIG,
            attempt=attempt, input_tokens=input_tokens, output_tokens=output_tokens,
            runtime_seconds=round(elapsed, 3), error=error, error_kind=kind, timestamp=now()))
        if error is None:
            return result
        if kind == "invalid_output":
            invalid += 1
            retry = invalid <= args.invalid_output_retries
        elif kind in {"transport", "transient_http"}:
            transient += 1
            retry = transient <= args.transient_retries
        else:
            retry = False
        if not retry:
            raise RuntimeError(error)
        time.sleep(args.backoff_base * 2 ** (attempt - 1) + random.uniform(0, args.backoff_jitter))


def finish(db, job, worker, values, failure=None):
    db.execute("BEGIN IMMEDIATE")
    current = db.execute("SELECT * FROM work_queue WHERE source_index=?", (job["source_index"],)).fetchone()
    if current["status"] != "in_flight" or current["claimed_by"] != worker:
        db.rollback()
        raise RuntimeError("worker lost ownership")
    reservation = current["reserved_usd"]
    if failure is None:
        cached = db.execute("SELECT * FROM result_cache WHERE cache_key=?", (job["cache_key"],)).fetchone()
        if cached:
            values, source_id = cache_values(cached), cached["source_review_id"]
        else:
            source_id = None
            db.execute("""INSERT INTO result_cache VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (job["cache_key"], job["review_text"], job["review_id"], values["topic"],
                 values["intent"], values["sentiment"], values["severity"], values["entities_json"],
                 values["evidence_quote"], values["needs_review"], values["needs_review_reason"],
                 values["topic_confidence"], values["intent_confidence"], values["severity_confidence"],
                 values["sentiment_confidence"], LABEL_CONFIG))
        save_record(db, job, values, source_id)
        db.execute("""UPDATE work_queue SET status='completed',claimed_by=NULL,reserved_usd=0,
                   last_error=NULL,updated_at=? WHERE source_index=?""", (now(), job["source_index"]))
    else:
        db.execute("""UPDATE work_queue SET status='failed',claimed_by=NULL,reserved_usd=0,
                   last_error=?,updated_at=? WHERE source_index=?""",
                   (str(failure)[:2000], now(), job["source_index"]))
    db.execute("""UPDATE spend_ledger SET reserved_usd=MAX(0,reserved_usd-?),
               spent_estimated_usd=spent_estimated_usd+?,updated_at=? WHERE singleton=1""",
               (reservation, reservation, now()))
    db.commit()


def worker_loop(db_path, args, phase, limiter, logger, stats, stop, number):
    worker = f"worker-{number}-{uuid.uuid4().hex[:8]}"
    db = connect(db_path)
    try:
        while not stop.is_set():
            state, job = claim(
                db, worker, args.worst_case_cost, args.start_index, args.limit
            )
            if state == "done": return
            if state == "budget": stop.set(); return
            if state == "wait": time.sleep(0.05); continue
            if state == "cache":
                with stats["lock"]: stats["cache"] += 1
                continue
            try:
                values = classify(job, args, worker, phase, limiter, logger)
                finish(db, job, worker, values)
                with stats["lock"]: stats["api"] += 1
            except Exception as exc:
                finish(db, job, worker, None, exc)
                with stats["lock"]: stats["failed"] += 1
    finally:
        db.close()


def export(db, out_dir, start_index=0, end_index=None):
    scope_sql = "source_index >= ? AND (? IS NULL OR source_index < ?)"
    scope_args = (start_index, end_index, end_index)
    with (out_dir / "records.jsonl").open("w", encoding="utf-8") as handle:
        for row in db.execute(
            f"SELECT * FROM records WHERE {scope_sql} ORDER BY source_index",
            scope_args,
        ):
            if row["status"] == "completed":
                item = {"review_id": row["review_id"], "source_sha256": row["source_sha256"],
                        "status": "completed", "topic": row["topic"], "intent": row["intent"],
                        "sentiment": row["sentiment"], "severity": row["severity"],
                        "entities": json.loads(row["entities_json"]), "evidence_quote": row["evidence_quote"],
                        "needs_review": bool(row["needs_review"]), "label_config": row["label_config"]}
                if row["cache_source_id"]: item["cache_source_id"] = row["cache_source_id"]
            else:
                item = {"review_id": row["review_id"], "source_sha256": row["source_sha256"],
                        "status": row["status"], "reason": row["reason"]}
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    ids = [x[0] for x in db.execute(
        f"""SELECT review_id FROM records WHERE status='completed' AND {scope_sql}
            ORDER BY source_index""",
        scope_args,
    )]
    (out_dir / "checkpoint_current.json").write_text(
        json.dumps({"completed_ids": ids, "count": len(ids), "timestamp": now()}, indent=2), encoding="utf-8")


def snapshot_completed(db, path):
    """Persist a stable resume snapshot without replacing earlier evidence."""
    ids = [row[0] for row in db.execute(
        "SELECT review_id FROM records WHERE status='completed' ORDER BY source_index"
    )]
    path.write_text(
        json.dumps({"completed_ids": ids, "count": len(ids), "timestamp": now()}, indent=2) + "\n",
        encoding="utf-8",
    )
    return len(ids)


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def arguments():
    p = argparse.ArgumentParser()
    p.add_argument("input_csv")
    p.add_argument("--out", default="grading_work")
    p.add_argument("--start-index", type=int, default=0)
    p.add_argument("--limit", type=int, default=None, help="Exclusive source-index end (legacy semantics)")
    p.add_argument("--workers", type=int, choices=(1, 2), default=2)
    p.add_argument("--max-new-calls", type=int, default=None)
    p.add_argument("--spend-cap", type=float)
    p.add_argument("--worst-case-cost", type=float, default=DEFAULT_WORST_CASE_COST)
    p.add_argument("--requests-per-minute", type=int, default=300)
    p.add_argument("--tokens-per-minute", type=int, default=120000)
    p.add_argument("--estimated-tokens-per-request", type=int, default=1500)
    p.add_argument("--transient-retries", type=int, default=2)
    p.add_argument("--invalid-output-retries", type=int, choices=(0, 1), default=1)
    p.add_argument("--backoff-base", type=float, default=0.5)
    p.add_argument("--backoff-jitter", type=float, default=0.25)
    p.add_argument("--request-timeout", type=float, default=30)
    p.add_argument("--api-url", default="https://api.typesafe.ai/v1/systemone")
    p.add_argument("--recover-in-flight", action="store_true")
    return p.parse_args()


def main():
    args = arguments()
    load_dotenv()
    args.api_key = os.getenv("TYPESAFE_API_KEY")
    if not args.api_key: raise ValueError("TYPESAFE_API_KEY not found in .env")
    if args.start_index < 0 or args.limit is not None and args.limit < args.start_index:
        raise ValueError("Invalid slice")
    source, out = Path(args.input_csv), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    db_path, calls = out / "pipeline_state.sqlite", out / "calls.jsonl"
    phase = "resume" if db_path.exists() else "initial"
    db = open_db(db_path)
    before_path = out / "checkpoint_before.json"
    # A fresh run must retain an explicit empty pre-run checkpoint so the
    # orchestrator can package the same resume evidence as a resumed run.
    # Never replace an existing checkpoint: it is the stable before-state.
    if not before_path.exists():
        snapshot_completed(db, before_path)
    selected = args.limit - args.start_index if args.limit is not None else sum(1 for _ in source.open(encoding="utf-8")) - 1 - args.start_index
    args.spend_cap = selected * DEFAULT_WORST_CASE_COST if args.spend_cap is None else args.spend_cap
    init_ledger(db, calls, args.spend_cap, args.worst_case_cost)
    if args.max_new_calls is not None:
        ledger = db.execute("SELECT * FROM spend_ledger WHERE singleton=1").fetchone()
        args.spend_cap = min(args.spend_cap, ledger["spent_estimated_usd"] + ledger["reserved_usd"]
                             + args.max_new_calls * args.worst_case_cost)
        db.execute("UPDATE spend_ledger SET cap_usd=?,updated_at=? WHERE singleton=1", (args.spend_cap, now()))
        db.commit()
    if args.recover_in_flight: print("Recovered uncertain in-flight rows:", recover_in_flight(db))
    unresolved = db.execute("SELECT COUNT(*) FROM work_queue WHERE status='in_flight'").fetchone()[0]
    if unresolved: raise RuntimeError(f"{unresolved} uncertain in-flight rows; inspect then use --recover-in-flight")
    seed(db, source, args.start_index, args.limit)
    db.close()
    stats = {"lock": threading.Lock(), "api": 0, "cache": 0, "failed": 0}
    stop, started = threading.Event(), time.monotonic()
    limiter, logger = RateLimiter(args.requests_per_minute, args.tokens_per_minute), Logger(db_path, calls)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(worker_loop, db_path, args, phase, limiter, logger, stats, stop, i + 1)
                   for i in range(args.workers)]
        for future in futures: future.result()
    db = connect(db_path)
    export(db, out, args.start_index, args.limit)
    counts = {x["status"]: x["n"] for x in db.execute("SELECT status,COUNT(*) n FROM work_queue GROUP BY status")}
    ledger = dict(db.execute("SELECT * FROM spend_ledger WHERE singleton=1").fetchone())
    total = db.execute(
        """SELECT COUNT(*) FROM records WHERE source_index >= ?
           AND (? IS NULL OR source_index < ?)""",
        (args.start_index, args.limit, args.limit),
    ).fetchone()[0]
    if before_path.exists():
        before_count = len(json.loads(before_path.read_text(encoding="utf-8"))["completed_ids"])
        if total > before_count:
            snapshot_completed(db, out / "checkpoint_after.json")
    run = {"version": "a5-audit-v1", "analysis_count": total,
           "analysis_sha256": file_sha256(source),
           "classification_input_fields": ["review_text"],
           "allow_multi_issue": False,
           "label_config": LABEL_CONFIG,
           "provider_request_batch_size": 1,
           "provider_batch_size_reason": "multi-state pilot returned one aggregate answer",
           "workers": args.workers, "spend_cap_usd": args.spend_cap}
    (out / "run.json").write_text(json.dumps(run, indent=2), encoding="utf-8")
    db.close()
    print("Phase:", phase, "| Workers:", args.workers, "| Provider batch size: 1")
    print("Queue:", counts)
    print("New API classifications:", stats["api"], "| Cache hits:", stats["cache"], "| Failed:", stats["failed"])
    print("Budget stopped dispatch:", stop.is_set(), "| Ledger:", ledger)
    print("Wall-clock seconds:", round(time.monotonic() - started, 3))


if __name__ == "__main__":
    main()
