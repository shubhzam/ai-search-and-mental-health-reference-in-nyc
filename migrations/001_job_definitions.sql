BEGIN;

CREATE TABLE job_definitions (
    arm text NOT NULL CHECK (arm IN ('pilot', 'burst', 'daily')),
    prompt_id text NOT NULL CHECK (btrim(prompt_id) <> ''),
    model_id text NOT NULL CHECK (btrim(model_id) <> ''),
    task_id text NOT NULL CHECK (
        task_id IN ('anthropic_search', 'openai_search', 'gemini_search')
    ),
    schedule_type text NOT NULL CHECK (schedule_type IN ('DAILY', 'DATE')),
    run_from date NOT NULL,
    run_until date NOT NULL,
    search_enabled boolean NOT NULL CHECK (search_enabled),
    PRIMARY KEY (arm, prompt_id, model_id, run_from),
    CHECK (run_from <= run_until),
    CHECK (schedule_type <> 'DATE' OR run_from = run_until)
);

COMMIT;
