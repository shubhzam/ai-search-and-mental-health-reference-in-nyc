BEGIN;

CREATE TABLE executions (
    execution_id text PRIMARY KEY,
    scope text NOT NULL CHECK (scope IN ('pilot', 'collection')),
    prompt_id text NOT NULL,
    requested_model text NOT NULL,
    provider text NOT NULL CHECK (provider IN ('anthropic', 'openai', 'gemini')),
    planned_date date,
    outcome text NOT NULL DEFAULT 'pending'
        CHECK (outcome IN ('pending', 'passed', 'unresolved', 'incomplete', 'rejected'))
);

CREATE TABLE attempts (
    source_path text PRIMARY KEY,
    execution_id text NOT NULL REFERENCES executions (execution_id),
    batch_id text NOT NULL,
    attempt_key text NOT NULL,
    retry_of text,
    status text NOT NULL CHECK (status IN
        ('reserved', 'unresolved', 'passed', 'incomplete', 'no_search', 'rejected')),
    started_at timestamptz,
    finished_at timestamptz,
    returned_model text,
    response_id text,
    usage jsonb,
    estimated_usd numeric CHECK (estimated_usd >= 0),
    reserved_usd numeric NOT NULL CHECK (reserved_usd >= 0),
    output_token_limit integer CHECK (output_token_limit > 0),
    accounting_note text,
    ledger_sha256 text,
    raw_path text,
    raw_sha256 text,
    metadata jsonb NOT NULL,
    response jsonb,
    CHECK (raw_sha256 IS NULL OR raw_path IS NOT NULL),
    CHECK (response IS NULL OR raw_sha256 IS NOT NULL),
    CHECK (status <> 'passed' OR response IS NOT NULL),
    UNIQUE (execution_id, attempt_key)
);

COMMIT;
