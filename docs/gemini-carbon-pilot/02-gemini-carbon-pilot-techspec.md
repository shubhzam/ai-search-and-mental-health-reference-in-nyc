# Gemini Carbon pilot · Tech spec

Runtime targets are Python 3.13, uv, google-genai 2.23.0 and the existing locked persistence dependencies. No package upgrade is planned. The November 24 model lookup verified generateContent visibility for the configured project key. Generation and search success remain pilot checks.

Official references checked November 24, 2026: [Carbon model](https://aistudio.google.com/docs/models/gemini-4-carbon), [Google Search grounding](https://aistudio.google.com/docs/google-search), [pricing](https://aistudio.google.com/docs/pricing).

The exact twelve prompt IDs and baseline response references are in review-manifest.json. All selected Flash responses have an 8,192-token cap. Carbon uses the same source prompt and shared suffix, google_search enabled, automatic function calling disabled, and max_output_tokens 8192. The inherited request timeout is 90 seconds and SDK retries are disabled. Requested model is gemini-4-carbon. Do not set an explicit thinking level in this first pilot; save any provider-returned settings and usage.

Append these two instructions separated by blank lines:

```
Search the live web for current options and cite your sources.

Give up to four relevant options. Keep each to two sentences, note any cost or eligibility you can verify, and cite your sources.
```

Implement a reviewed Carbon pilot manifest option in the existing batch plan validation. Bind the exact model, prompt selection, source hashes and eligibility date range to the pilot docs. Keep the original model panel intact. Planned eligibility is November 24–30 inclusive for this pilot's pricing window. A later invocation needs pricing revalidation.

The standard input/output rates through November 30 are $2/$10 per million tokens, including thinking output. From December 1 the documented rates become $4/$20. Twelve responses at the full output cap cost at most $0.98304 in output charges, plus input/tool-context charges. This is not a total batch ceiling. Search pricing has 5,000 monthly free requests shared across Gemini 3 and newer models, then $0.014 per query. Retain the gross tool estimate with an explicit free-allowance caveat.

Use existing executions and attempts tables, preserving scope collection, exact model identity, request/response JSON, UTC timestamps, usage, cost estimate, and raw path/hash. Save live files under data/live/collection/gemini-carbon-pilot-20261124/. Store cohort identity in the saved plan, and filter the pilot by model ID in analysis. Existing indexes cover C2.

Errors stop further pilot dispatch. Passed requires provider completion, visible answer text, grounding queries/sources, usable token accounting, matching requested/returned model, local raw bytes and committed database response. Missing/mismatched files or changed reviewed inputs fail before success reporting. Credential values remain outside artifacts and logs.

## Implemented commands and verification

The approved pilot ran November 25. Preview and save its exact plan using:

```sh
uv run --locked --python 3.13 referral-collector batch --carbon-pilot \
  --batch-id gemini-carbon-pilot-20261125 \
  --write-plan data/plan-gemini-carbon-pilot-20261125.json
```

Load the saved plan with --plan and --live using the same batch ID. The completed pilot files are under data/live/collection/gemini-carbon-pilot-20261125/. Validation binds the pilot cohort, exact prompt order, manifest hash, source prompt hash, baseline hashes, model, date range, and request settings. The Carbon observer requires visible output and a matching model ID in addition to completion. Three new tests passed alongside the existing nineteen tests, including fake Carbon database persistence and duplicate resume.
