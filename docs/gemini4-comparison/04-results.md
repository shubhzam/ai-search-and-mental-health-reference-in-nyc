# Gemini 4 comparison results · November 26, 2026

Neon, Hydrogen and Argon each completed the same 24 prompts as Carbon. This added 72 complete responses across 74 paid attempts: Hydrogen had two MAX_TOKENS responses, each followed by one successful retry. Both partial responses and their usage remain saved. Neon and Argon passed on their first attempts. No outstanding reservations or unresolved attempts remain.

All requests used live Google Search, the original concise instruction, an 8,192-token output limit and default thinking settings. Returned model IDs matched the requested IDs. Every completed response has visible text, STOP completion, search evidence and usable usage. Collection ran November 26, 00:14–01:05 EST (05:14–06:05 UTC). These are later search dates than Carbon's baseline; different default thinking behavior is another comparison variable.

| Model | Complete | Estimated token USD, including partials | Gross USD before search allowance | Grounding queries |
|---|---:|---:|---:|---:|
| Neon | 24 | $1.989825 | $4.509825 | 180 |
| Hydrogen | 24 | $1.511453 | $4.507453 | 214 |
| Argon | 24 | $0.136996 | $1.354996 | 87 |

Total estimated token charges are $3.638274, including both partial attempts. The gross estimate is $10.372274 before the shared Google Search allowance, across 481 queries. These are usage estimates, not a verified charge or remaining-credit balance. Costs follow the existing adapter's prompt/tool-use and candidate/thought token fields and the November 26 standard rates.

## Matching and persistence

The comparison manifest fixes the exact 24 prompt IDs and checksums of their Carbon baselines. Borough balance: Bronx: 6; Brooklyn: 4; Manhattan: 4; Queens: 4; Staten Island: 6. Payment balance: medicaid: 5; not_stated: 6; private_insurance: 7; uninsured: 6. These are previously collected questions, so the study still covers 200 distinct prompts.

The final audit verified all 676 host-local raw response files against PostgreSQL SHA-256 and parsed response JSON. There are 659 collection attempts and 17 pilot attempts, including 652 complete collection responses. All 72 new successful responses have valid start/finish timestamps, zero remaining reservations and exactly one successful answer per prompt/model. Each new model's successful prompt set equals Carbon's 24-prompt set.

Reopening all five saved Gemini 4 batch plans with provider calls disabled made zero additional requests. The two historical Hydrogen plans still correctly report their retained incomplete attempts; their continuation completed the missing answers. All 26 offline and isolated PostgreSQL tests passed, including exact plan validation, model identity, visible completion, usage rates, persistence and duplicate-safe resume.

## Reproduce and locate

Preview an approved model with `uv run --locked --python 3.13 referral-collector batch --gemini4-model gemini-4-neon --batch-id <unique-id>`. Save the plan before live use. For recovery, reopen the exact saved batch ID and plan; a fresh date is a different execution identity. Do not create a new run to inspect existing results.

Raw JSON, capture receipts and actual batch plans are under the ignored `data/live/collection/` folders beginning `gemini4-`, with immutable files for each execution. PostgreSQL `executions` identifies prompt/model and `attempts` stores request/response JSON, timestamps, usage and raw references. The full local audit is `data/gemini4-audit-20261126.json`. Credentials stay in ignored `.env`.

Only implementation, tests, reviewed manifests and aggregate results are published. Referral quality and citation accuracy have not yet been evaluated. The original three-model panel still has 168 fully matched prompts, with 12 Claude and 32 OpenAI answers missing.
