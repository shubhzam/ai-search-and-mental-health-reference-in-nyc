"""Run one budgeted live-search pilot attempt per eligible model."""

import csv
import os
from datetime import datetime
from importlib.metadata import version
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import yaml
from dotenv import dotenv_values

from .live import dispatch, now
from .persistence import RESERVATION, Attempt, import_attempts, inventory
from .pilot_providers import RATES, SDK_NAMES, request_options
from .seed_preview import ModelManifest, StudyModel
from .settings import Settings
from .storage import collection_lock


KEY_NAMES = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
}
SEARCH_INSTRUCTION = "Search the live web for current options and cite your sources."


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


def provider_keys(providers) -> dict:
    local = dotenv_values(".env", interpolate=False)
    keys = {}
    for provider in providers:
        name = KEY_NAMES[provider]
        value = (os.environ.get(name, local.get(name)) or "").strip()
        if not value:
            raise ValueError(f"Missing {name}")
        keys[provider] = value
    return keys


def run_pilot(prompt_id: str, model_ids: list[str], live: bool) -> int:
    prompt, models = _plan(prompt_id, model_ids)
    if not live:
        print(f"Pilot preview · {prompt_id} · $9 operating limit per provider")
        print(prompt)
        for model in models:
            print(f"{model.provider} / {model.model_id}")
        return 0

    settings = Settings()
    data, url = settings.storage_dir, settings.database_url
    keys = provider_keys({model.provider for model in models})
    run_id = uuid4().hex
    with collection_lock(data):
        import_attempts(url, inventory(data))
        for model in models:
            location = f"data/live/pilot/{run_id}/{model.model_id}"
            record = {
                "provider": model.provider, "requested_model": model.model_id, "prompt_id": prompt_id,
                "reserved_at": now(), "status": "reserved", "reserved_usd": float(RESERVATION),
                "sdk_version": version(SDK_NAMES[model.provider]),
                "request": request_options(model.provider, model.model_id, prompt),
            }
            attempt = Attempt("pilot", run_id, f"{location}/attempt.json", record,
                              raw_path=f"{location}/response.json")
            status = dispatch(url, data, attempt, keys[model.provider])
            print(f"{model.model_id}: {status}", flush=True)
            if status not in {"passed", "skipped"}:
                return 1
    return 0
