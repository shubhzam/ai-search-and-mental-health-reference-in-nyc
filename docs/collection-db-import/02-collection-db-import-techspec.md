# Collection database import · Tech spec

## Scope and runtime

Python 3.13 and uv with existing locked Psycopg and Pydantic dependencies. PostgreSQL 17. No provider requests are part of this import. The implementation will use explicit migration 002 after plan approval.

Official references checked November 18, 2026: [PostgreSQL JSON types](https://www.postgresql.org/docs/17/datatype-json.html) and [Psycopg transactions](https://www.psycopg.org/psycopg3/docs/basic/transactions.html).

## Proposed CLI

`uv run --locked --python 3.13 referral-collector import-collection --dry-run`

Replace --dry-run with --apply to commit. Modes are mutually exclusive. Default root is project data/. Print source counts and inserted/unchanged totals. Validation, source conflicts and database failures exit nonzero. Database connection errors suppress credential-bearing details.

## Proposed schema

| Table | Fields and contracts |
|---|---|
| executions | execution_id text primary key (I2), scope pilot/collection, prompt_id, requested_model, provider, nullable planned_date, outcome passed/incomplete/rejected/unresolved/pending |
| attempts | source_path text primary key (I2), execution_id foreign key, batch_id, status, nullable started_at/finished_at timestamptz, nullable returned_model and response_id, nullable usage JSONB, estimated_usd and reserved_usd numeric, output_token_limit integer, ledger_sha256, nullable raw_path and raw_sha256, metadata JSONB, nullable response JSONB |

An index on attempts.execution_id supports I2 execution-history reads. No JSONB index is required for the initial dataset. Source paths are project-relative. Store full attempt metadata in metadata and full parsed response or provider error body in response. Verify passed raw-file checksums before committing. Derive execution identity from retry_of when present, otherwise execution_key. Pilot identity includes pilot run directory. Preserve missing pilot finish times as null.

## Validation and writes

Validate all source paths stay under data/, every successful response has search/completion evidence, recorded hashes match where available, timestamps parse, and money fields are finite/nonnegative. Import partial/error bodies with their recorded statuses. Missing raw files are permitted only for attempts whose recorded state allows no response. Report every such case.

Use the shared collection lock during snapshot creation and persistence. One database transaction serializes importers, compares existing source rows and hashes, inserts new executions/attempts, and updates derived execution outcome from preserved attempts. Any passed attempt makes its execution passed. Otherwise unresolved takes priority over incomplete and rejected. No job catalog expansion is implied by importing supplemental executions.

## Edge cases

- Repeated identical sources produce unchanged counts.
- Changed existing ledger/raw content aborts for explicit reconciliation.
- Retry records join the original execution and retain their distinct source paths.
- Missing timestamps remain null and are reported.
- Invalid JSON, mismatched hashes, or unwritable inventory output fail before commit.
- A missing migration or database outage returns nonzero; no partial import is committed.
