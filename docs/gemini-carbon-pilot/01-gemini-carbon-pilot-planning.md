# Gemini Carbon pilot · Planning

Test Gemini 4 Carbon on twelve questions that already have complete responses from the original three-model panel. This provides a paired comparison of Carbon and Flash on referral selection, cited sources, and cost/eligibility details. Collection time remains a comparison variable because live search results can change.

The user approved the proposed twelve-question pilot. A non-generating model lookup on November 24 returned HTTP 200 for gemini-4-carbon, advertised generateContent support, and a 32,768-token output ceiling. The documentation advertises 65,536 synchronous output tokens. Our requested 8,192 is below both ceilings. Search execution and SDK compatibility still require a live response.

Select the first twelve eligible prompts from the existing deterministic borough/payment ordering that have passed on all three original models and have an 8,192-token Flash baseline. This avoids choosing questions by apparent answer quality. Save exact baseline references and hashes in review-manifest.json. The small sample is exploratory and does not guarantee equal coverage of every mental-health need.

This is the existing sequential reservation, dispatch, capture and persistence process with an additional model. Execution identity includes the Carbon model ID. A shared prompt ID does not duplicate an original execution because the model differs. PostgreSQL owns execution/attempt state, and host-visible raw storage retains response bytes. Keep retries explicit and stop on incomplete output, missing search evidence, ambiguous billing, or provider error.

| Access | Key | Size / frequency |
|---|---|---|
| C1 | Reviewed pilot manifest and baseline references | Twelve prompts; once per pilot |
| C2 | Execution and attempt identity | Twelve Carbon executions; existing database indexes |
| C3 | Response and usage | One capture and settlement per request |

Extend plan validation narrowly for this reviewed pilot model and source manifest. Preserve strict request comparison. Use the existing Gemini adapter and immutable capture path. A schema migration is unnecessary because model IDs are stored as text. Add Carbon rates and explicitly label monetary figures as usage estimates. Free-search allowances are shared across the billing account's eligible models and cannot be inferred solely from this repo.

Before live dispatch, verify twelve planned jobs, unchanged prompt/hash references and exact settings in offline tests. Start with the first pilot request and continue only after observing complete output, nonempty visible text, live-search evidence, usage and a matching local checksum/DB response. Reopening a completed pilot must send zero duplicate requests. Database failure before dispatch must prevent spending; failure after capture must recover from the saved bytes. No automatic retry or sample expansion is authorized.
