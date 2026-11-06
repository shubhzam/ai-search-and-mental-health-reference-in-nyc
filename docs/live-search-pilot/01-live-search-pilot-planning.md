# Live-search pilot · Planning

## What the pilot answers

Send one shared prompt to each eligible model in the manifest. Check whether the study credentials can reach that exact model, whether a live search actually ran, and how much usage one response incurred. The pilot informs the model panel and sample size for the matched study. A single response per model gives an early cost signal and a response format to inspect.

Start with Gemini 2.5 Flash and Claude Sonnet 4.5 because their documented access restrictions make them the most likely to block the panel. Review the dry-run plan and choose a budget reserve for each request before calling any provider.

## Pattern and entities

This is a small multi-step process. Preflight the manifests and environment, reserve spend for one attempt, make the request, then save the response and record the outcome. Each pilot run owns at most one attempt per selected model ID. The prompt and model IDs come from the manifests. A provider-generated response ID and reported model version are provenance, while referral and citation counts are observations attached to an attempt. The database catalog is untouched. Realtime updates, high-volume reads and writes, large blobs, and proximity do not drive this feature.

## Access patterns

| ID | Operation | Key | Frequency |
|---|---|---|---|
| P1 | Load prompt and eligible panel | Prompt ID and model ID | Once per invocation, at most 12 model records |
| P2 | Read and reserve pilot spend | Provider and attempt ID | Before each live call |
| P3 | Save provider response and outcome | Run ID and model ID | Once per attempted model |

## Decision log

1. Use one explicit prompt ID and the same search instruction for every model. Require structured search evidence in the response. A successful HTTP status or links in answer text alone cannot establish that the provider searched.
2. Run sequentially with automatic retries off. A timeout may still have been billed. Record unresolved spend and reconcile it before another run. Parallel calls would make the small per-provider budget harder to control.
3. Write the provider response before declaring success. Keep the request body, usage, and provenance in local pilot storage. Keep credentials out of records and logs. Persist a reservation before dispatch and allow one writer so restarting cannot silently spend the same allowance twice.
4. Use direct synchronous SDK calls and a plain runner. Cap tool calls where supported and make estimates conservative. A provider controls actual token and tool billing. An application-side estimate can stop further requests but cannot guarantee a hard billing limit.

## Definition of done

Dry run prints the selected IDs and verifies manifests without credentials. Missing credentials, unwritable storage, or insufficient reserve block live dispatch. A fixture covers an accepted response with no search and a timeout with unresolved billing. During the live pilot, each attempt ends with a recorded outcome. Review actual usage, search evidence, and manual referral and citation counts before choosing the study panel and sample size.
