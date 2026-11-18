"""Plan and run bounded manual collection using PostgreSQL reservations."""

import csv
import json
import re
from datetime import date, datetime
from importlib.metadata import version
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from .live import dispatch, now
from .persistence import RESERVATION, Attempt, digest, import_attempts, inventory, path_in, read_object
from .pilot import SEARCH_INSTRUCTION, provider_keys
from .pilot_providers import SDK_NAMES, request_options
from .seed_preview import ModelManifest, preview_jobs
from .settings import Settings
from .storage import _save, collection_lock, ensure_directory

SUFFIX = "Give up to four relevant options. Keep each to two sentences, note any cost or eligibility you can verify, and cite your sources."
PANEL = {
    "anthropic": "claude-sonnet-4-5-20250929",
    "openai": "gpt-4o-2024-08-06",
    "gemini": "gemini-3.8-flash",
}
EXECUTION_KEY = re.compile(r"[A-Za-z0-9_.-]{1,180}")
BATCH_ID = re.compile(r"[a-z0-9-]{1,80}")
ENTRY_FIELDS = {
    "execution_key", "prompt_id", "requested_model", "provider",
    "planned_date", "active_from", "active_until", "request",
}


def build_plan(planned_date: date, count: int, prompt_ids=(), gemini_limit: int = 2200) -> dict:
    if prompt_ids and (len(prompt_ids) > 12 or len(set(prompt_ids)) != len(prompt_ids)):
        raise ValueError("Select at most 12 distinct supplemental prompts")
    if not prompt_ids and not 1 <= count <= 10:
        raise ValueError('This bounded batch supports 1–10 matched prompts')
    review = Path('docs/three-model-study')
    summary = json.loads((review / 'review-summary.json').read_text())
    for name, expected_hash in summary['input_sha256'].items():
        if digest(Path(name).read_bytes()) != expected_hash:
            raise ValueError('Reviewed input hash mismatch')
    models = ModelManifest.model_validate(yaml.safe_load((review / 'models.yaml').read_text())).models
    if {m.provider: m.model_id for m in models} != PANEL or len(models) != 3:
        raise ValueError('Unexpected study panel')
    selected = prompt_ids
    if not selected:
        jobs = preview_jobs(Path('prompts.csv'), review / 'models.yaml', date.fromisoformat(summary['start']), 4, 48)
        selected = list(dict.fromkeys(j.prompt_id for j in jobs if j.run_from == planned_date))[:count]
        if len(selected) != count:
            raise ValueError('Not enough approved prompts on planned date')
    with Path('prompts.csv').open(encoding='utf-8-sig', newline='') as f:
        prompts = {r['prompt_id']: r['prompt_text'] for r in csv.DictReader(f)}
    executions = []
    for prompt_id in selected:
        for m in models:
            prompt = f'{prompts[prompt_id]}\n\n{SEARCH_INSTRUCTION}\n\n{SUFFIX}'
            options = request_options(m.provider, m.model_id, prompt)
            if m.provider == 'gemini':
                options['config']['max_output_tokens'] = gemini_limit
            else:
                options['max_tokens' if m.provider == 'anthropic' else 'max_output_tokens'] = 2200
            executions.append(dict(execution_key=f'{planned_date}__{prompt_id}__{m.model_id}',
                prompt_id=prompt_id, requested_model=m.model_id, provider=m.provider,
                planned_date=str(planned_date), active_from=str(m.active_from), active_until=str(m.active_until), request=options))
    return dict(schema_version=1, timing_deviation='Night collection authorized; actual timestamps recorded separately',
                input_sha256=summary['input_sha256'], executions=executions)


