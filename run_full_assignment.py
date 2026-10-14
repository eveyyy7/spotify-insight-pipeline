"""Run and package the complete Assignment 5 pipeline without manual copying."""
import argparse
import csv
import gzip
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def run(*parts):
    command = [sys.executable, *map(str, parts)]
    print("+", " ".join(command))
    subprocess.run(command, cwd=ROOT, check=True)


def package_submission(source_dir, grading_dir):
    grading_dir.mkdir(parents=True, exist_ok=True)
    for name in (
        "run.json", "ingestion.json", "membership.csv", "ranking.csv",
        "claims.csv", "checkpoint_before.json", "checkpoint_after.json",
    ):
        shutil.copy2(source_dir / name, grading_dir / name)
    for name in ("records.jsonl", "calls.jsonl"):
        with (source_dir / name).open("rb") as incoming, gzip.open(
            grading_dir / f"{name}.gz", "wb", compresslevel=6
        ) as outgoing:
            shutil.copyfileobj(incoming, outgoing)
    for optional in ("memo.md", "verification_results.jsonl", "grouping_results.jsonl"):
        if (source_dir / optional).exists():
            shutil.copy2(source_dir / optional, grading_dir / optional)


def write_analysis_scope(source, destination, limit):
    """Preserve the exact original rows in the declared checker scope."""
    with source.open(newline="", encoding="utf-8") as incoming, destination.open(
        "w", newline="", encoding="utf-8"
    ) as outgoing:
        reader = csv.DictReader(incoming)
        writer = csv.DictWriter(outgoing, fieldnames=reader.fieldnames, lineterminator="\n")
        writer.writeheader()
        for index, row in enumerate(reader):
            if index >= limit:
                break
            writer.writerow(row)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("--state-dir", type=Path, default=ROOT / "grading_full")
    parser.add_argument("--submission-dir", type=Path, default=ROOT / "grading")
    parser.add_argument("--workers", type=int, choices=(1, 2), default=2)
    parser.add_argument(
        "--classification-limit", type=int, default=660622,
        help="Exclusive source-index end; use 100100 for a >100k submission",
    )
    parser.add_argument("--spend-cap", type=float, default=50.0)
    parser.add_argument("--requests-per-minute", type=int, default=300)
    parser.add_argument("--tokens-per-minute", type=int, default=0)
    parser.add_argument("--verification-cases", type=int, default=50)
    parser.add_argument("--grouping-cases", type=int, default=200)
    parser.add_argument("--skip-enrich", action="store_true")
    parser.add_argument("--skip-model-postprocessing", action="store_true")
    args = parser.parse_args()
    source = args.input_csv.resolve()
    state = args.state_dir.resolve()
    submission = args.submission_dir.resolve()

    if not args.skip_enrich:
        run(
            ROOT / "run_pipeline.py", source, "--out", state,
            "--limit", str(args.classification_limit),
            "--workers", str(args.workers), "--spend-cap", str(args.spend_cap),
            "--requests-per-minute", str(args.requests_per_minute),
            "--tokens-per-minute", str(args.tokens_per_minute),
        )

    records = state / "records.jsonl"
    if not records.exists():
        raise FileNotFoundError(f"Missing enrichment export: {records}")

    if not args.skip_model_postprocessing:
        run(ROOT / "run_verification.py", source, records, "--out", state,
            "--max-cases", str(args.verification_cases))
        run(ROOT / "run_grouping.py", source, records, "--out", state,
            "--max-cases", str(args.grouping_cases))
    run(ROOT / "build_ranking.py", records, "--out", state)
    if not args.skip_model_postprocessing:
        run(ROOT / "run_memo.py", "--out", state)

    run(ROOT / "check_submission.py", "profile", "--full", source,
        "--out", state / "ingestion.json")
    analysis_scope = state / f"analysis_scope_{args.classification_limit}.csv"
    write_analysis_scope(source, analysis_scope, args.classification_limit)
    run_manifest_path = state / "run.json"
    run_manifest = json.loads(run_manifest_path.read_text(encoding="utf-8"))
    run_manifest["analysis_sha256"] = sha256(analysis_scope)
    run_manifest_path.write_text(json.dumps(run_manifest, indent=2) + "\n", encoding="utf-8")
    reference = ROOT / "local-reference.json"
    run(ROOT / "check_submission.py", "reference", "--full", source,
        "--analysis", analysis_scope, "--out", reference)
    package_submission(state, submission)
    run(ROOT / "check_submission.py", "check", "--reference", reference,
        "--submission", submission, "--out", ROOT / "self-check.json")
    print("Submission package:", submission)
    print("Audit report:", ROOT / "self-check.json")


if __name__ == "__main__":
    main()
