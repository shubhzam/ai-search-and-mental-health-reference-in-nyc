# Gemini 4 daily collection · Tech spec

Python 3.13, uv and existing locked google-genai 2.23.0. Four authenticated model lookups verified generateContent support November 26. Use existing synchronous search adapter, 90-second default timeout and disabled SDK retries. After two saved daily Neon deadline errors, explicit daily plans may set transport_timeout_ms=180000; record this value in each attempt. Older and original comparison plans retain the 90-second default. No schema/dependency migration.

Add cohort gemini4-daily using docs/gemini4-daily/review-manifest.json. The manifest contains twelve distinct fixed prompt IDs, four exact Gemini 4 model IDs, baseline raw references and hashes, source prompt hash, 8,192-token limit and inclusive November 26–30 eligibility. Each plan contains twelve entries for one model; an explicit continuation contains an ordered subset. Preserve original gemini4-comparison validation unchanged.

Add build_gemini4_daily_plan(model_id) and batch --gemini4-daily-model with Carbon, Neon, Hydrogen and Argon choices. Preview validates without provider calls. Existing --plan accepts saved daily plans. Each plan binds the manifest SHA-256 and original input hashes. Existing request-shape, date, retry identity, completion, visible-text and returned-model checks apply.

Use existing executions/attempts tables and data/live/collection/daily4-<model>-20261126-<sequence>/. Reserve before dispatch; persist immutable response and receipt before DB settlement. Record estimated usage for every attempt. Incomplete output receives at most one linked operational retry. A saved terminal HTTP 504 may receive one linked retry after retaining its full original reservation as a labeled provisional estimated charge; preserve the error JSON and accounting history. Credit rejection receives no retry. Repeated failure, credit rejection or unresolved usage stops that model and is reported. An unresolved shared-provider reservation stops all Gemini dispatch.

Model rates per million input/output USD: Carbon 2/10, Neon 3/15, Hydrogen 1.5/7.5, Argon 2/10 through November 30. Gross search estimate .014/query precedes free allowances and is not an account balance. Existing process-local cap override follows prior user instructions.

Missing or changed raw baseline, wrong prompt/model/settings, duplicate identity, or modified manifest hash rejects the plan. DB failure prevents a new provider call. Recover captured raw bytes before retrying interrupted persistence. No referral interpretation or original-panel replacement.
