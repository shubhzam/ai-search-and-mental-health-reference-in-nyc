# NYC referral study collection results

The study compares `gemini-3.8-flash`, `claude-sonnet-4-5-20250929`, and `gpt-4o-2024-08-06` on the same prompts using live search and the shared study instruction. The original requests used a 2,200-token output limit. The Gemini retry and evening Gemini requests used 8,192. Actual collection occurred outside the originally proposed morning window.

## November 10, 2026 · 10:05 PM to 10:12 PM EST

10 fully matched prompts. 30 complete responses with verified live-search evidence and matching raw-file checksums. 30 planned responses in this batch.

Status counts: passed 30.

| Provider | Passed | Estimated batch cost |
|---|---:|---:|
| Gemini | 10 | $0.5848 |
| Anthropic | 10 | $0.7963 |
| OpenAI | 10 | $0.5835 |

Fully matched prompt IDs: `g-118`, `g-315`, `g-437`, `g-217`, `g-249`, `g-446`, `g-271`, `g-287`, `g-321`, `g-100`.

## November 11, 2026 · 01:26 PM to 01:28 PM EST

One fully matched prompt and five complete responses with verified live-search evidence and matching raw-file checksums. The batch planned 30 responses.

Five responses passed. Gemini returned `MAX_TOKENS` for `g-290` and omitted the answer-token count. The runner stopped, leaving 24 requests pending. The original raw response is saved locally, and the full $0.50 reservation is now recorded as a provisional charge against the budget. Actual billing for that attempt remains unconfirmed.

| Provider | Passed | Estimated batch cost |
|---|---:|---:|
| Gemini | 1 | $0.0653 |
| Anthropic | 2 | $0.1269 |
| OpenAI | 2 | $0.1153 |

Fully matched prompt IDs: `g-452`.

At 5:01 p.m. EST, a single manual Gemini retry completed `g-290` with two observed searches and a verified raw response. It used the same prompt and search settings with an 8,192-token output limit. The estimated retry cost was $0.0353. This brings November 11 to two fully matched prompts and six complete responses. The `g-290` comparison used different output limits across providers.

## November 11 evening continuation

Actual collection ran from 09:44:38 PM to 09:50:05 PM EST.

The continuation selected the eight untouched prompts from the November 11 assignment. Gemini used 8,192 output tokens. Claude and OpenAI used 2,200. All three used the same study prompt and live search settings.

Outcomes across 24 planned requests: 24 passed.

| Provider | Verified complete responses | Estimated cost |
|---|---:|---:|
| Gemini | 8 | $0.4859 |
| Anthropic | 8 | $0.6599 |
| OpenAI | 8 | $0.4668 |

8 fully matched prompts in this continuation. Prompt IDs: `g-114`, `g-253`, `g-225`, `g-423`, `g-125`, `g-144`, `g-358`, `g-018`.

## November 12–13 original study completion

November 12 added 36 responses for its scheduled assignments and 36 more that evening for the November 13 assignments. The November 13 morning closeout filled the 12 outstanding November 10 and 11 assignments. The saved records include actual UTC timestamps and planned dates.

All 144 original assignments are verified, with 48 complete responses per provider and 48 fully matched prompts.

## November 13 supplemental batch

Collected 05:43 PM to 05:52 PM EST. The batch used the next 12 unused prompts in the deterministic borough and payment ordering, with three prompts per payment condition. Gemini used an 8,192-token output limit, and Anthropic and OpenAI used 2,200. All requests used the shared study instruction and live search.

12 fully matched prompts. Outcomes across 36 planned supplemental requests: 36 passed.

Prompt IDs: `g-080`, `g-219`, `g-162`, `g-006`, `g-333`, `g-172`, `g-415`, `g-252`, `g-104`, `g-182`, `g-426`, `g-205`.

| Provider | Verified complete responses | Estimated batch cost |
|---|---:|---:|
| Gemini | 12 | $0.7685 |
| Anthropic | 12 | $0.8950 |
| OpenAI | 12 | $0.7024 |

## November 14 supplemental batch

Collected 10:40 AM to 10:40 AM EST. The batch used the next 12 unused prompts in the deterministic borough and payment ordering, with three prompts per payment condition. Gemini used an 8,192-token output limit, and Anthropic and OpenAI used 2,200. All requests used the shared study instruction and live search.

