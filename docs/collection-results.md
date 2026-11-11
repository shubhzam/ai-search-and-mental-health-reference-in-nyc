# NYC referral study collection results

The study compares `gemini-3.8-flash`, `claude-sonnet-4-5-20250929`, and `gpt-4o-2024-08-06` on the same prompts using live search and a 2,200-token output limit. Both batches used the shared study instruction. Actual collection occurred outside the originally proposed morning window.

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

Five responses passed. Gemini returned `MAX_TOKENS` for `g-290` and omitted the answer-token count. The raw response is saved locally and the $0.50 reservation remains held while spend is unresolved. The runner stopped without retrying, leaving 24 requests pending.

| Provider | Passed | Estimated batch cost |
|---|---:|---:|
| Gemini | 1 | $0.0653 |
| Anthropic | 2 | $0.1269 |
| OpenAI | 2 | $0.1153 |

Fully matched prompt IDs: `g-452`.

## Study progress and budget

35 of 144 planned study responses passed. 109 still need a complete response. Pilot attempts are excluded from progress.

| Provider | Estimated pilot and collection spend | Outstanding reservation | Additional uncertainty allowance | Room under $9 operating limit |
|---|---:|---:|---:|---:|
| Gemini | $0.7773 | $0.50 | $0.01 | $7.7127 |
| Anthropic | $1.2638 | $0.00 | $0.00 | $7.7362 |
| OpenAI | $1.0158 | $0.00 | $0.00 | $7.9842 |

Spend is estimated from usage. The operating limit is $9 per provider, within a $10 total cap per provider. Raw responses and attempt records are retained locally in the ignored data directory.
