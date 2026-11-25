# Gemini Carbon pilot · Worked dataflow

Read review-manifest.json and verify the prompts.csv hash and twelve existing Flash baseline hashes. Resolve the first selected prompt's text from prompts.csv. Build a gemini-4-carbon request with the same shared instruction and an 8,192-token cap. The model's name distinguishes its execution key from the Flash baseline.

The batch command reserves one attempt in PostgreSQL, then dispatches a synchronous generateContent request with google_search. Capture the raw HTTP bytes under data/live/collection/gemini-carbon-pilot-20261124/<execution_key>/response.json and persist the receipt with actual UTC timestamps. Validate returned model, visible text, STOP, grounding queries and web sources, and token usage. Commit the response JSON, raw hash, usage, and terminal attempt outcome in PostgreSQL.

For the first response, compare the local raw checksum with its committed database row before progressing to the remaining eleven questions. Final verification checks twelve Carbon outcomes and the exact twelve baseline prompt IDs. Carbon's answers retain their later collection timestamps for downstream analysis.

Failure example: PostgreSQL disconnects after response capture. The raw file and receipt survive, and the reservation remains recorded. Stop dispatch, restore the database connection, and invoke existing recover-collection to settle the captured response without another paid call. A timeout without captured bytes remains unresolved and needs billing reconciliation. An incomplete answer retains its saved response and ends the pilot for review.
