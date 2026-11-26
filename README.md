# AI Search and Mental Health Referrals in NYC

This study compares the referrals and sources that Gemini, Claude, and GPT-4o return for matched New York City mental health prompts with live search enabled. The study plan pairs 48 prompts with three model snapshots for 144 scheduled responses. The [collection results](docs/collection-results.md) record completed runs, actual collection times, and differences in request settings.

## Architecture whiteboard · planned system

The design starts with a job catalog, expands it into dated executions, and gives each provider its own queue and workers. Follow the arrows from the study inputs down to the analysis tables.

```mermaid
---
config:
  look: handDrawn
  handDrawnSeed: 42
  theme: base
  themeVariables:
    fontFamily: 'Comic Sans MS, Trebuchet MS, sans-serif'
    fontSize: 15px
    lineColor: '#64748b'
    textColor: '#1e293b'
    edgeLabelBackground: '#f8fafc'
  flowchart:
    curve: basis
    nodeSpacing: 28
    rankSpacing: 38
---
flowchart TB
    SPEC["Study inputs<br/>prompts.csv + model manifests"] --> SEED["Seed CLI"]
    SEED -->|"1 · Store job definitions"| PG[("PostgreSQL<br/>Jobs + dated executions")]
    PG -->|"2 · Expand and find due work"| WATCH["APScheduler watcher<br/>Ticks every 5 minutes"]

    subgraph BROKER["RabbitMQ · provider queues"]
        QA(["Anthropic queue"])
        QO(["OpenAI queue"])
        QG(["Gemini queue"])
    end
    WATCH -->|"3 · Publish"| QA
    WATCH --> QO
    WATCH --> QG

    subgraph WORKERS["Python · independent worker pools"]
        WA["Claude workers"]
        WO["OpenAI workers"]
        WG["Gemini workers"]
    end
    QA --> WA
    QO --> WO
    QG --> WG

    WA <-.-> CLAUDE(("Claude API"))
    WO <-.-> OPENAI(("OpenAI API"))
    WG <-.-> GEMINI(("Gemini API"))

    WORKERS -->|"4 · Save raw JSON"| RAW[("Raw responses<br/>Host-visible volume")]

    PG -.-> CHECK["Coverage + spend check"]
    RAW -->|"5 · Nightly export"| PARQUET[("Parquet tables")]
    PARQUET --> DUCK["DuckDB analysis"]

    classDef input fill:#fff1c2,stroke:#b7791f,color:#422006,stroke-width:2px
    classDef service fill:#dbeafe,stroke:#3b66a1,color:#172554,stroke-width:2px
    classDef queue fill:#ffedd5,stroke:#c26d24,color:#431407,stroke-width:2px
    classDef worker fill:#dcfce7,stroke:#32835a,color:#052e16,stroke-width:2px
    classDef api fill:#f3e8ff,stroke:#8857a6,color:#3b0764,stroke-width:2px
    classDef store fill:#ccfbf1,stroke:#277b75,color:#042f2e,stroke-width:2px
    class SPEC input
    class SEED,WATCH,CHECK,DUCK service
    class QA,QO,QG queue
    class WA,WO,WG worker
    class CLAUDE,OPENAI,GEMINI api
    class PG,RAW,PARQUET store
    style BROKER fill:#fff7ed,stroke:#c26d24,stroke-dasharray:5 4,color:#431407
    style WORKERS fill:#f0fdf4,stroke:#32835a,stroke-dasharray:5 4,color:#052e16
```

**Read the shapes.** Rectangles are services, capsules are queues, cylinders are stores, and circles are external APIs. Dotted arrows show live-search calls and the daily check.

1. **Schedule.** The watcher expands active job definitions into dated executions and publishes due work. A unique key made from the date and run key lets the watcher repeat the expansion without creating duplicate execution rows.
2. **Collect.** Each provider has its own queue and worker pool so it can manage its own rate limits. A worker checks the stored execution, reserves provider budget, and calls the configured search API.
3. **Persist.** The worker saves the raw response first, commits the execution outcome and file reference, then acknowledges the queue message. A redelivered message can check the committed outcome or recover from an existing file. If a provider may have processed a request before the worker could save it, its charge remains uncertain and needs reconciliation before retrying.
4. **Analyze.** The daily check compares expected and completed executions and tracks spend. The nightly export derives `responses`, `search_results`, and `citations` Parquet tables from the raw files. DuckDB joins those tables to the prompt metadata for comparisons by borough, payment condition, and need.

### Worker completion order

```mermaid
---
config:
  look: handDrawn
  handDrawnSeed: 42
  theme: base
  themeVariables:
    fontFamily: 'Comic Sans MS, Trebuchet MS, sans-serif'
    lineColor: '#64748b'
    textColor: '#1e293b'
---
flowchart LR
    FILE[("1 · Save raw JSON")] --> ROW[("2 · Commit outcome in Postgres")]
    ROW --> ACK(["3 · Acknowledge RabbitMQ message"])
    classDef store fill:#ccfbf1,stroke:#277b75,color:#042f2e,stroke-width:2px
    classDef queue fill:#ffedd5,stroke:#c26d24,color:#431407,stroke-width:2px
    class FILE,ROW store
    class ACK queue
```

The watcher, queue workers, and export are planned. The manual collector uses PostgreSQL execution and attempt tables. The [design walkthrough](docs/referral-collector-design.html) covers scheduling, failure recovery, and the data model in more detail.

## Manual collection and PostgreSQL storage

