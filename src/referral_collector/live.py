"""Reserve spend, capture provider bytes, then settle the PostgreSQL attempt."""

from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path

from .persistence import (
    ALLOWANCE, OPERATING_LIMIT, RESERVATION, Attempt, connect, digest, ensure_execution,
    insert_attempt, lock_writes, path_in, read_object, update_outcome,
)
from .pilot_providers import observe, request_search
from .storage import _save, _save_record, ensure_directory

REJECTED_HTTP = {400, 401, 403, 404, 429}


class ResponseWriteError(OSError):
    """The response could not be durably captured."""


def now() -> str:
    return datetime.now(UTC).isoformat()


def reserve(url, attempt: Attempt, *, eligible: bool = True, raw_exists: bool = False) -> bool:
    """Reserve once. Return False if this exact request already has an attempt."""
    provider = attempt.record["provider"]
    with connect(url) as conn:
        lock_writes(conn)
        existing = conn.execute("""
            SELECT execution_id, metadata FROM attempts WHERE source_path = %s
            """, (attempt.source,)).fetchone()
        if existing:
            saved = existing["metadata"]
            if existing["execution_id"] != attempt.execution_id or any(
                saved.get(k) != attempt.record.get(k)
                for k in ("request", "plan_sha256", "execution_key", "retry_of")
            ):
                raise ValueError(f"Saved request differs: {attempt.source}")
            return False
        if conn.execute("SELECT 1 FROM attempts WHERE status = 'reserved' LIMIT 1").fetchone():
            raise ValueError("A pending reservation requires recover-collection before further dispatch")
        current = conn.execute("""
            SELECT e.outcome, CASE WHEN e.provider = %s THEN true ELSE false END AS same_provider
            FROM executions e WHERE e.execution_id = %s
            """, (provider, attempt.execution_id)).fetchone()
        retry = attempt.record.get("retry_of")
        if retry:
            if (not current or not current["same_provider"]
                    or current["outcome"] not in {"rejected", "incomplete"}
                    or attempt.attempt_key == retry):
                raise ValueError(f"Retry requires a failed original execution: {retry}")
        elif current:
            raise ValueError(f"Execution already attempted: {attempt.execution_id}")
        if attempt.scope == "pilot" and conn.execute("""
            SELECT 1 FROM executions WHERE requested_model = %s LIMIT 1
            """, (attempt.record["requested_model"],)).fetchone():
            return False
        if not eligible:
            raise ValueError("Model is outside its approved eligibility window")
        if raw_exists:
            raise ValueError(f"Raw response exists without a reservation: {attempt.raw_path}")
        totals = conn.execute("""
            SELECT coalesce(sum(coalesce(a.estimated_usd, 0) + a.reserved_usd), 0) AS spent,
                   coalesce(bool_or(a.reserved_usd > 0 OR a.status = 'unresolved'), false) AS uncertain
            FROM attempts a JOIN executions e USING (execution_id)
            WHERE e.provider = %s
            """, (provider,)).fetchone()
        if totals["uncertain"]:
            raise ValueError(f"{provider}: unresolved spend blocks dispatch")
        if totals["spent"] + ALLOWANCE.get(provider, 0) + RESERVATION > OPERATING_LIMIT:
            raise ValueError(f"{provider}: operating budget blocks dispatch")
        ensure_execution(conn, attempt)
        insert_attempt(conn, attempt)
        update_outcome(conn, attempt.execution_id)
    return True


def raw_file(data: Path, raw_path: str) -> Path:
    if not raw_path.startswith("data/live/"):
        raise ValueError(f"Invalid live raw path: {raw_path}")
    return path_in(data, raw_path.removeprefix("data/"))


def terminal_attempt(data: Path, attempt: Attempt, transport_error=None, started_at=None) -> Attempt | None:
    raw = raw_file(data, attempt.raw_path)
    receipt_path = raw.with_name("receipt.json")
    receipt = read_object(receipt_path.read_bytes()) if receipt_path.is_file() else {}
    record = dict(attempt.record)
    response = raw_hash = None
    if raw.is_file():
        raw_content = raw.read_bytes()
        raw_hash = digest(raw_content)
        if receipt and receipt["raw_sha256"] != raw_hash:
            raise ValueError(f"Raw response checksum mismatch: {attempt.raw_path}")
        try:
            response = read_object(raw_content)
        except ValueError:
            record["accounting_note"] = "Raw HTTP body could not be parsed. Reservation retained."
    elif transport_error is None:
        return None
    status_code = receipt.get("http_status")
    if transport_error is not None:
        record["error_type"] = type(transport_error).__name__
        if status_code is None:
            status_code = getattr(transport_error, "status_code", None) or getattr(transport_error, "code", None)
    if type(status_code) is int:
        record["http_status"] = status_code
    record["started_at"] = receipt.get("started_at") or started_at
    record["finished_at"] = receipt.get("finished_at") if raw_hash else now()
    record["status"] = "unresolved"
    if status_code in REJECTED_HTTP:
        record.update(status="rejected", reserved_usd=0)
    elif response and (status_code is None or 200 <= status_code < 300) and "error" not in response:
        try:
            observation = observe(record["provider"], record["requested_model"], response)
            if record["provider"] == "gemini" and "candidatesTokenCount" not in observation.usage:
                raise ValueError("Gemini output usage missing")
        except (KeyError, TypeError, ValueError, AttributeError):
            record["accounting_note"] = "Provider usage could not be verified. Reservation retained."
        else:
            record.update(asdict(observation), reserved_usd=0)
            if not observation.search_observed:
                record["status"] = "no_search"
            else:
                record["status"] = "passed" if observation.complete else "incomplete"
    return replace(attempt, record=record, raw_hash=raw_hash, response=response)


