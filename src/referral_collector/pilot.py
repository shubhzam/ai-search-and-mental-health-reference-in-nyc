"""Run one budgeted, local search pilot attempt per study model."""

import csv
import fcntl
import json
import os
from dataclasses import asdict
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import uuid4
from zoneinfo import ZoneInfo

import yaml
from dotenv import dotenv_values

from .pilot_providers import RATES, SDK_NAMES, observe, request_options, request_search
from .seed_preview import ModelManifest, StudyModel


OPERATING_LIMIT_USD = 9
RESERVE_USD = 0.50
KEY_NAMES = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
}
SEARCH_INSTRUCTION = "Search the live web for current options and cite your sources."


class ResponseWriteError(OSError):
    """The provider responded but the response could not be preserved."""


def _save(path: Path, content: bytes, *, immutable: bool = False) -> None:
    with NamedTemporaryFile(dir=path.parent, delete=False) as target:
        temporary = Path(target.name)
        try:
            target.write(content)
            target.flush()
            os.fsync(target.fileno())
            if immutable:
                # A hard link fails if a response already exists at the final path.
                os.link(temporary, path)
            else:
                temporary.replace(path)
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            temporary.unlink(missing_ok=True)


def _save_record(path: Path, record: dict) -> None:
    _save(path, (json.dumps(record, indent=2) + "\n").encode())


def _records(root: Path) -> list[dict]:
    return [json.loads(path.read_bytes()) for path in root.glob("*/*.attempt.json")]


def _plan(prompt_id: str, model_ids: list[str]) -> tuple[str, list[StudyModel]]:
    with Path("prompts.csv").open(encoding="utf-8-sig", newline="") as source:
        prompts = [
            row["prompt_text"] for row in csv.DictReader(source, strict=True)
            if row["prompt_id"] == prompt_id
        ]
    if len(prompts) != 1 or not prompts[0].strip():
        raise ValueError(f"Expected one nonempty prompt for {prompt_id!r}")

    models = ModelManifest.model_validate(yaml.safe_load(Path("models.yaml").read_text())).models
    by_id = {model.model_id: model for model in models}
    if len(by_id) != len(models):
        raise ValueError("Duplicate model IDs")
    today = datetime.now(ZoneInfo("America/New_York")).date()
    if model_ids:
        if len(model_ids) != len(set(model_ids)):
            raise ValueError("Duplicate model filters")
        for model_id in model_ids:
            if model_id not in by_id:
                raise ValueError(f"Unknown model: {model_id}")
        models = [by_id[model_id] for model_id in model_ids]
    else:
        models = [model for model in models if model.active_from <= today <= model.active_until]
    if not models:
        raise ValueError("No eligible models selected")
    for model in models:
        if model.model_id not in RATES:
            raise ValueError(f"No pilot pricing configured for {model.model_id}")
        if not model.active_from <= today <= model.active_until:
            raise ValueError(f"Model {model.model_id} is ineligible on {today}")
    return f"{prompts[0]}\n\n{SEARCH_INSTRUCTION}", models


def _attempt(run_dir: Path, model: StudyModel, prompt_id: str, prompt: str, key: str) -> dict:
    options = request_options(model.provider, model.model_id, prompt)
    attempt_path = run_dir / f"{model.model_id}.attempt.json"
    response_path = run_dir / f"{model.model_id}.response.json"
    record = {
        "provider": model.provider,
        "requested_model": model.model_id,
        "prompt_id": prompt_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sdk_version": version(SDK_NAMES[model.provider]),
        "status": "reserved",
        "reserved_usd": RESERVE_USD,
        "request": options,
    }
    _save_record(attempt_path, record)

    def capture(body: bytes) -> None:
        try:
            _save(response_path, body, immutable=True)
        except OSError as error:
            raise ResponseWriteError("Could not preserve the pilot response") from error

    try:
        request_search(model.provider, key, options, capture)
    except ResponseWriteError:
        raise
    except Exception as error:
        status_code = getattr(error, "status_code", None) or getattr(error, "code", None)
        record["status"] = "rejected" if status_code in (400, 401, 403, 404, 429) else "unresolved"
        record["error_type"] = type(error).__name__
        if isinstance(status_code, int):
            record["http_status"] = status_code
    else:
        try:
            observation = observe(model.provider, model.model_id, json.loads(response_path.read_bytes()))
        except (KeyError, TypeError, ValueError, AttributeError) as error:
            record.update(status="unresolved", error_type=type(error).__name__)
        else:
            record.update(asdict(observation))
            if not observation.search_observed:
                record["status"] = "no_search"
            elif not observation.complete:
                record["status"] = "incomplete"
            else:
                record["status"] = "passed"

    if record["status"] not in {"unresolved", "reserved"}:
        record["reserved_usd"] = 0
    _save_record(attempt_path, record)
    return record


def run_pilot(prompt_id: str, model_ids: list[str], live: bool) -> int:
    prompt, models = _plan(prompt_id, model_ids)
    root = Path("data/pilot")
    if not live:
        print(f"Pilot preview · {prompt_id} · ${OPERATING_LIMIT_USD} operating limit per provider")
        print(prompt)
        attempted = {record["requested_model"] for record in _records(root)}
        for model in models:
            action = "already attempted" if model.model_id in attempted else "planned"
            print(f"{model.provider} / {model.model_id}: {action}")
        return 0

    local = dotenv_values(".env", interpolate=False)
    keys = {}
    for provider in {model.provider for model in models}:
        name = KEY_NAMES[provider]
        value = (os.environ.get(name, local.get(name)) or "").strip()
        if not value:
            raise ValueError(f"Missing {name}")
        keys[provider] = value

    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    failed = False
    with (root / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        records = _records(root)
        run_dir = root / uuid4().hex
        for model in models:
            if any(record["requested_model"] == model.model_id for record in records):
                print(f"{model.model_id}: skipped (already attempted)")
                continue
            provider_records = [record for record in records if record["provider"] == model.provider]
            spent = sum(
                record.get("estimated_usd", 0) + record["reserved_usd"] for record in provider_records
            )
            if any(record["reserved_usd"] for record in provider_records) or (
                spent + RESERVE_USD > OPERATING_LIMIT_USD
            ):
                print(f"{model.model_id}: blocked by unresolved spend or budget limit")
                failed = True
                continue
            run_dir.mkdir(mode=0o700, exist_ok=True)
            record = _attempt(run_dir, model, prompt_id, prompt, keys[model.provider])
            records.append(record)
            details = ""
            if "searches" in record:
                details = f" ({record['searches']} searches, ${record['estimated_usd']:.4f} est.)"
            elif "http_status" in record:
                details = f" (HTTP {record['http_status']})"
            print(f"{model.model_id}: {record['status']}{details}", flush=True)
            failed |= record["status"] != "passed"
        if run_dir.is_dir():
            print(f"Pilot records: {run_dir}")
    return int(failed)
