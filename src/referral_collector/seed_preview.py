"""Read the study manifests and preview a matched collection schedule."""

import csv
from collections import defaultdict
from datetime import date, timedelta
from itertools import islice, zip_longest
from pathlib import Path
from random import Random
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from .seed import JobDefinition


class StudyModel(BaseModel):
    model_id: str = Field(min_length=1)
    provider: Literal["anthropic", "openai", "gemini"]
    generation_rung: int = Field(ge=1)
    active_from: date
    active_until: date


class ModelManifest(BaseModel):
    models: list[StudyModel] = Field(min_length=1)


def _select_prompts(path: Path, count: int) -> list[str]:
    cells: dict[tuple[str, str], list[str]] = defaultdict(list)
    prompt_ids: set[str] = set()
    required = {"prompt_id", "borough", "payment_condition", "prompt_text"}
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source, strict=True)
        if not required.issubset(reader.fieldnames or ()):
            raise ValueError("Prompt CSV requires prompt_id, borough, payment_condition, and prompt_text")
        for row in reader:
            if None in row or any(not (row[field] or "").strip() for field in required):
                raise ValueError(f"Invalid prompt CSV row at line {reader.line_num}")
            prompt_id = row["prompt_id"].strip()
            if prompt_id in prompt_ids:
                raise ValueError(f"Duplicate prompt ID: {prompt_id}")
            prompt_ids.add(prompt_id)
            cells[row["borough"].strip(), row["payment_condition"].strip()].append(prompt_id)

    boroughs = sorted({borough for borough, _ in cells})
    payments = sorted({payment for _, payment in cells})
    rng = Random(20261109)
    groups = []
    for offset in range(len(boroughs)):
        for index, payment in enumerate(payments):
            borough = boroughs[(offset + index) % len(boroughs)]
            group = sorted(cells[borough, payment])
            if not group:
                raise ValueError(f"Missing prompts for {borough} / {payment}")
            rng.shuffle(group)
            groups.append(group)

    interleaved = (prompt for round_ in zip_longest(*groups) for prompt in round_ if prompt)
    selected = list(islice(interleaved, count))
    if len(selected) != count:
        raise ValueError(f"Requested {count} prompts, but the manifest contains only {len(selected)}")
    return selected


def preview_jobs(
    prompts_path: Path, models_path: Path, start: date, days: int, prompt_count: int
) -> list[JobDefinition]:
    """Assign each chosen prompt to one date and every model in the panel."""
    if not 1 <= days <= prompt_count <= 48:
        raise ValueError("Use 1 to 48 prompts and at least one prompt per collection day")
    end = start + timedelta(days=days - 1)
    models = ModelManifest.model_validate(
        yaml.safe_load(models_path.read_text(encoding="utf-8-sig"))
    ).models
    if len({model.model_id for model in models}) != len(models):
        raise ValueError("Duplicate model IDs")
    if len({(model.provider, model.generation_rung) for model in models}) != len(models):
        raise ValueError("Duplicate generation rungs for a provider")
    for model in models:
        if not model.model_id.strip() or model.model_id != model.model_id.strip():
            raise ValueError(f"Invalid model ID: {model.model_id!r}")
        if not model.active_from <= start <= end <= model.active_until:
            raise ValueError(f"Model {model.model_id!r} must be eligible for the entire collection window")

    selected = _select_prompts(prompts_path, prompt_count)
    models.sort(key=lambda model: (model.provider, model.generation_rung))
    jobs = []
    for index, prompt_id in enumerate(selected):
        run_date = start + timedelta(days=index * days // prompt_count)
        for model in models:
            jobs.append(JobDefinition(
                arm="daily",
                prompt_id=prompt_id,
                model_id=model.model_id,
                task_id=f"{model.provider}_search",
                schedule_type="DATE",
                run_from=run_date,
                run_until=run_date,
                search_enabled=True,
            ))
    return jobs
