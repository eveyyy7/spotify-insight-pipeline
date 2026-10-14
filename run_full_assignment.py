"""Run and package the complete Assignment 5 pipeline without manual copying."""
import argparse
import gzip
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("--state-dir", type=Path, default=ROOT / "grading_full")
    parser.add_argument("--submission-dir", type=Path, default=ROOT / "grading")
    parser.add_argument("--workers", type=int, choices=(1, 2), default=2)
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
            ROOT / "run_pipeline.py", source, "--out", state, "--limit", "660622",
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
    reference = ROOT / "local-reference.json"
    run(ROOT / "check_submission.py", "reference", "--full", source,
        "--analysis", source, "--out", reference)
    package_submission(state, submission)
    run(ROOT / "check_submission.py", "check", "--reference", reference,
        "--submission", submission, "--out", ROOT / "self-check.json")
    print("Submission package:", submission)
    print("Audit report:", ROOT / "self-check.json")


if __name__ == "__main__":
    main()
