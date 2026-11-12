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

## Study progress and budget

60 of 144 planned study responses passed. 84 still need a complete response. Pilot attempts are excluded from progress.

| Provider | Accounted pilot and collection spend | Outstanding reservation | Additional uncertainty allowance | Room under $9 operating limit |
|---|---:|---:|---:|---:|
| Gemini | $1.7986 | $0.00 | $0.01 | $7.1914 |
| Anthropic | $1.9237 | $0.00 | $0.00 | $7.0763 |
| OpenAI | $1.4825 | $0.00 | $0.00 | $7.5175 |

Spend is estimated from usage and includes the $0.50 Gemini provisional charge. The operating limit is $9 per provider, within a $10 total cap per provider. Raw responses and attempt records are retained locally in the ignored data directory.
