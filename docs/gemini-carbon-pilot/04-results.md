# Gemini Carbon pilot results

The approved twelve-question pilot completed November 25, 2026. All twelve requests passed with the exact gemini-4-carbon model, visible answer text, STOP completion, Google Search grounding evidence, and usable token counts. Each used an 8,192-token limit and the original shared study instruction.

All twelve responses are committed to PostgreSQL with request/response JSON, usage, timestamps and raw-file checksums. The nonempty host-local raw files matched both checksums and parsed database JSON. All thirty-six baseline response references retained matching checksums. Reopening the completed pilot made zero additional provider calls.

Estimated token charges were $0.213416. The provider returned 64 grounding queries. The ledger gross estimate was $1.109416, including $0.896 in search charges before free allowances. The actual billed amount depends on account-level allowance usage and provider billing. The token estimate also follows the existing adapter's reported prompt/tool-use token fields; it is not an invoice reconciliation.

The dataset now includes 200 successful Flash responses, 188 Claude responses, 168 GPT-4o responses, and 12 Carbon responses. That is 568 complete responses across 200 distinct study prompts. The original three-model comparison still has 168 fully matched prompts and 44 missing responses. Carbon provides twelve additional answers to existing questions and does not fill those original-model gaps.

The twelve questions were chosen deterministically from existing matched prompts with an 8,192-token Flash baseline. Live-search dates differ, and no referral-accuracy or quality advantage has yet been established. That requires response/citation analysis.

Twenty-two offline and fake-provider/database tests passed. No dependencies or schema migration were required. The original panel manifest remains available, while Carbon uses a dedicated reviewed cohort. The user's prior instruction to disable application spend limits applied to this finite pilot, which stopped at twelve requests.
