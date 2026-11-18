# Collection database import · Worked dataflow

Read data/collection/afternoon-20261111/2026-11-11__g-290__gemini-3.8-flash/attempt.json and its adjacent response.json. This is an incomplete attempt. Its execution identity is 2026-11-11__g-290__gemini-3.8-flash. Preserve the provisional spend and accounting note.

Read the separate successful retry from data/collection/afternoon-20261111-gemini-retry/. Its retry_of value resolves to the same execution identity. Preserve its own source path, UTC timestamps, 8,192-token request setting, usage, response body and raw-file checksum.

The importer produces one executions row and two attempts rows. Both attempts retain their provider response JSON. The successful attempt gives the execution a passed outcome. This preserves the incomplete 2,200-token attempt for the audit and lets analysis select the successful response explicitly.

After full inventory validation, acquire the database import lock, compare existing attempt source hashes, insert missing rows, derive execution outcomes and commit. A second identical import inserts nothing. SQL queries can count successful collection attempts, distinct prompts and model coverage, while excluding pilot scope.

Failure trace: a saved response has changed since its recorded hash. Validation aborts before database writes and identifies the source file. Recover the preserved original bytes or explicitly reconcile the discrepancy before reimporting. The importer makes no replacement provider call.
