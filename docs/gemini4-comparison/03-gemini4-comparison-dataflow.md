# Gemini 4 comparison · Dataflow

Read the comparison manifest containing 24 Carbon prompt IDs and baseline hashes. Resolve each source text from prompts.csv and construct the approved suffix. For Neon, the first execution key includes planned date, prompt ID and gemini-4-neon. Argon and Hydrogen use their own exact model IDs and independent execution rows.

The normal batch runner validates the manifest and raw baselines, imports any missing historical ledgers, then reserves one attempt in PostgreSQL. Send one synchronous generateContent call with live search and 8,192 output tokens. Capture HTTP bytes and receipt under the host-visible data/live/collection model batch folder. Verify complete visible answer, grounding sources and queries, usage and returned model. Commit the outcome, response JSON, raw path and checksum before the next request.

After each model, query PostgreSQL for exactly 24 successful prompt IDs and compare that set to Carbon. Parse every raw file and compare its checksum and JSON to the database. Summarize token charges separately from hypothetical search charges before allowances. Update repository docs and push only implementation, tests, reviewed manifests and summaries.

Failure trace: an API timeout leaves uncertain spend. Preserve error/raw receipt and original reservation. If the saved provider body establishes a terminal error, retain the full reservation as a provision before recording a separate retry linked to that execution. A successful request is never retried. If failure remains unresolved or a credit rejection prevents progress, report the pending set instead of claiming 24 completed.
