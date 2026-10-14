# Submission checklist

## Scope and grading export

- [ ] State the exact source scope, completed count, quarantine count, and
  remaining failures in the README or memo. Under the latest course guidance,
  the submitted analysis must exceed 100,000 original rows; this project uses
  the first 100,100 rows. Label that scope precisely and do not call it a full
  660,622-row corpus run.
- [ ] Package the adapter folder described in `GRADING_CONTRACT.md`: `run.json`,
  full-source `ingestion.json`, one record per ID in the declared scope,
  membership/ranking/claims exports, call log, and before/after checkpoints.
  Include `memo.md` or clearly link the memo. Large JSONL files may be gzip
  compressed.
- [ ] For a full run, use the full CSV as both checker `--full` and `--analysis`.
  For a partial run, use the full CSV as `--full` and a CSV of the exact original
  rows in the submitted scope as `--analysis`. The scope CSV must preserve the
  six source fields and exact values. Save `local-reference.json` and
  `self-check.json` outside the grading export.
- [ ] Re-run the zero-API checker on the exact final package. Review its status,
  coverage, and issue list; resolve or explain every remaining issue. A passing
  mechanical audit does not establish label accuracy or turn a partial scope
  into a full run.
- [ ] Include the `cost/` calculator, actual pilot artifacts, dated rates,
  measurement notes, estimates, and offline replay instructions. Make clear
  which figures are measured and which are projected.

## Credentials and package safety

- [ ] Include `.env.example` with blank values and `.gitignore` with local
  credentials, source archives/data, runtime state, and checker references
  ignored. Never include `.env`, API keys, private key files, or key-bearing
  logs/screenshots.
- [ ] Before packaging, confirm `git check-ignore .env` recognizes the local
  secret file and inspect `git ls-files -- .env '.env.*'` and the staged file
  list. Only the intentionally blank `.env.example` may be tracked among those
  environment files.
- [ ] Do not include the raw source CSV or source ZIP unless the course
  explicitly requests them. Include the source manifest/checksums and concise
  reproduction instructions instead. Keep local references and generated
  checker reports outside the grading export.

## Dashboard final refresh

- [ ] Regenerate dashboard seed data from the final saved grading artifacts;
  do not hand-edit counts or quotes. Confirm the dashboard's displayed scope
  and completion status match the saved run manifest.
- [ ] Check that headline counts, ranking order, issue membership, review IDs,
  and evidence quotes match the final exports. Spot-check several rows against
  their original review texts.
- [ ] Remove stale checkpoint language, stale sample numbers, and development
  metrics from the final presentation, or label any retained development
  comparison clearly. Ensure incomplete or quarantined cases are represented
  accurately.
- [ ] Open the site in its intended access mode, verify the main views and
  `/api/insights` use the refreshed data, then record the checked URL and date
  in the submission notes. Do not call the dashboard final until that refresh
  and review are complete.
