"""Deterministic integration benchmark for the queue, workers, and spend guard."""
import csv
import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "spotify_reviews_18months.csv"
START, END = 490, 498  # fixed slice immediately after grading_full's saved rows


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length))
        time.sleep(0.15)
        payload = {
            "model": "deterministic-test-provider",
            "answers": {
                "topic": {"choice": "playback", "confidence": 0.9},
                "intent": {"choice": "complaint", "confidence": 0.9},
                "severity": {"choice": "3", "confidence": 0.9},
                "sentiment": {"score": 1, "confidence": 0.9},
            },
            "usage": {"input_tokens": 100, "output_tokens": 20},
            "echo_review_id": body["state"]["review_id"],
        }
        encoded = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, *_):
        pass


def run_case(name, workers, url, root, spend_cap=None):
    out = root / name
    command = [
        sys.executable, str(ROOT / "run_pipeline.py"), str(SOURCE),
        "--out", str(out), "--start-index", str(START), "--limit", str(END),
        "--workers", str(workers), "--api-url", url,
        "--requests-per-minute", "0", "--tokens-per-minute", "0",
        "--backoff-base", "0", "--backoff-jitter", "0",
    ]
    if spend_cap is not None:
        command += ["--spend-cap", str(spend_cap)]
    env = dict(os.environ, TYPESAFE_API_KEY="integration-test-key")
    started = time.monotonic()
    result = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True, check=True)
    elapsed = time.monotonic() - started
    db = sqlite3.connect(out / "pipeline_state.sqlite")
    queue = dict(db.execute("SELECT status,COUNT(*) FROM work_queue GROUP BY status"))
    calls = db.execute("SELECT review_id,outcome FROM api_call_attempts").fetchall()
    rows = db.execute(
        """SELECT review_id,topic,intent,sentiment,severity,cache_source_id
           FROM records WHERE status='completed' ORDER BY source_index"""
    ).fetchall()
    ledger = db.execute(
        "SELECT cap_usd,spent_estimated_usd,reserved_usd FROM spend_ledger WHERE singleton=1"
    ).fetchone()
    db.close()
    successful = [review_id for review_id, outcome in calls if outcome == "succeeded"]
    assert len(successful) == len(set(successful)), "duplicate paid successful calls"
    assert ledger[2] == 0, "reservation leak"
    return {"elapsed_seconds": round(elapsed, 3), "queue": queue, "calls": len(calls),
            "successful_call_ids": successful, "rows": rows, "ledger": ledger,
            "stdout": result.stdout}


def main():
    stamp = time.strftime("%Y%m%d-%H%M%S")
    root = ROOT / f"grading_parallel_benchmark_{stamp}"
    root.mkdir()
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/v1/systemone"
    try:
        one = run_case("one_worker", 1, url, root)
        two = run_case("two_workers", 2, url, root)
        guard = run_case("spend_guard", 2, url, root, spend_cap=0.0002)
    finally:
        server.shutdown()
        server.server_close()
    assert one["rows"] == two["rows"], "worker counts produced different records"
    assert two["elapsed_seconds"] < one["elapsed_seconds"], "two workers did not improve runtime"
    assert guard["queue"].get("completed") == 2 and guard["queue"].get("pending") == 6
    report = {
        "slice": [START, END], "provider": "deterministic local integration provider",
        "one_worker_seconds": one["elapsed_seconds"], "two_worker_seconds": two["elapsed_seconds"],
        "speedup": round(one["elapsed_seconds"] / two["elapsed_seconds"], 2),
        "outputs_identical": True,
        "one_worker_calls": one["calls"], "two_worker_calls": two["calls"],
        "duplicate_successful_calls": 0,
        "guard_queue": guard["queue"], "guard_ledger": guard["ledger"],
    }
    (root / "benchmark_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print("Artifacts:", root)


if __name__ == "__main__":
    main()