def settle(url, attempt: Attempt) -> None:
    with connect(url) as conn:
        lock_writes(conn)
        result = conn.execute("""
            UPDATE attempts SET (status, started_at, finished_at, returned_model, response_id,
                                 usage, estimated_usd, reserved_usd, output_token_limit, accounting_note,
                                 ledger_sha256, raw_path, raw_sha256, metadata, response) =
                                (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            WHERE source_path = %s AND status = 'reserved'
            """, (*attempt.values(), attempt.source))
        if result.rowcount != 1:
            raise ValueError(f"Expected an outstanding reservation: {attempt.source}")
        update_outcome(conn, attempt.execution_id)


def dispatch(url, data: Path, attempt: Attempt, key: str, *, eligible: bool = True) -> str:
    """A storage or database exception ends this run with its reservation intact."""
    raw = raw_file(data, attempt.raw_path)
    ensure_directory(raw.parent)
    if not reserve(url, attempt, eligible=eligible, raw_exists=raw.exists()):
        return resume_attempt(url, data, attempt.source) or "skipped"

    capture_error = None

    def capture(body: bytes, http_status: int | None = None):
        nonlocal capture_error
        try:
            received = now()
            _save(raw, body, immutable=True)
            _save_record(raw.with_name("receipt.json"), {
                "http_status": http_status, "started_at": started_at, "finished_at": received,
                "raw_sha256": digest(body),
            })
        except OSError as error:
            capture_error = ResponseWriteError(f"Could not capture {attempt.raw_path}")
            raise capture_error from error

    transport_error = None
    started_at = now()
    try:
        request_search(attempt.record["provider"], key, attempt.record["request"], capture)
    except ResponseWriteError:
        raise
    except Exception as error:
        transport_error = error
    if capture_error is not None:
        raise capture_error
    terminal = terminal_attempt(data, attempt, transport_error, started_at)
    if terminal is None:
        raise ValueError(f"No response was captured: {attempt.source}")
    settle(url, terminal)
    return terminal.record["status"]


def _from_row(row) -> Attempt:
    return Attempt(row["scope"], row["batch_id"], row["source_path"], row["metadata"],
                   raw_path=row["raw_path"])


def resume_attempt(url, data: Path, source: str) -> str | None:
    with connect(url) as conn:
        row = conn.execute("""
            SELECT e.scope, a.* FROM attempts a JOIN executions e USING (execution_id)
            WHERE a.source_path = %s
            """, (source,)).fetchone()
    if row is None:
        return None
    if row["status"] == "reserved":
        attempt = terminal_attempt(data, _from_row(row))
        if attempt is None:
            raise ValueError(f"No saved bytes for {source}; reservation requires reconciliation")
        settle(url, attempt)
        return attempt.record["status"]
    if row["raw_sha256"]:
        raw = raw_file(data, row["raw_path"])
        if not raw.is_file() or digest(raw.read_bytes()) != row["raw_sha256"]:
            raise ValueError(f"Raw response missing or altered: {row['raw_path']}")
    return row["status"]


def recover(url, data: Path) -> dict:
    with connect(url) as conn:
        pending = list(conn.execute("""
            SELECT e.scope, a.* FROM attempts a JOIN executions e USING (execution_id)
            WHERE a.status = 'reserved' AND a.ledger_sha256 IS NULL ORDER BY a.source_path
            """))
        unresolved = [row["source_path"] for row in conn.execute("""
            SELECT source_path FROM attempts
            WHERE status = 'unresolved' AND ledger_sha256 IS NULL ORDER BY source_path
            """)]
    report = {"recovered": {}, "missing_raw": [], "unresolved": unresolved}
    for row in pending:
        terminal = terminal_attempt(data, _from_row(row))
        if terminal is None:
            report["missing_raw"].append(row["source_path"])
        else:
            settle(url, terminal)
            report["recovered"][terminal.source] = terminal.record["status"]
            if terminal.record["status"] == "unresolved":
                report["unresolved"].append(terminal.source)
    return report
