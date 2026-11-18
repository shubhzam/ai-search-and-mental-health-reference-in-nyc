# Collection database import · Planning

## Purpose and evidence

Make saved collection history queryable in PostgreSQL before analysis. Local collection currently has 254 attempts, including 252 successful responses across 84 matched prompts, one incomplete response and one rejected request. Another 17 pilot attempts must remain identifiable as pilot data. Existing PostgreSQL job definitions cover the original 144 assignments. Supplemental collection extends beyond that catalog.

## Pattern and entities

This is a multi-step validation and atomic persistence process. Plain importer functions suffice. An execution groups attempts for one planned prompt/model/date. A retry links to its original execution through retry_of. A source attempt is uniquely identified by its project-relative ledger path. A provider response belongs to that attempt. Pilot executions use their run directory plus prompt/model identity because earlier records lack execution keys. Preserve unknown timestamps as null. File modification times cannot supply missing provider timing.

| ID | Access | Size and frequency |
|---|---|---|
| I1 | Validate all ledger and response pairs | 271 attempts at handoff, once per import |
| I2 | Compare stored source identity and content hashes | Once per attempt per import |
| I3 | Group completed collection by prompt/model | 252 successful study attempts, analysis queries |

Execution and source-path primary keys serve I2. An execution foreign-key index serves attempt lookup. A small table scan serves I3 initially.

## Decisions

Import all attempts and preserve pilot versus collection scope. Store searchable metadata and full response JSON in PostgreSQL, alongside raw-file paths and SHA-256 hashes. Host raw files retain exact response bytes. Keeping a database response copy makes immediate response inspection possible in SQL. Treat the raw files as the byte-level record.

Use separate executions and attempts so failed requests and later successes survive together. Do not require supplemental executions to reference a job definition that was never seeded. Preserve original metadata in JSONB and retain explicit columns for dates, timestamps, usage, cost, model, status and token limit. Preserve provisional cost notes and original statuses.

Validate the complete inventory before one transaction. Identical reruns report unchanged rows. Changed source content aborts with an explicit conflict, preventing silent loss of historical accounting. Import after collection processes release their shared lock. Serialize database import writers with a transaction lock. A disconnect or invalid raw file aborts the batch; rerun the identical inputs after recovery.

## Definition of done

Dry-run reports counts and missing/inconsistent files. Apply matches 254 collection attempts and 17 pilot attempts at this snapshot. SQL confirms 252 successful collection attempts, 84 prompts and 84 per provider, with original/retry history linked correctly. Reapply inserts zero rows. Verify rollback on a changed source, duplicate protection, and database failure recovery. Reconcile a database response with the local file checksum. Stop for plan review before implementation, following the project instruction.
