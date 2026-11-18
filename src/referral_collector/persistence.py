"""Validate saved attempts and persist an auditable execution history."""

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .pilot_providers import SDK_NAMES, observe

WRITE_LOCK = 749806512
STATUSES = {"reserved", "unresolved", "passed", "incomplete", "no_search", "rejected"}
RESERVATION = Decimal("0.50")
OPERATING_LIMIT = Decimal("9.00")
ALLOWANCE = {"gemini": Decimal("0.01")}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def path_in(data: Path, relative: str) -> Path:
    path = data / relative
    if Path(relative).is_absolute() or ".." in Path(relative).parts or not path.resolve().is_relative_to(data.resolve()):
        raise ValueError(f"Path escapes data directory: {relative}")
    return path


def read_object(content: bytes) -> dict:
    def invalid(token):
        raise ValueError(f"Invalid JSON constant: {token}")

    value = json.loads(content, parse_constant=invalid)
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    return value


def amount(value) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError("Invalid spend amount")
    result = Decimal(str(value))
    if not result.is_finite() or result < 0:
        raise ValueError("Invalid spend amount")
    return result


def timestamp(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        raise ValueError("Timestamp requires an explicit offset")
    return parsed


def token_limit(request: dict) -> int | None:
    value = request.get("max_tokens", request.get("max_output_tokens", request.get("config", {}).get("max_output_tokens")))
    if value is not None and (type(value) is not int or value <= 0):
        raise ValueError("Invalid output token limit")
    return value


def jsonb(value):
    return Jsonb(value) if value is not None else None


@dataclass(frozen=True)
class Attempt:
    scope: str
    batch: str
    source: str
    record: dict
    ledger_hash: str | None = None
    raw_path: str | None = None
    raw_hash: str | None = None
    response: dict | None = None

    @property
    def attempt_key(self):
        return self.record.get("execution_key") or self.execution_id

    @property
    def execution_id(self):
        if self.scope == "pilot":
            return f"pilot/{self.batch}/{self.record['prompt_id']}/{self.record['requested_model']}"
        return self.record.get("retry_of") or self.record["execution_key"]

    @property
    def identity(self):
        planned = self.record.get("planned_date")
        return (
            self.scope, self.record["prompt_id"], self.record["requested_model"],
            self.record["provider"], date.fromisoformat(planned) if planned else None,
        )

    def values(self):
        r = self.record
        started = timestamp(r.get("started_at") or r.get("timestamp"))
        finished = timestamp(r.get("finished_at"))
        if started and finished and finished < started:
            raise ValueError(f"Finish precedes start: {self.source}")
        request = r["request"]
        if (r["provider"] not in SDK_NAMES or r["status"] not in STATUSES
                or request["model"] != r["requested_model"] or not r["prompt_id"]):
            raise ValueError(f"Invalid attempt identity: {self.source}")
        estimated = amount(r["estimated_usd"]) if r.get("estimated_usd") is not None else None
        if r["status"] in {"passed", "incomplete", "no_search"} and estimated is None:
            raise ValueError(f"Missing estimated cost: {self.source}")
        usage = r.get("usage")
        if usage is not None and not isinstance(usage, dict):
            raise ValueError(f"Invalid usage: {self.source}")
        return (
            r["status"], started, finished, r.get("returned_model"), r.get("response_id"),
            jsonb(usage), estimated, amount(r["reserved_usd"]), token_limit(request),
            r.get("accounting_note"), self.ledger_hash, self.raw_path, self.raw_hash,
            Jsonb(r), jsonb(self.response),
        )


def inventory(data: Path) -> list[Attempt]:
    results = []
    plans = {}
    for scope, pattern in (("pilot", "*/*.attempt.json"), ("collection", "*/*/attempt.json")):
        for path in sorted((data / scope).glob(pattern)):
            relative = path.relative_to(data).as_posix()
            try:
                content = path_in(data, relative).read_bytes()
                record = read_object(content)
                ledger_hash = digest(content)
                if scope == "collection":
                    batch = path.parent.parent.name
                    if record["execution_key"] != path.parent.name:
                        raise ValueError("Execution key differs from ledger path")
                    if batch not in plans:
                        plan = path_in(data, f"collection/{batch}/plan.json").read_bytes()
                        entries = read_object(plan)["executions"]
                        by_key = {entry["execution_key"]: entry for entry in entries}
                        if len(by_key) != len(entries):
                            raise ValueError("Duplicate plan executions")
                        plans[batch] = digest(plan), by_key
                    plan_hash, entries = plans[batch]
                    entry = entries[record["execution_key"]]
                    if any(record.get(key) != value for key, value in entry.items()):
                        raise ValueError("Ledger request differs from saved plan")
                    record = dict(record, plan_sha256=plan_hash)
                    raw = path.with_name("response.json")
                else:
                    batch = path.parent.name
                    raw = path.with_name(path.name.removesuffix(".attempt.json") + ".response.json")
                raw_name = raw.relative_to(data).as_posix()
                raw = path_in(data, raw_name)
                raw_hash = response = None
                if raw.exists():
                    raw_content = raw.read_bytes()
                    raw_hash = digest(raw_content)
                    response = read_object(raw_content)
                elif record["status"] in {"passed", "incomplete", "no_search"} or record.get("raw_sha256"):
                    raise ValueError("Required raw response is missing")
                if record.get("raw_sha256", raw_hash) != raw_hash:
                    raise ValueError("Saved response checksum mismatch")
                if record["status"] == "passed":
                    evidence = observe(record["provider"], record["requested_model"], response)
                    if not evidence.complete or not evidence.search_observed:
                        raise ValueError("Missing completion or search evidence")
                attempt = Attempt(scope, batch, f"data/{relative}", record, ledger_hash,
                                  f"data/{raw_name}" if raw_hash else None, raw_hash, response)
                attempt.values()
                results.append(attempt)
            except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
                raise ValueError(f"{relative}: {error}") from error
    originals = {a.execution_id: a for a in results if not a.record.get("retry_of")}
    seen = set()
    for attempt in results:
        identity = attempt.execution_id, attempt.attempt_key
        if identity in seen:
            raise ValueError(f"Duplicate attempt identity: {attempt.source}")
        seen.add(identity)
        if attempt.record.get("retry_of"):
            original = originals.get(attempt.execution_id)
            if not original or original.identity != attempt.identity or attempt.attempt_key == attempt.execution_id:
                raise ValueError(f"Invalid retry link: {attempt.source}")
    return results


def inventory_report(attempts: list[Attempt]) -> dict:
    report = {}
    for scope in ("collection", "pilot"):
        rows = [a for a in attempts if a.scope == scope]
        passed = [a for a in rows if a.record["status"] == "passed"]
        report[scope] = {
            "attempts": len(rows), "executions": len({a.execution_id for a in rows}),
            "statuses": dict(Counter(a.record["status"] for a in rows)),
            "passed_by_provider": dict(Counter(a.record["provider"] for a in passed)),
            "distinct_passed_prompts": len({a.record["prompt_id"] for a in passed}),
            "matched_prompts": sum(
                providers == set(SDK_NAMES)
                for providers in _prompt_providers(passed).values()
            ),
            "no_raw": [a.source for a in rows if a.raw_hash is None],
            "missing_start": sum(not (a.record.get("started_at") or a.record.get("timestamp")) for a in rows),
            "missing_finish": sum(not a.record.get("finished_at") for a in rows),
        }
    return report


def _prompt_providers(attempts):
    prompts = {}
    for a in attempts:
        prompts.setdefault(a.record["prompt_id"], set()).add(a.record["provider"])
    return prompts


def connect(url):
    conn = psycopg.connect(str(url), connect_timeout=5, row_factory=dict_row)
    conn.isolation_level = psycopg.IsolationLevel.READ_COMMITTED
    return conn


def lock_writes(conn):
    conn.execute("SET LOCAL lock_timeout = '5s'")
    conn.execute("SELECT pg_advisory_xact_lock(%s)", (WRITE_LOCK,))


def ensure_execution(conn, attempt: Attempt):
    conn.execute("""
        INSERT INTO executions (execution_id, scope, prompt_id, requested_model, provider, planned_date)
        VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (execution_id) DO NOTHING
        """, (attempt.execution_id, *attempt.identity))
    row = conn.execute("""
        SELECT scope, prompt_id, requested_model, provider, planned_date
        FROM executions WHERE execution_id = %s
        """, (attempt.execution_id,)).fetchone()
    if tuple(row.values()) != attempt.identity:
        raise ValueError(f"Execution identity changed: {attempt.execution_id}; reconcile explicitly")


def insert_attempt(conn, attempt: Attempt):
    conn.execute("""
        INSERT INTO attempts (
            source_path, execution_id, batch_id, attempt_key, retry_of,
            status, started_at, finished_at, returned_model, response_id, usage,
            estimated_usd, reserved_usd, output_token_limit, accounting_note,
            ledger_sha256, raw_path, raw_sha256, metadata, response
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (attempt.source, attempt.execution_id, attempt.batch, attempt.attempt_key,
              attempt.record.get("retry_of"), *attempt.values()))


def update_outcome(conn, execution_id: str):
    conn.execute("""
        UPDATE executions SET outcome = (
            SELECT CASE
                WHEN bool_or(status = 'passed') THEN 'passed'
                WHEN bool_or(status = 'unresolved') THEN 'unresolved'
                WHEN bool_or(status IN ('incomplete', 'no_search')) THEN 'incomplete'
                WHEN bool_or(status = 'rejected') THEN 'rejected'
                ELSE 'pending'
            END FROM attempts WHERE execution_id = %s
        ) WHERE execution_id = %s
        """, (execution_id, execution_id))


def import_attempts(url, attempts: list[Attempt]) -> dict:
    inserted = 0
    with connect(url) as conn:
        lock_writes(conn)
        existing = {
            row["source_path"]: row for row in conn.execute("""
                SELECT source_path, ledger_sha256, raw_sha256, metadata->>'plan_sha256' AS plan_sha256
                FROM attempts WHERE ledger_sha256 IS NOT NULL
                """)
        }
        incoming = {a.source for a in attempts}
        missing = existing.keys() - incoming
        if missing:
            raise ValueError(f"Missing previously imported source: {min(missing)}; reconcile explicitly")
        affected = set()
        new_attempts = []
        for a in attempts:
            if (row := existing.get(a.source)) is not None:
                if (row["ledger_sha256"], row["raw_sha256"], row["plan_sha256"]) != (
                    a.ledger_hash, a.raw_hash, a.record.get("plan_sha256")
                ):
                    raise ValueError(f"Source changed: {a.source}; reconcile explicitly")
            else:
                new_attempts.append(a)
        for a in new_attempts:
            ensure_execution(conn, a)
            insert_attempt(conn, a)
            affected.add(a.execution_id)
            inserted += 1
        for execution_id in affected:
            update_outcome(conn, execution_id)
    return {"inserted": inserted, "unchanged": len(attempts) - inserted}