Anthropic rejected the first request with a low API credit balance error. The runner saved the error response locally and stopped. The remaining 35 requests were pending when that batch stopped. The original reservation was later moved to a $0.50 provisional charge, and Claude collection resumed after credentials were updated.

Prompt IDs: `g-356`, `g-019`, `g-021`, `g-335`, `g-068`, `g-148`, `g-035`, `g-052`, `g-140`, `g-160`, `g-046`, `g-062`.

| Provider | Verified complete responses | Estimated batch cost |
|---|---:|---:|
| Gemini | 0 | $0.0000 |
| Anthropic | 0 | $0.0000 |
| OpenAI | 0 | $0.0000 |

## November 17–18 supplemental collection

The November 17 morning run saved 24 complete Gemini and OpenAI responses. Claude catch-up saved 12 complete responses that evening, including the retry for `g-356`. November 18 added 36 complete responses across 12 more prompts. Together these runs added 24 fully matched prompts.

## Verified inventory and storage

| Scope | Executions | Attempts | Successful responses | With response JSON | Fully matched prompts |
|---|---:|---:|---:|---:|---:|
| Collection | 312 | 314 | 312 | 314 | 104 |
| Pilot | 17 | 17 | 9 | 17 | 1 |

The collection includes 144 executions matching the original schedule and 168 supplemental executions. Each provider contributed 104 successful collection responses. Two executions have a second attempt: Gemini `g-290` (incomplete → passed) and Claude `g-356` (rejected → passed). All 17 pilot finish timestamps are unknown and stored as null.

On November 19, migration 002 was applied to the local Docker PostgreSQL database. The historical import inserted 271 attempts; a second import inserted zero. New manual runs now persist directly to that database. The November 20 audit verified all 325 raw response files against database hashes and JSON bodies, including pilots and failed attempts. PostgreSQL uses the persistent `project_postgres-data` volume with fsync and synchronous_commit enabled. A separate backup/restore test remains pending.

New pilot and batch runs reserve spend in PostgreSQL before dispatch, save immutable raw bytes under `data/live/`, and commit the terminal outcome and full parsed response in PostgreSQL. Interrupted writes can recover from saved bytes. The historical ledgers and responses remain under `data/collection/` and `data/pilot/`.

## November 19–20 collection

November 19 added 36 complete responses across 12 prompts. November 20 added nine responses across three prompts, followed by three single-prompt runs. The collection now has 306 complete responses across 102 matched prompts, with 102 successful responses per provider. All 54 new responses have PostgreSQL request and response JSON, usage, raw-file hashes, and actual start/finish timestamps.

OpenAI's valid null error field initially caused one successful response to be classified as unresolved. The parser check was fixed and the stored raw response was reconciled without repeating the provider request. All 19 fake-provider and database tests passed after adding null-error coverage.

The November 20 single-prompt runs used temporary reservations of $0.40 and $0.30. The final single-prompt run used the standard $0.50 reservation with an explicitly authorized operating-threshold override, bounded by the $10 provider cap. These overrides were process-local and are recorded in the saved plans.

## November 21 collection

The morning and evening runs added one unused matched prompt each, g-258 and g-277. All six responses passed and are stored in PostgreSQL with raw files, timestamps, usage, and checksums. The collection now has 312 complete responses across 104 matched prompts, 104 per provider. The final audit checked 331 raw files including pilots and unsuccessful attempts.

The morning run used a disclosed $0.20 reservation. The evening run used the standard $0.50 reservation with the authorized process-local operating-threshold override bounded by the $10 total provider cap. Raw plans record the settings.

## Shared provider budget

| Provider | Accounted pilot and collection spend | Outstanding reservation | Additional uncertainty allowance | Room under $10 cap |
|---|---:|---:|---:|---:|
| Gemini | $7.1600 | $0.00 | $0.01 | $2.8300 |
| Anthropic | $8.9742 | $0.00 | $0.00 | $1.0258 |
| OpenAI | $6.3625 | $0.00 | $0.00 | $3.6375 |

Estimates include the $0.50 Gemini and $0.50 Anthropic provisional charges. The default operating limit is $9 per provider within the $10 total cap. Raw data and credentials stay in ignored local storage.
