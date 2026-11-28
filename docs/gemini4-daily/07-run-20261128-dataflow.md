# November 28 immediate run · Dataflow

Resolve review-20261128.json under the daily docs directory. Hash the file and verify its twelve Flash baseline raw hashes. For g-108/Neon, form 2026-11-28__g-108__gemini-4-neon with the unchanged source text and shared suffix. Save the plan with daily_review_manifest, manifest checksum and transport_timeout_ms=180000.

The existing runner locks collection, reserves the execution in PostgreSQL, calls live Google Search, atomically saves response.json and receipt.json to data/live/collection/daily3-neon-20261128-00/<execution-key>/, then commits response JSON, checksum, usage and timestamps. Repeat the same twelve questions for Hydrogen and Argon only.

A completed attempt resumes from its stored identity without another provider call. A MAX_TOKENS result remains an incomplete stored attempt; one linked __retry-1 may follow. A captured provider 504 retains original bytes and an explicit provisional charge before one linked retry. Missing raw bytes or unreconciled transport state stops collection. Audit every new result and all existing raw references; publish code and aggregate docs, keeping raw bytes and credentials local.
