# NYC referral study collection results

The study compares `gemini-3.8-flash`, `claude-sonnet-4-5-20250929`, and `gpt-4o-2024-08-06` on the same prompts using live search and the shared study instruction. The original requests used a 2,200-token output limit. The Gemini retry documented below used 8,192. Actual collection occurred outside the originally proposed morning window.

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

## Study progress and budget

36 of 144 planned study responses passed. 108 still need a complete response. Pilot attempts are excluded from progress.

| Provider | Accounted pilot and collection spend | Outstanding reservation | Additional uncertainty allowance | Room under $9 operating limit |
|---|---:|---:|---:|---:|
| Gemini | $1.3126 | $0.00 | $0.01 | $7.6774 |
| Anthropic | $1.2638 | $0.00 | $0.00 | $7.7362 |
| OpenAI | $1.0158 | $0.00 | $0.00 | $7.9842 |

Spend is estimated from usage. The operating limit is $9 per provider, within a $10 total cap per provider. Raw responses and attempt records are retained locally in the ignored data directory.
