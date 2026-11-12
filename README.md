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

The watcher, execution tables, queue workers, and export are planned. The [design walkthrough](docs/referral-collector-design.html) covers scheduling, failure recovery, and the data model in more detail.

## What runs today · manual collection

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
    edgeLabelBackground: '#f8fafc'
  flowchart:
    curve: basis
---
flowchart TB
    SPEC["Reviewed study inputs"] --> SEED["Seed CLI"]
    SEED --> PG[("PostgreSQL<br/>144 planned jobs")]
    SPEC --> BATCH["Manual batch runner"]
    BATCH <-.->|"Live search"| API(("Provider APIs"))
    BATCH --> FILES[("Local data/<br/>Raw JSON + UTC attempt records")]
    FILES --> REPORT["Verified results summary"]

    classDef input fill:#fff1c2,stroke:#b7791f,color:#422006,stroke-width:2px
    classDef service fill:#dbeafe,stroke:#3b66a1,color:#172554,stroke-width:2px
    classDef api fill:#f3e8ff,stroke:#8857a6,color:#3b0764,stroke-width:2px
    classDef store fill:#ccfbf1,stroke:#277b75,color:#042f2e,stroke-width:2px
    class SPEC input
    class SEED,BATCH,REPORT service
    class API api
    class PG,FILES store
```

PostgreSQL holds the planned prompt, model, and date assignments. The manual batches use the reviewed assignments and call providers directly. Docker Compose provides PostgreSQL and RabbitMQ locally, and the current batches run independently of RabbitMQ.

| Location | What it stores |
|---|---|
| PostgreSQL `job_definitions` | 144 scheduled job definitions |
| `data/collection/<batch>/<execution>/` | `response.json` with the raw provider response and `attempt.json` with the request, planned date, UTC start and finish times, usage, outcome, and estimated cost |
| `data/collection/<batch>/` | The batch plan and status summary |
| `data/pilot/` | Earlier pilot requests, responses, and usage records |
| [`docs/collection-results.md`](docs/collection-results.md) | Verified progress and budget summary published to GitHub |

The `data/` directory and `.env` are ignored by Git. The collector counts pilot and study attempts against a $9 operating limit within the $10 cap per provider. An uncertain charge stays accounted for until it can be reconciled.
