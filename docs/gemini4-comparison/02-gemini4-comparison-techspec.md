# Gemini 4 comparison · Tech spec

Use Python 3.13, uv, google-genai 2.23.0 and current locked persistence dependencies. Model lookups for gemini-4-neon, gemini-4-hydrogen and gemini-4-argon returned 200 and generateContent support November 26. Model docs and [pricing](https://aistudio.google.com/docs/pricing) were checked. Existing synchronous request timeout remains 90 seconds with SDK automatic retries disabled.

Each saved plan uses cohort gemini4-comparison and includes the SHA-256 of docs/gemini4-comparison/review-manifest.json. A plan contains 24 entries for one approved model, in exact manifest prompt order, dated within November 26–30. An explicitly recorded continuation may contain an ordered subset and retry identities linked to failed attempts. Validation checks the fixed prompt hash and 24 Carbon baseline hashes, exact model ID, full request shape, eligibility and 8,192-token output limit.

Shared suffix remains the live-search instruction followed by the four-options/two-sentence/cost-and-eligibility/citation instruction. Use google_search and disabled automatic function calling. No explicit thinking level is set. Preserve provider defaults and actual token usage.

Standard USD per million input/output tokens are Neon 3/15, Hydrogen 1.5/7.5, and Argon 2/10 through November 30. Recheck Argon pricing from December 1. The gross tool estimate remains $0.014 per grounding query before the shared monthly free allowance. Token and gross estimates must be labeled separately in results.

Use existing executions and attempts tables. Save under data/live/collection/gemini4-<model>-20261126/. Each terminal passed record must have complete usable output, search evidence, usage, returned-model match, raw checksum, request/response JSON and timestamps. No schema changes. All keys and raw files stay ignored. Persist reservation before dispatch and raw bytes before terminal DB settlement.

DB outage prevents new dispatch. After-capture DB failure recovers from stored bytes. Missing/changed baselines or plan settings fail validation. Provider rejection, truncation, or unresolved usage stops that model's batch. Preserve uncertainty in provisional spend before a separately authorized retry; at most one retry per failed request in this run. Identical complete plan resumes issue zero paid calls.
