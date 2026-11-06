# Live-search pilot · Tech spec

## Version targets

Python 3.13 with proposed SDK targets `anthropic==2.6.0`, `openai==3.45.0`, and `google-genai==2.23.0`. These releases are published. Verify joint resolution and imports with `uv` before locking them. Live availability and tool behavior are pilot results.

[Anthropic SDK release](https://pypi.org/project/anthropic/2.6.0/) · [OpenAI SDK release](https://pypi.org/project/openai/3.45.0/) · [Google Gen AI SDK release](https://pypi.org/project/google-genai/2.23.0/)

## CLI and preflight

```sh
uv run --locked referral-collector pilot --prompt-id anc-03
uv run --locked referral-collector pilot --prompt-id anc-03 --live
```

The command is a proposal. Default mode previews only. Read the root manifests and evaluate eligibility on the current America/New_York date. Allow repeated `--model` filters for targeted checks. The first targeted pass selects `gemini-2.5-flash` and `claude-sonnet-4-5-20250929`. A subsequent pass skips already attempted models unless explicitly approved after billing reconciliation. Load `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, and `GEMINI_API_KEY` for selected providers from the environment or ignored local `.env`, with environment precedence. Validate all required keys and local storage before dispatch.

## Request and evidence contracts

Use the exact manifest model ID and the same prompt text with a shared instruction to search current sources and cite them. Use a 90-second request timeout, disable SDK retries, and set a proposed 1,500-token output limit. Record incomplete or truncated outputs as such.

| Provider | Request | Evidence of search |
|---|---|---|
| Claude | Messages with `web_search_20250305`, `max_uses=2` | Positive `usage.server_tool_use.web_search_requests` and a successful `web_search_tool_result` block |
| OpenAI | Responses with `web_search`, live external access, and source inclusion | Completed `web_search_call` whose action is `search` |
| Gemini | GenerateContent with `google_search` | Nonempty grounding search queries and web grounding sources on the answer candidate |

[Claude web search](https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool) · [OpenAI web search](https://developers.openai.com/api/docs/guides/tools-web-search) · [Gemini grounding](https://ai.google.dev/gemini-api/docs/generate-content/google-search?hl=en)

## Storage, spend, and failure

Write under `data/pilot/<run_id>/`. Store one immutable provider response per model and an attempt record with prompt ID, requested and reported model, SDK version, timestamp, response ID when available, status, search evidence, usage, and estimated USD. Use one local ledger across pilot runs and atomically record a reservation before dispatch. Hold the reservation if billing is unknown. Use a $9 operating ceiling within the $10 total per provider and stop before an attempt would exceed it based on recorded spend and the conservative reservation. Reconcile unknown charges against provider usage before continuing.

Return 0 when all selected attempts pass. Return nonzero for preflight, provider, search-evidence, budget, or persistence failure. Preserve any response with missing search evidence. Report timeouts as unresolved and stop further calls to that provider. No PostgreSQL tables, indexes, RabbitMQ messages, or automatic production seeding.
