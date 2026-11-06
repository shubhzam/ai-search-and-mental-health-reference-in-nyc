# Seed job definitions · Tech spec

## Revised matched-study preview

The budget-limited study uses up to 48 distinct prompts. Preview it with
`uv run referral-collector seed --dry-run --start 2026-11-09`.
The command reads `prompts.csv` and `models.yaml` from the current directory by default.
`--days` defaults to 4 and `--prompt-count` to 48. Each selected prompt runs on one date
with every model in the manifest. Each model must be eligible for the entire window.
The preview samples across borough and payment-condition combinations using seed
`20261109`, prints the dated jobs and per-provider totals, and performs no writes
or provider calls. The preview excludes pilot and burst jobs. The full-study CLI
proposal below is retained as design history.

## Version targets and status

Python 3.13, PostgreSQL 17, Psycopg 3.3.8, Pydantic 2.14.3, and pydantic-settings 2.16.2 match the scaffold and its lockfile. PostgreSQL locking and Psycopg transaction semantics are checked against official docs. The preview uses PyYAML 6.0.3 with safe loading. Provider model access and actual search execution are pending pilot verification.

[PostgreSQL locking](https://www.postgresql.org/docs/17/sql-lock.html) · [PostgreSQL inserts](https://www.postgresql.org/docs/17/sql-insert.html) · [Psycopg transactions](https://www.psycopg.org/psycopg3/docs/basic/transactions.html)

## Interface and requirements

Proposed entry point, using the existing collector CLI:

```sh
uv run referral-collector seed --arms pilot,burst,daily \
  --start 2026-11-09 --end 2026-12-20 \
  --prompts prompts.csv --models models.yaml
```

The command uses `REFERRAL_DATABASE_URL`. File paths are explicit. Proposed contract for review: the inclusive start and end bound the daily arm. Dated pilot and burst inputs come from the approved study plan. Daily anchors generate `DAILY` rows. Rotation, pilot, and burst generate `DATE` rows. Daily rotation uses seed `20261109`; the pool, ordering and exhaustion rule require approval before implementation. Apply approved model eligibility dates inclusively. Map provider to its documented search task ID and require search on.

Input validation requires unique prompt IDs and globally unique pinned model IDs, supported provider names, valid dates and known references. Required source fields and arm membership rules will be finalized against the manifests. The CLI prints `inserted=N unchanged=N` after commit, exits 0 on success and exits nonzero on configuration, validation, conflict, or database failure.

## Schema

Explicit migration creates `job_definitions`. All fields are required.

| Field | Type and contract |
|---|---|
| arm | text, one of `pilot`, `burst`, `daily` |
| prompt_id, model_id | text, IDs in the input manifests |
| task_id | text, one of `anthropic_search`, `openai_search`, `gemini_search` |
| schedule_type | text, `DAILY` or `DATE` |
| run_from, run_until | date, inclusive, ordered and equal for `DATE` |
| search_enabled | boolean, true |

Primary key and its index (S2) cover `(arm, prompt_id, model_id, run_from)`. S1 scans the table. Manifest IDs are validated in the loader. There are no database foreign keys to files.

## Transaction and edge cases

Use a read-committed transaction with a proposed five-second lock timeout. Acquire `SHARE ROW EXCLUSIVE` before reading the catalog. Reject duplicate input keys. Count exact stored matches as unchanged. Reject changed rows under an existing key or inclusive interval overlaps for the same prompt/model across distinct rows. Insert new rows and commit once. A lock timeout, missing migration, or database disconnect returns an error. If the connection fails at commit and the outcome is unknown, rerun with identical inputs.

This feature excludes execution rows, provider calls, queue traffic, and study scheduling at runtime.
