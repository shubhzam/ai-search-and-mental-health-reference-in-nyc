# Gemini 4 daily collection · Dataflow

Read the separate twelve-question manifest and verify all Flash baseline checksums. For g-193/Carbon, construct 2026-11-26__g-193__gemini-4-carbon with the original prompt plus the live-search and concise-options suffix. Request google_search with 8,192 output tokens and default thinking.

The batch runner validates the plan and eligibility, imports any missing historical records and obtains the shared collection lock. Reserve the attempt in PostgreSQL, call generateContent, then capture response.json and receipt.json beneath data/live/collection/daily4-carbon-20261126-00/<execution-key>/. Verify visible complete output, matching returned model, grounding evidence and usage. Commit JSON, timestamps, raw SHA-256 and terminal status before the next request.

Repeat those exact questions for the other three models. Compare each successful prompt set with the twelve fixed IDs; verify local raw bytes against DB JSON and hashes. Preserve the original 24-question comparison manifest and plans.

Failure example: MAX_TOKENS commits an incomplete response and its usage. A continuation uses the same execution with __retry-1 and retry_of pointing to the original key. Keep both raw files. A DB outage after capture requires recovery from the saved body before any new dispatch. Unresolved billing stops the shared Gemini provider.
