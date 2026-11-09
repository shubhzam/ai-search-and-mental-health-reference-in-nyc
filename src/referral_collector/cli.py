"""Local commands for the collector."""

import argparse
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

from .broker import check_broker, smoke_broker
from .database import check_database
from .pilot import run_pilot
from .seed_preview import preview_jobs
from .settings import Settings


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
    seed = commands.add_parser("seed", help="Preview the matched study schedule")
    seed.add_argument("--dry-run", action="store_true", required=True)
    seed.add_argument("--start", type=date.fromisoformat, required=True, metavar="YYYY-MM-DD")
    seed.add_argument("--days", type=int, default=4)
    seed.add_argument("--prompt-count", type=int, default=48)
    seed.add_argument("--prompts", type=Path, default=Path("prompts.csv"))
    seed.add_argument("--models", type=Path, default=Path("models.yaml"))
    pilot = commands.add_parser("pilot", help="Preview or run the live-search pilot")
    pilot.add_argument("--prompt-id", required=True)
    pilot.add_argument("--model", action="append", default=[], help="Select an exact model ID")
    pilot.add_argument("--live", action="store_true", help="Make billable provider requests")
    args = parser.parse_args()

    if args.command == "pilot":
        try:
            return run_pilot(args.prompt_id, args.model, args.live)
        except (ValueError, OSError, KeyError, CSVError, YAMLError) as error:
            print(f"Pilot failed: {error}", file=sys.stderr)
            return 1

    if args.command == "seed":
        try:
            jobs = preview_jobs(args.prompts, args.models, args.start, args.days, args.prompt_count)
        except (ValueError, OSError, OverflowError, CSVError, YAMLError) as error:
            print(f"Seed dry run failed: {error}", file=sys.stderr)
            return 1
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
