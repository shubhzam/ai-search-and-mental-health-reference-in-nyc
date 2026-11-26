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

CARBON_REVIEW = Path("docs/gemini-carbon-pilot/review-manifest.json")
GEMINI4_REVIEW = Path("docs/gemini4-comparison/review-manifest.json")
GEMINI4_MODELS = {"gemini-4-neon", "gemini-4-hydrogen", "gemini-4-argon"}
GEMINI4_DAILY_REVIEW = Path("docs/gemini4-daily/review-manifest.json")
GEMINI4_DAILY_MODELS = GEMINI4_MODELS | {"gemini-4-carbon"}


def build_gemini4_daily_plan(model_id: str) -> dict:
    """Build a separate twelve-question daily cohort without changing prior plans."""
    if model_id not in GEMINI4_DAILY_MODELS:
        raise ValueError("Unsupported Gemini 4 daily model")
    review = read_object(GEMINI4_DAILY_REVIEW.read_bytes())
    today = datetime.now(ZoneInfo("America/New_York")).date()
    plan = build_plan(today, 1, review["prompt_ids"], gemini_limit=8192)
    entries = []
    for entry in plan["executions"]:
        if entry["provider"] != "gemini":
            continue
        entry.update(requested_model=model_id,
                     execution_key=f"{today}__{entry['prompt_id']}__{model_id}",
                     active_from=review["active_from"], active_until=review["active_until"])
        entry["request"]["model"] = model_id
        entries.append(entry)
    plan.update(executions=entries, cohort="gemini4-daily",
                comparison_manifest_sha256=digest(GEMINI4_DAILY_REVIEW.read_bytes()),
                timing_deviation="Daily Gemini cohort uses recorded actual collection times")
    return plan


def build_gemini4_plan(model_id: str) -> dict:
    """Match one approved model to the fixed 24-question Carbon baseline."""
    if model_id not in GEMINI4_MODELS:
        raise ValueError("Unsupported Gemini 4 comparison model")
    review = read_object(GEMINI4_REVIEW.read_bytes())
    prompt_ids = review["prompt_ids"]
    first = build_plan(date(2026, 11, 10), 1, prompt_ids[:12], gemini_limit=8192)
    second = build_plan(date(2026, 11, 10), 1, prompt_ids[12:], gemini_limit=8192)
    today = datetime.now(ZoneInfo("America/New_York")).date().isoformat()
    entries = []
    for entry in first["executions"] + second["executions"]:
        if entry["provider"] != "gemini":
            continue
        entry.update(requested_model=model_id, planned_date=today,
                     execution_key=f"{today}__{entry['prompt_id']}__{model_id}",
                     active_from=review["active_from"], active_until=review["active_until"])
        entry["request"]["model"] = model_id
        entries.append(entry)
    first.update(executions=entries, cohort="gemini4-comparison",
                 comparison_manifest_sha256=digest(GEMINI4_REVIEW.read_bytes()),
                 timing_deviation="Additional model collected later than Carbon baseline")
    return first


def build_carbon_plan() -> dict:
    """Build only the approved twelve-question Carbon comparison."""
    review = read_object(CARBON_REVIEW.read_bytes())
    today = datetime.now(ZoneInfo("America/New_York")).date()
    plan = build_plan(date(2026, 11, 10), 1, review["prompt_ids"], gemini_limit=8192)
    entries = []
    for entry in plan["executions"]:
        if entry["provider"] != "gemini":
            continue
        entry["requested_model"] = "gemini-4-carbon"
        entry["planned_date"] = today.isoformat()
        entry["execution_key"] = f"{today}__{entry['prompt_id']}__gemini-4-carbon"
        entry["active_from"] = "2026-11-24"
        entry["active_until"] = "2026-11-30"
        entry["request"]["model"] = "gemini-4-carbon"
        entries.append(entry)
    plan.update(executions=entries, cohort="gemini-carbon-pilot",
                pilot_manifest_sha256=digest(CARBON_REVIEW.read_bytes()),
                timing_deviation="Carbon pilot collected later than its Flash baselines")
    return plan


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
    panel = PANEL
    carbon = plan.get("cohort") == "gemini-carbon-pilot"
    comparison = plan.get("cohort") == "gemini4-comparison"
    daily = plan.get("cohort") == "gemini4-daily"
    timeout_ms = plan.get("transport_timeout_ms", 90_000)
    if type(timeout_ms) is not int or timeout_ms not in ((90_000, 180_000) if daily else (90_000,)):
        raise ValueError("Unsupported transport timeout for this cohort")
    if comparison or daily:
        manifest_path = GEMINI4_DAILY_REVIEW if daily else GEMINI4_REVIEW
        approved_models = GEMINI4_DAILY_MODELS if daily else GEMINI4_MODELS
        expected_count = 12 if daily else 24
        manifest = read_object(manifest_path.read_bytes())
        model_ids = {e["requested_model"] for e in executions}
        ordered = manifest["prompt_ids"]
        selected = [e["prompt_id"] for e in executions]
        expected = [p for p in ordered if p in selected] if plan.get("continuation") else ordered
        if (plan.get("comparison_manifest_sha256") != digest(manifest_path.read_bytes())
                or manifest["source_prompt_sha256"] != digest(Path("prompts.csv").read_bytes())
                or set(manifest["models"]) != approved_models
                or len(ordered) != expected_count or len(set(ordered)) != expected_count
                or len(model_ids) != 1 or not model_ids <= approved_models
                or selected != expected):
            raise ValueError("Gemini 4 comparison differs from its reviewed manifest")
        for baseline in manifest["baseline_responses"]:
            if digest(Path(baseline["raw_path"]).read_bytes()) != baseline["raw_sha256"]:
                raise ValueError("Gemini 4 baseline checksum mismatch")
        model_id = next(iter(model_ids))
        panel = {"gemini": model_id}
        model_dates = {model_id: (manifest["active_from"], manifest["active_until"])}
    if carbon:
        manifest = read_object(CARBON_REVIEW.read_bytes())
        if (plan.get("pilot_manifest_sha256") != digest(CARBON_REVIEW.read_bytes())
                or manifest["source_prompt_sha256"] != digest(Path("prompts.csv").read_bytes())
                or not 1 <= len(manifest["prompt_ids"]) <= 12
                or len(set(manifest["prompt_ids"])) != len(manifest["prompt_ids"])
                or len(executions) != len(manifest["prompt_ids"])
                or [e["prompt_id"] for e in executions] != manifest["prompt_ids"]):
            raise ValueError("Carbon pilot differs from its reviewed manifest")
        for baseline in manifest["baseline_responses"]:
            if digest(Path(baseline["raw_path"]).read_bytes()) != baseline["raw_sha256"]:
                raise ValueError("Carbon baseline checksum mismatch")
        panel = {"gemini": "gemini-4-carbon"}
        model_dates = {"gemini-4-carbon": ("2026-11-24", "2026-11-30")}
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
                or (entry["active_from"], entry["active_until"]) != model_dates.get(model)
                or panel.get(provider) != model):
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
            if (carbon or comparison or daily) and requested_limit != 8192:
                raise ValueError("Gemini 4 comparison requires 8192 output tokens")
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
            if "transport_timeout_ms" in plan:
                record["transport_timeout_ms"] = plan["transport_timeout_ms"]
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
