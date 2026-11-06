# Seed job definitions · Planning

## What this feature owns

The seed command turns the approved study inputs into a PostgreSQL catalog of what should run and on which dates. Loading the catalog before collection makes it possible to inspect daily coverage and catch omissions before the collection window. The design keeps prompt text and grid metadata in `prompts.csv` and model metadata in `models.yaml`. Keep the exact input files with the study so an ID can still be traced to the same prompt or model later.

## Pattern and entities

This is a multi-step process with a contention boundary. Read and validate both manifests, expand them into candidate definitions, then commit the catalog change in one transaction. Realtime updates, long-running tasks, scaling reads or writes, large blobs, and proximity do not drive this one-time load.

The manifests own prompt and model IDs. One prompt and one model can each appear in many definitions. A definition owns a schedule interval and arm. An execution represents one occurrence on a particular date. An attempt is a try within that occurrence. The seed command creates definitions only. A provider task ID names a callable role in the design.

## Access patterns

| ID | Operation | Filter or key | Size and frequency |
|---|---|---|---|
| S1 | Read current definitions and check proposed intervals | Whole catalog, compare by prompt/model | One catalog scan per seed invocation |
| S2 | Insert and identify repeats | Arm, prompt ID, model ID, start date | One row per definition, during seeding |

## Decision log

1. Store anchor schedules as inclusive intervals and dated schedules as single-day intervals. A prompt/model-only primary key would collapse different dates. A random ID alone would let a retry duplicate definitions.
2. Use a natural key of arm, prompt, model, and start date. Separately reject overlapping intervals for the same prompt/model across arms because the walkthrough derives execution identity from that pair and date. Silently accepting an overlap would make one scheduled occurrence disappear. Confirm whether the study intends any such repeats.
3. Compare rows inside one transaction while holding a table lock that serializes writers and permits ordinary reads. An exact repeat is unchanged. Changed values under the same key and overlapping intervals abort the batch. A blind conflict skip would hide changed input. Row-level coordination could help if catalog writes became frequent.
4. Use plain parsing, expansion, and persistence functions. The first operational symptom to watch for is a seed blocked by another writer. Use a bounded lock wait and report the failure.

## Review before implementation

The supplied walkthrough gives a daily window of November 9–December 20, 2026 and a November 8 burst. Confirm that the CLI date flags bound the daily arm only, plus the pilot date and panel membership. Confirm the approved manifests and rotation policy. Twelve slots per day for 42 days require 504 assignments, and the walkthrough names a 480-prompt grid. If that is the rotation pool, a single shuffle without reuse cannot fill the window. Also confirm the final eligibility dates in the model manifest.

## Definition of done

With a small fixture, verify expected rows, a repeat with zero inserts, rejection of a changed row and an overlap, and two concurrent identical seeds. With PostgreSQL stopped, verify a nonzero exit and rerun successfully after restart. Validate daily counts against the approved study manifests once supplied.