def validate_plan(plan: dict) -> list[dict]:
    if plan["schema_version"] != 1:
        raise ValueError("Unsupported plan schema")
    executions = plan["executions"]
    if not isinstance(executions, list) or not 1 <= len(executions) <= 36:
        raise ValueError("A plan must have 1–36 attempts")
    review = Path("docs/three-model-study")
    reviewed = read_object((review / "review-summary.json").read_bytes())
    if plan["input_sha256"] != reviewed["input_sha256"]:
        raise ValueError("Plan input hashes differ from the reviewed study")
    for name, expected in reviewed["input_sha256"].items():
        if digest(Path(name).read_bytes()) != expected:
            raise ValueError(f"Reviewed input hash mismatch: {name}")
    models = ModelManifest.model_validate(yaml.safe_load((review / "models.yaml").read_text())).models
    model_dates = {m.model_id: (str(m.active_from), str(m.active_until)) for m in models}
    with Path("prompts.csv").open(encoding="utf-8-sig", newline="") as source:
        prompts = {r["prompt_id"]: r["prompt_text"] for r in csv.DictReader(source)}
    keys = set()
    for entry in executions:
        if set(entry) - {"retry_of"} != ENTRY_FIELDS:
            raise ValueError("Unexpected plan entry fields")
        provider = entry["provider"]
        model = entry["requested_model"]
        prompt = entry["prompt_id"]
        planned = date.fromisoformat(entry["planned_date"]).isoformat()
        original = f"{planned}__{prompt}__{model}"
        attempt_key = entry["execution_key"]
        retry = entry.get("retry_of")
        if (not EXECUTION_KEY.fullmatch(attempt_key) or attempt_key in keys
                or (entry["active_from"], entry["active_until"]) != model_dates[model]
                or PANEL[provider] != model):
            raise ValueError("Invalid or duplicate execution identity")
        if retry:
            if retry != original or not re.fullmatch(re.escape(original) + r"__retry-[1-9][0-9]*", attempt_key):
                raise ValueError("Invalid retry key")
        elif attempt_key != original:
            raise ValueError("Invalid execution key")
        keys.add(attempt_key)
        options = request_options(provider, model, f"{prompts[prompt]}\n\n{SEARCH_INSTRUCTION}\n\n{SUFFIX}")
        if provider == "gemini":
            requested_limit = entry["request"]["config"]["max_output_tokens"]
            if requested_limit not in (2200, 8192):
                raise ValueError("Unsupported Gemini token limit")
            options["config"]["max_output_tokens"] = requested_limit
        else:
            options["max_tokens" if provider == "anthropic" else "max_output_tokens"] = 2200
        if options != entry["request"]:
            raise ValueError(f"Request differs from study settings: {attempt_key}")
    return executions


def run_batch(plan: dict, batch_dir: Path, data: Path | None = None, keys=None, *, url=None) -> int:
    """Run a reviewed batch. The supplied directory contributes its batch ID."""
    batch_id = batch_dir.name
    if not BATCH_ID.fullmatch(batch_id):
        raise ValueError("Batch ID must use lowercase letters, digits and hyphens")
    executions = validate_plan(plan)
    if url is None or data is None:
        settings = Settings()
        url = settings.database_url if url is None else url
        data = settings.storage_dir if data is None else data
    if keys is None:
        keys = provider_keys({entry["provider"] for entry in executions})
    with collection_lock(data):
        import_attempts(url, inventory(data))
        directory = path_in(data, f"live/collection/{batch_id}")
        ensure_directory(directory)
        plan_path = directory / "plan.json"
        if plan_path.exists():
            plan_bytes = plan_path.read_bytes()
            if read_object(plan_bytes) != plan:
                raise ValueError("Batch plan differs from its saved copy")
        else:
            plan_bytes = (json.dumps(plan, indent=2) + "\n").encode()
            _save(plan_path, plan_bytes, immutable=True)
        plan_hash = digest(plan_bytes)
        for entry in executions:
            provider = entry["provider"]
            location = f"data/live/collection/{batch_id}/{entry['execution_key']}"
            record = dict(entry, reserved_at=now(), status="reserved", reserved_usd=float(RESERVATION),
                          sdk_version=version(SDK_NAMES[provider]), plan_sha256=plan_hash)
            attempt = Attempt("collection", batch_id, f"{location}/attempt.json", record,
                              raw_path=f"{location}/response.json")
            today = datetime.now(ZoneInfo("America/New_York")).date().isoformat()
            # Eligibility is checked only for new dispatches. Existing attempts can be recovered later.
            eligible = entry["active_from"] <= today <= entry["active_until"]
            status = dispatch(url, data, attempt, keys[provider], eligible=eligible)
            print(f"{entry['execution_key']}: {status}", flush=True)
            if status != "passed":
                return 1
    return 0


if __name__ == "__main__":
    import sys

    from .cli import main

    sys.argv.insert(1, "batch")
    raise SystemExit(main())
