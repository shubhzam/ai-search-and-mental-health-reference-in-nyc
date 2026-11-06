"""Atomic persistence of validated job definitions."""

from collections.abc import Iterable
from dataclasses import astuple, dataclass
from datetime import date
from itertools import pairwise

import psycopg
from psycopg.rows import class_row
from pydantic import PostgresDsn


@dataclass(frozen=True)
class JobDefinition:
    arm: str
    prompt_id: str
    model_id: str
    task_id: str
    schedule_type: str
    run_from: date
    run_until: date
    search_enabled: bool

    @property
    def key(self) -> tuple[str, str, str, date]:
        return self.arm, self.prompt_id, self.model_id, self.run_from


def store_job_definitions(
    database_url: PostgresDsn, definitions: Iterable[JobDefinition]
) -> tuple[int, int]:
    """Commit a batch and return its inserted and unchanged counts."""
    candidates = {}
    for definition in definitions:
        if definition.key in candidates:
            raise ValueError(f"Duplicate job definition key: {definition.key}")
        candidates[definition.key] = definition

    with psycopg.connect(str(database_url), connect_timeout=5) as connection:
        connection.isolation_level = psycopg.IsolationLevel.READ_COMMITTED
        connection.execute("SET LOCAL lock_timeout = '5s'")
        connection.execute("LOCK TABLE job_definitions IN SHARE ROW EXCLUSIVE MODE")
        with connection.cursor(row_factory=class_row(JobDefinition)) as cursor:
            cursor.execute("""
                SELECT arm, prompt_id, model_id, task_id, schedule_type,
                       run_from, run_until, search_enabled
                FROM job_definitions
                """)
            existing = {definition.key: definition for definition in cursor}

        new = []
        for key, candidate in candidates.items():
            if key not in existing:
                new.append(candidate)
            elif existing[key] != candidate:
                raise ValueError(f"Stored job definition differs: {key}")

        ordered = sorted(
            [*existing.values(), *new],
            key=lambda job: (job.prompt_id, job.model_id, job.run_from),
        )
        for previous, current in pairwise(ordered):
            same_pair = (previous.prompt_id, previous.model_id) == (
                current.prompt_id, current.model_id
            )
            if same_pair and current.run_from <= previous.run_until:
                raise ValueError(f"Overlapping job definitions: {previous.key}, {current.key}")

        with connection.cursor() as cursor:
            cursor.executemany("""
                INSERT INTO job_definitions
                    (arm, prompt_id, model_id, task_id, schedule_type,
                     run_from, run_until, search_enabled)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, [astuple(definition) for definition in new])

    return len(new), len(candidates) - len(new)
