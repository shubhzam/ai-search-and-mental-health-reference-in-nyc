"""Exercise the paid-request CLI using fake provider responses only."""

import contextlib
import io
import json
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

from referral_collector import batch, live, pilot
from referral_collector.cli import main
from referral_collector.persistence import digest, import_attempts, inventory


def response():
    return json.dumps({
        "model": batch.PANEL["openai"], "id": "fixture-response", "status": "completed", "error": None,
        "usage": {"input_tokens": 100, "output_tokens": 100},
        "output": [{"type": "web_search_call", "status": "completed", "action": {"type": "search"}}],
    }).encode()


def invoke(*args):
    output = io.StringIO()
    with (patch("sys.argv", ["referral-collector", *args]),
          contextlib.redirect_stdout(output), contextlib.redirect_stderr(output)):
        code = main()
    return code, output.getvalue()


def fixture_plan():
    plan = batch.build_plan(date(2026, 11, 10), 1)
    plan["executions"] = [e for e in plan["executions"] if e["provider"] == "openai"]
    return plan


def save_history(data, plan, run="history", *, status="passed", body=None):
    plan_path = data / "collection" / run / "plan.json"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text(json.dumps(plan))
    entry = plan["executions"][0]
    path = plan_path.parent / entry["execution_key"] / "attempt.json"
    path.parent.mkdir()
    content = response() if body is None else body
    path.with_name("response.json").write_bytes(content)
    path.write_text(json.dumps(dict(
        entry, status=status, timestamp="2026-11-10T22:00:00+00:00",
        reserved_usd=0, estimated_usd=0.07, raw_sha256=digest(content),
    )))
    return path