Pilot and batch commands reserve spend in PostgreSQL before every provider request. The collector syncs the raw HTTP bytes to host-visible storage, then commits the attempt status, response or error JSON, SHA-256, timing, usage, and estimated charge. An execution groups the original attempt with any explicit retries. The manual commands call providers directly. RabbitMQ is available for the planned scheduler.

| Location | What it stores |
|---|---|
| PostgreSQL `job_definitions` | The 144 original scheduled assignments |
| PostgreSQL `executions` and `attempts` | Pilot and collection history, including supplemental executions, request and response JSON, timestamps and spend |
| `data/collection/` and `data/pilot/` | Historical raw bytes and ledgers, with collection plans |
| `data/live/` | New raw bytes, capture receipts and batch plans |

As of November 26, PostgreSQL holds **652 complete collection responses** across 200 distinct prompts, with 659 collection attempts and 17 pilot attempts. The original panel has 168 fully matched prompts. Carbon, Neon, Hydrogen and Argon each have 24 complete responses on the same comparison prompts. All 676 raw files passed the database/checksum audit. See [the collection summary](docs/collection-results.md), [Carbon results](docs/gemini-carbon-pilot/04-results.md) and [Gemini 4 comparison results](docs/gemini4-comparison/04-results.md).

### Start services and import history

Run from the repository root with Python 3.13. Keep provider keys in the ignored `.env` and preserve the ignored `data/` directory.

```sh
uv sync --locked --python 3.13
docker compose up -d --wait postgres rabbitmq
uv run --locked --python 3.13 referral-collector health
docker compose exec -T postgres psql -X -v ON_ERROR_STOP=1 -U collector -d collector -c '\dt' -c 'SELECT count(*) FROM job_definitions'
docker compose exec -T postgres psql -X -v ON_ERROR_STOP=1 -U collector -d collector < migrations/002_collection_persistence.sql
uv run --locked --python 3.13 referral-collector import-collection --dry-run
uv run --locked --python 3.13 referral-collector import-collection --apply
uv run --locked --python 3.13 referral-collector import-collection --apply
```

Apply migration 002 once to the existing collector database. An identical second import reports `inserted=0 unchanged=271` for the November 18 snapshot. A changed or missing imported source aborts the import. Restore the original files or explicitly reconcile the historical record before proceeding.

### Launch future runs

```sh
# Preview a pilot, then add --live when ready for billable requests.
uv run --locked --python 3.13 referral-collector pilot --prompt-id anc-03 --model gpt-4o-2024-08-06

# Preview the original schedule. Existing attempts cannot be dispatched again.
uv run --locked --python 3.13 referral-collector batch --planned-date 2026-11-10 --prompt-count 1 --batch-id scheduled-preview

# Example supplemental plan. Supply the planned date and reviewed, unused prompt IDs.
uv run --locked --python 3.13 referral-collector batch --planned-date 2026-11-18 \
  --prompt-id g-001 --gemini-output-tokens 8192 --batch-id supplemental-preview \
  --write-plan data/supplemental-preview.json

# Run a reviewed plan containing new attempts.
uv run --locked --python 3.13 referral-collector batch --plan data/new-batch-plan.json --batch-id new-batch --live

# Recover saved responses after a persistence interruption.
uv run --locked --python 3.13 referral-collector recover-collection
```

Use a stable batch ID when resuming a live batch. A saved historical plan can be copied and trimmed to unattempted entries. For a deliberate retry, keep the original planned date and request identity, set `retry_of` to the original execution key, and give the attempt key a new `__retry-N` suffix. Save it as a new plan and use a new batch ID. The runner accepts an explicit retry for a failed original with cleared reservations. The eligible model windows come from the reviewed manifest.

With Docker, the same files appear at `/data`. Match the container user to the host owner of the private response directories.

```sh
COLLECTOR_UID="$(id -u)" COLLECTOR_GID="$(id -g)" docker compose run --rm --build collector \
  batch --plan /data/new-batch-plan.json --batch-id new-batch --live
```

If the database fails before dispatch, the command stops. If it fails after capture, run `recover-collection` after restoring connectivity. A pending attempt without saved bytes keeps its reservation and requires provider-side reconciliation. The collector uses a shared $9 operating limit and a $0.50 per-attempt reservation within the $10 project cap per provider. The budget includes pilots, provisional charges, retries and supplemental work. Usage-based estimates can differ from provider invoices.

### Inspect the saved responses

```sql
SELECT e.prompt_id, e.provider, e.planned_date, a.finished_at, a.response
FROM executions e JOIN attempts a USING (execution_id)
WHERE e.scope = 'collection' AND a.status = 'passed'
ORDER BY e.prompt_id, e.provider;

SELECT e.execution_id, a.attempt_key, a.retry_of, a.status, a.started_at,
       a.finished_at, a.estimated_usd, a.reserved_usd, a.accounting_note,
       a.raw_path, a.raw_sha256
FROM executions e JOIN attempts a USING (execution_id)
WHERE e.execution_id = '2026-11-11__g-290__gemini-3.8-flash'
ORDER BY a.started_at;
```

Run the fake-provider tests with a database user that can create disposable schemas.

```sh
REFERRAL_TEST_DATABASE_URL=postgresql://collector:local-dev@localhost:5432/collector \
  uv run --locked --python 3.13 python -m unittest discover -s tests -v
```

See [the import and recovery design](docs/collection-db-import/04-automatic-persistence-and-recovery.md).
