"""Local commands for the collector."""

import argparse
import json
import os
import sys
from collections import Counter
from csv import Error as CSVError
from datetime import date
from pathlib import Path
from tempfile import NamedTemporaryFile

from pika.exceptions import AMQPError
from psycopg import Error as DatabaseError
from pydantic import ValidationError
from pydantic_settings import SettingsError
from yaml import YAMLError

from .batch import (
    BATCH_ID, GEMINI4_DAILY_MODELS, GEMINI4_MODELS, build_carbon_plan,
    build_gemini4_daily_plan, build_gemini4_plan, build_plan, run_batch, validate_plan,
)
from .broker import check_broker, smoke_broker
from .database import check_database
from .live import recover
from .persistence import import_attempts, inventory, inventory_report, read_object
from .pilot import run_pilot
from .seed import store_job_definitions
from .seed_preview import preview_jobs
from .settings import Settings
from .storage import _save, collection_lock


def check_storage(storage_dir: Path) -> None:
    """Verify that a file can be created, written, and removed."""
    with NamedTemporaryFile(dir=storage_dir, prefix=".referral-health-") as probe:
        probe.write(b"health check\n")
        probe.flush()


def main() -> int:
    parser = argparse.ArgumentParser(description="LLM Referral Collector")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("health", help="Check local infrastructure")
    commands.add_parser("smoke", help="Test RabbitMQ delivery")
    seed = commands.add_parser("seed", help="Preview or store the matched study schedule")
    seed_mode = seed.add_mutually_exclusive_group(required=True)
    seed_mode.add_argument("--dry-run", action="store_true")
    seed_mode.add_argument("--apply", action="store_true", help="Commit job definitions to PostgreSQL")
    seed.add_argument("--start", type=date.fromisoformat, required=True, metavar="YYYY-MM-DD")
    seed.add_argument("--days", type=int, default=4)
    seed.add_argument("--prompt-count", type=int, default=48)
    seed.add_argument("--prompts", type=Path, default=Path("prompts.csv"))
    seed.add_argument("--models", type=Path, default=Path("models.yaml"))
    pilot = commands.add_parser("pilot", help="Preview or run the live-search pilot")
    pilot.add_argument("--prompt-id", required=True)
    pilot.add_argument("--model", action="append", default=[], help="Select an exact model ID")
    pilot.add_argument("--live", action="store_true", help="Make billable provider requests")
    batch = commands.add_parser("batch", help="Preview or run a reviewed manual collection batch")
    batch_input = batch.add_mutually_exclusive_group(required=True)
    batch_input.add_argument("--planned-date", type=date.fromisoformat)
    batch_input.add_argument("--plan", type=Path)
    batch_input.add_argument("--carbon-pilot", action="store_true", help="Use the reviewed twelve-question Carbon pilot")
    batch_input.add_argument("--gemini4-model", choices=sorted(GEMINI4_MODELS), help="Use the reviewed 24-question Carbon comparison")
    batch_input.add_argument("--gemini4-daily-model", choices=sorted(GEMINI4_DAILY_MODELS), help="Use the separate twelve-question daily Gemini cohort")
    batch.add_argument("--prompt-count", type=int, default=10)
    batch.add_argument("--gemini4-daily-review", type=Path, help="Use a separately saved dated daily manifest")
    batch.add_argument("--prompt-id", action="append", default=[], help="Select explicit supplemental prompts")
    batch.add_argument("--gemini-output-tokens", type=int, choices=(2200, 8192), default=2200)
    batch.add_argument("--write-plan", type=Path, help="Save the reviewed preview as a new plan file")
    batch.add_argument("--batch-id", required=True)
    batch.add_argument("--live", action="store_true", help="Make billable provider requests")
    importer = commands.add_parser("import-collection", help="Validate and import historical attempts")
    import_mode = importer.add_mutually_exclusive_group(required=True)
    import_mode.add_argument("--dry-run", action="store_true")
    import_mode.add_argument("--apply", action="store_true")
    importer.add_argument("--data-dir", type=Path)
    commands.add_parser("recover-collection", help="Persist interrupted attempts from saved raw bytes")
    args = parser.parse_args()

    if args.command in {"pilot", "batch", "import-collection", "recover-collection"}:
        try:
            if args.command == "pilot":
                return run_pilot(args.prompt_id, args.model, args.live)
            if args.command == "batch":
                if not BATCH_ID.fullmatch(args.batch_id):
                    raise ValueError("Batch ID must use lowercase letters, digits and hyphens")
                if args.plan and (args.prompt_id or args.gemini_output_tokens != 2200):
                    raise ValueError("When loading a plan, select prompts and token limits in the plan file")
                if args.live and args.write_plan:
                    raise ValueError("Use --write-plan in preview mode")
                if args.live and args.prompt_id:
                    raise ValueError("Save and review a supplemental plan first, then use --plan with --live")
                if args.gemini4_daily_review and not args.gemini4_daily_model:
                    raise ValueError("Select --gemini4-daily-model when choosing its review")
                daily_options = {"review_path": args.gemini4_daily_review} if args.gemini4_daily_review else {}
                plan = (build_gemini4_daily_plan(args.gemini4_daily_model, **daily_options) if args.gemini4_daily_model else
                        build_gemini4_plan(args.gemini4_model) if args.gemini4_model else
                        build_carbon_plan() if args.carbon_pilot else
                        read_object(args.plan.read_bytes()) if args.plan
                        else build_plan(args.planned_date, args.prompt_count, args.prompt_id,
                                        args.gemini_output_tokens))
                if args.live:
                    return run_batch(plan, Path(args.batch_id))
                for entry in validate_plan(plan):
                    print(entry["execution_key"])
                if args.write_plan:
                    _save(args.write_plan, (json.dumps(plan, indent=2) + "\n").encode(), immutable=True)
                return 0
            if args.command == "import-collection" and args.dry_run:
                data = args.data_dir or Path(os.environ.get("REFERRAL_STORAGE_DIR", "data"))
                with collection_lock(data):
                    print(json.dumps(inventory_report(inventory(data)), indent=2))
                return 0
            settings = Settings()
            data = getattr(args, "data_dir", None) or settings.storage_dir
            with collection_lock(data):
                if args.command == "recover-collection":
                    report = recover(settings.database_url, data)
                    print(json.dumps(report, indent=2))
                    return int(bool(report["missing_raw"] or report["unresolved"]))
                attempts = inventory(data)
                if not attempts:
                    raise ValueError(f"No historical attempts found in {data}")
                report = inventory_report(attempts)
                report.update(import_attempts(settings.database_url, attempts))
                print(json.dumps(report, indent=2))
                return 0
        except (DatabaseError, SettingsError, ValidationError) as error:
            print(f"{args.command} stopped: {type(error).__name__}", file=sys.stderr)
            return 1
        except (ValueError, OSError, KeyError, TypeError, AttributeError, CSVError, YAMLError) as error:
            print(f"{args.command} stopped: {error}", file=sys.stderr)
            return 1

    if args.command == "seed":
        try:
            jobs = preview_jobs(args.prompts, args.models, args.start, args.days, args.prompt_count)
        except (ValueError, OSError, OverflowError, CSVError, YAMLError) as error:
            print(f"Seed validation failed: {error}", file=sys.stderr)
            return 1
        if args.apply:
            try:
                settings = Settings()
                inserted, unchanged = store_job_definitions(settings.database_url, jobs)
            except (DatabaseError, SettingsError, ValidationError, OSError) as error:
                # Connection and configuration errors may contain credentials.
                print(f"Seed apply failed: {type(error).__name__}", file=sys.stderr)
                return 1
            except ValueError as error:
                print(f"Seed apply failed: {error}", file=sys.stderr)
                return 1
            print(f"inserted={inserted} unchanged={unchanged}")
            return 0
        counts = Counter(job.task_id.removesuffix("_search") for job in jobs)
        print("run_date\tprompt_id\tmodel_id\ttask_id")
        for job in jobs:
            print(f"{job.run_from}\t{job.prompt_id}\t{job.model_id}\t{job.task_id}")
        for provider, count in sorted(counts.items()):
            print(f"{provider}: {count} jobs")
        print(f"Total: {len(jobs)} jobs (dry run)")
        return 0

    try:
        settings = Settings()
    except ValidationError as error:
        print(error, file=sys.stderr)
        return 1
    except (SettingsError, OSError) as error:
        print(f"Settings: FAILED ({type(error).__name__})", file=sys.stderr)
        return 1

    broker_errors = (AMQPError, OSError, ValueError)
    if args.command == "smoke":
        checks = (
            ("RabbitMQ smoke", smoke_broker, settings.rabbitmq_url, (*broker_errors, RuntimeError)),
        )
    else:
        checks = (
            ("PostgreSQL", check_database, settings.database_url, (DatabaseError, RuntimeError)),
            ("RabbitMQ", check_broker, settings.rabbitmq_url, broker_errors),
            ("Storage", check_storage, settings.storage_dir, (OSError,)),
        )
    exit_code = 0
    for name, check, value, expected_errors in checks:
        try:
            check(value)
        except expected_errors as error:
            print(f"{name}: FAILED ({type(error).__name__})", file=sys.stderr)
            exit_code = 1
        else:
            print(f"{name}: OK")
    return exit_code