class BatchTests(unittest.TestCase):
    def test_approved_request_settings(self):
        plan = batch.build_plan(date(2026, 11, 10), 10)
        self.assertEqual(len(batch.validate_plan(plan)), 30)
        for entry in plan["executions"]:
            options = entry["request"]
            if entry["provider"] == "gemini":
                self.assertEqual(options["config"]["max_output_tokens"], 2200)
                prompt = options["contents"]
            elif entry["provider"] == "anthropic":
                self.assertEqual(options["max_tokens"], 2200)
                prompt = options["messages"][0]["content"]
            else:
                self.assertEqual(options["max_output_tokens"], 2200)
                prompt = options["input"]
            self.assertTrue(prompt.endswith(batch.SUFFIX))
            self.assertIn(batch.SEARCH_INSTRUCTION, prompt)

    def test_cli_dry_run_and_raw_checksum(self):
        with tempfile.TemporaryDirectory() as root:
            data = Path(root)
            path = save_history(data, fixture_plan())
            code, output = invoke("import-collection", "--dry-run", "--data-dir", root)
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(output)["collection"]["attempts"], 1)
            path.with_name("response.json").write_bytes(b"{}")
            code, output = invoke("import-collection", "--dry-run", "--data-dir", root)
            self.assertEqual(code, 1)
            self.assertIn("checksum mismatch", output)

    def test_supplemental_plan_preview_and_write(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "supplemental.json"
            args = ("batch", "--planned-date", "2026-11-18", "--prompt-id", "g-003",
                    "--gemini-output-tokens", "8192", "--batch-id", "fixture", "--write-plan", str(path))
            with patch.object(live, "request_search") as request:
                self.assertEqual(invoke(*args)[0], 0)
                self.assertEqual(invoke(*args)[0], 1)
                self.assertEqual(invoke("batch", "--plan", str(path), "--batch-id", "fixture")[0], 0)
            request.assert_not_called()
            plan = json.loads(path.read_bytes())
            self.assertEqual(len(plan["executions"]), 3)
            gemini = next(e for e in plan["executions"] if e["provider"] == "gemini")
            self.assertEqual(gemini["request"]["config"]["max_output_tokens"], 8192)

    def test_database_failure_before_dispatch(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "fixture.json"
            path.write_text(json.dumps(fixture_plan()))
            settings = SimpleNamespace(storage_dir=Path(root),
                                       database_url="postgresql://fake:secret@127.0.0.1:1/missing")
            with (patch.object(batch, "Settings", return_value=settings),
                  patch.object(batch, "provider_keys", return_value={"openai": "fixture"}),
                  patch.object(live, "request_search") as request):
                code, output = invoke("batch", "--plan", str(path), "--batch-id", "test", "--live")
            self.assertEqual(code, 1)
            self.assertIn("OperationalError", output)
            self.assertNotIn("secret", output)
            request.assert_not_called()


@unittest.skipUnless(os.getenv("REFERRAL_TEST_DATABASE_URL"), "Requires disposable schema access")
class DatabaseCLITests(unittest.TestCase):
    def setUp(self):
        self.base = os.environ["REFERRAL_TEST_DATABASE_URL"]
        self.schema = "collection_test_" + uuid4().hex
        with psycopg.connect(self.base, autocommit=True) as connection:
            connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))
        self.addCleanup(self.drop_schema)
        self.dsn = make_conninfo(self.base, options=f"-csearch_path={self.schema}")
        with psycopg.connect(self.dsn, autocommit=True) as connection:
            connection.execute(Path("migrations/002_collection_persistence.sql").read_text())
        root = tempfile.TemporaryDirectory()
        self.addCleanup(root.cleanup)
        self.data = Path(root.name)
        self.plan = fixture_plan()
        self.plan_path = self.data / "fixture.json"
        self.plan_path.write_text(json.dumps(self.plan))
        settings = SimpleNamespace(storage_dir=self.data, database_url=self.dsn)
        for module in (batch, pilot, "referral_collector.cli"):
            patcher = (patch(f"{module}.Settings", return_value=settings) if isinstance(module, str)
                       else patch.object(module, "Settings", return_value=settings))
            patcher.start()
            self.addCleanup(patcher.stop)
        for module in (batch, pilot):
            patcher = patch.object(module, "provider_keys", return_value={"openai": "fixture"})
            patcher.start()
            self.addCleanup(patcher.stop)
        model = SimpleNamespace(provider="openai", model_id=batch.PANEL["openai"])
        patcher = patch.object(pilot, "_plan", return_value=("pilot fixture", [model]))
        patcher.start()
        self.addCleanup(patcher.stop)
        # Keep fixture eligibility independent of the day on which tests are run.
        patcher = patch.object(batch, "datetime", wraps=datetime)
        patcher.start().now.return_value = datetime(2026, 11, 18)
        self.addCleanup(patcher.stop)

    def drop_schema(self):
        with psycopg.connect(self.base, autocommit=True) as connection:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(self.schema)))

    def rows(self, query="SELECT status, reserved_usd, response FROM attempts ORDER BY source_path"):
        with psycopg.connect(self.dsn) as connection:
            return connection.execute(query).fetchall()

    def run_batch(self, batch_id="test"):
        return invoke("batch", "--plan", str(self.plan_path), "--batch-id", batch_id, "--live")

    def passed(self, provider, key, options, capture):
        self.assertEqual(self.rows("SELECT status, reserved_usd FROM attempts WHERE status = 'reserved'"),
                         [("reserved", 0.5)])
        capture(response(), 200)

    def test_batch_success_resume_and_cross_batch_duplicate(self):
        with patch.object(live, "request_search", side_effect=self.passed) as request:
            self.assertEqual(self.run_batch()[0], 0)
            self.assertEqual(self.run_batch()[0], 0)
            self.assertEqual(self.run_batch("different")[0], 1)
        request.assert_called_once()
        self.assertEqual(self.rows(), [("passed", 0, json.loads(response()))])

    def test_pilot_persists(self):
        with patch.object(live, "request_search", side_effect=self.passed) as request:
            self.assertEqual(invoke("pilot", "--prompt-id", "fixture", "--live")[0], 0)
            self.assertEqual(invoke("pilot", "--prompt-id", "fixture", "--live")[0], 0)
        request.assert_called_once()
        self.assertEqual(self.rows("SELECT scope, planned_date FROM executions"), [("pilot", None)])
        self.assertEqual(self.rows()[0][0], "passed")

    def test_raw_write_failure_holds_reservation_and_stops(self):
        save = live._save

        def fail_raw(path, *args, **kwargs):
            if path.name == "response.json":
                raise OSError("simulated write failure")
            return save(path, *args, **kwargs)

        with (patch.object(live, "_save", side_effect=fail_raw),
              patch.object(live, "request_search", side_effect=self.passed) as request):
            code, output = self.run_batch()
            self.assertEqual(code, 1)
            self.assertIn("Could not capture", output)
            self.assertEqual(invoke("recover-collection")[0], 1)
            self.assertEqual(self.run_batch()[0], 1)
        request.assert_called_once()
        self.assertEqual(self.rows(), [("reserved", 0.5, None)])

    def test_database_failure_after_response_recovers_without_redispatch(self):
        def disconnect(provider, key, options, capture):
            self.passed(provider, key, options, capture)

        with patch.object(live, "request_search", side_effect=disconnect) as request:
            with patch.object(live, "connect", side_effect=[
                live.connect(self.dsn), psycopg.OperationalError("connection lost"),
            ]):
                self.assertEqual(self.run_batch()[0], 1)
            self.assertEqual(self.rows(), [("reserved", 0.5, None)])
            raw, = self.data.glob("live/collection/*/*/response.json")
            self.assertEqual(raw.read_bytes(), response())
            code, output = invoke("recover-collection")
            self.assertEqual(code, 0)
            self.assertIn("passed", output)
            self.assertEqual(self.run_batch()[0], 0)
        request.assert_called_once()
        self.assertEqual(self.rows(), [("passed", 0, json.loads(response()))])

    def test_db_failure_during_reservation_prevents_dispatch(self):
        with (patch.object(live, "connect", side_effect=psycopg.OperationalError),
              patch.object(live, "request_search") as request):
            self.assertEqual(self.run_batch()[0], 1)
        request.assert_not_called()
        self.assertEqual(self.rows(), [])

    def test_provider_error_body_and_explicit_retry(self):
        body = b'{"error":{"message":"fixture credit rejection"}}'

        def reject(provider, key, options, capture):
            capture(body, 400)

        with patch.object(live, "request_search", side_effect=reject) as request:
            self.assertEqual(self.run_batch()[0], 1)
        request.assert_called_once()
        self.assertEqual(self.rows(), [("rejected", 0, json.loads(body))])
        entry = self.plan["executions"][0]
        entry["retry_of"] = entry["execution_key"]
        entry["execution_key"] += "__retry-1"
        self.plan_path.write_text(json.dumps(self.plan))
        with patch.object(live, "request_search", side_effect=self.passed) as request:
            self.assertEqual(self.run_batch("retry")[0], 0)
        request.assert_called_once()
        self.assertEqual(self.rows("SELECT outcome FROM executions"), [("passed",)])
        self.assertCountEqual(self.rows("SELECT status, retry_of FROM attempts"),
                              [("rejected", None), ("passed", entry["retry_of"])])

    def test_budget_includes_imported_provisional_cost(self):
        entry = self.plan["executions"][0]
        historical = batch.build_plan(date(2026, 11, 11), 1)
        historical["executions"] = [e for e in historical["executions"] if e["provider"] == entry["provider"]]
        path = save_history(self.data, historical, status="rejected", body=b'{"error":"fixture"}')
        record = json.loads(path.read_bytes())
        path.write_text(json.dumps(dict(record, estimated_usd=8.51, accounting_note="provisional fixture")))
        with patch.object(live, "request_search") as request:
            code, output = self.run_batch()
        self.assertEqual(code, 1)
        self.assertIn("operating budget blocks dispatch", output)
        request.assert_not_called()

    def test_import_retry_repeat_and_explicit_conflict(self):
        original = save_history(self.data, self.plan, status="rejected", body=b'{"error":"fixture"}')
        entry = self.plan["executions"][0]
        entry["retry_of"] = entry["execution_key"]
        entry["execution_key"] += "__retry-1"
        save_history(self.data, self.plan, "retry")
        code, output = invoke("import-collection", "--apply")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)["inserted"], 2)
        self.assertEqual(self.rows("SELECT outcome FROM executions"), [("passed",)])
        code, output = invoke("import-collection", "--apply")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)["inserted"], 0)
        self.assertEqual(json.loads(output)["unchanged"], 2)
        record = json.loads(original.read_bytes())
        original.write_text(json.dumps(dict(record, estimated_usd=8)))
        code, output = invoke("import-collection", "--apply")
        self.assertEqual(code, 1)
        self.assertIn("reconcile explicitly", output)
        self.assertEqual(self.rows("SELECT sum(estimated_usd) FROM attempts")[0][0], Decimal("0.14"))

    def test_concurrent_imports(self):
        save_history(self.data, self.plan)
        attempts = inventory(self.data)
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: import_attempts(self.dsn, attempts), range(2)))
        self.assertEqual(sorted(r["inserted"] for r in results), [0, 1])


if __name__ == "__main__":
    unittest.main()
