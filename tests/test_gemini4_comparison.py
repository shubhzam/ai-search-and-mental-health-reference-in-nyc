"""Approved Carbon requests use the standard persistence and recovery path."""
import contextlib
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from referral_collector import batch, live
from referral_collector.pilot_providers import observe


def carbon_response(text='Four referral options with sources.'):
    return {
        'modelVersion': 'gemini-4-carbon', 'responseId': 'fixture',
        'usageMetadata': {'promptTokenCount': 100, 'candidatesTokenCount': 100, 'thoughtsTokenCount': 100},
        'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': text}]},
                        'groundingMetadata': {'webSearchQueries': ['NYC services'],
                                              'groundingChunks': [{'web': {'uri': 'https://example.org'}}]}}],
    }


class Gemini4Tests(unittest.TestCase):
    def test_exact_matching_and_tampering(self):
        baseline = json.loads(batch.GEMINI4_REVIEW.read_bytes())["prompt_ids"]
        for model in sorted(batch.GEMINI4_MODELS):
            plan = batch.build_gemini4_plan(model)
            self.assertEqual([e["prompt_id"] for e in batch.validate_plan(plan)], baseline)
            for mutation in ("duplicate", "limit", "model", "missing"):
                changed = deepcopy(plan)
                if mutation == "duplicate":
                    changed["executions"][1] = deepcopy(changed["executions"][0])
                elif mutation == "limit":
                    changed["executions"][0]["request"]["config"]["max_output_tokens"] = 2200
                elif mutation == "model":
                    changed["executions"][0]["request"]["model"] = "gemini-4-carbon"
                else:
                    changed["executions"].pop()
                with self.assertRaises(ValueError):
                    batch.validate_plan(changed)
            changed = deepcopy(plan)
            changed["executions"] = changed["executions"][10:]
            changed["continuation"] = True
            self.assertEqual(len(batch.validate_plan(changed)), 14)

    def test_rates_identity_and_visible_answer(self):
        for model, expected in [("gemini-4-neon", .0173), ("gemini-4-hydrogen", .01565), ("gemini-4-argon", .0162)]:
            body = carbon_response()
            body["modelVersion"] = model
            result = observe("gemini", model, body)
            self.assertTrue(result.complete and result.search_observed)
            self.assertAlmostEqual(result.estimated_usd, expected)
            body["modelVersion"] = "other"
            self.assertFalse(observe("gemini", model, body).complete)
            body["modelVersion"] = model
            body["candidates"][0]["content"]["parts"][0]["text"] = ""
            self.assertFalse(observe("gemini", model, body).complete)

    @unittest.skipUnless(os.getenv("REFERRAL_TEST_DATABASE_URL"), "Needs temporary schema access")
    def test_persistence_and_duplicate_resume(self):
        base = os.environ["REFERRAL_TEST_DATABASE_URL"]
        schema = "gemini4_test_" + uuid4().hex
        with psycopg.connect(base, autocommit=True) as conn:
            conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        try:
            dsn = make_conninfo(base, options=f"-csearch_path={schema}")
            with psycopg.connect(dsn, autocommit=True) as conn:
                conn.execute(Path("migrations/002_collection_persistence.sql").read_text())
            with tempfile.TemporaryDirectory() as folder:
                data = Path(folder)
                def respond(provider, key, options, capture):
                    body = carbon_response()
                    body["modelVersion"] = options["model"]
                    self.assertEqual(options["config"]["max_output_tokens"], 8192)
                    capture(json.dumps(body).encode(), 200)
                with patch.object(live, "request_search", side_effect=respond) as request, contextlib.redirect_stdout(io.StringIO()):
                    for model in sorted(batch.GEMINI4_MODELS):
                        plan = batch.build_gemini4_plan(model)
                        for _ in range(2):
                            self.assertEqual(batch.run_batch(plan, Path(model), data, {"gemini": "fixture"}, url=dsn), 0)
                    self.assertEqual(request.call_count, 72)
                with psycopg.connect(dsn) as conn:
                    rows = conn.execute("SELECT requested_model,count(*) FROM attempts JOIN executions USING(execution_id) WHERE status='passed' AND response IS NOT NULL AND reserved_usd=0 GROUP BY requested_model").fetchall()
                    self.assertEqual(dict(rows), {m:24 for m in batch.GEMINI4_MODELS})
                self.assertEqual(len(list(data.glob("live/collection/*/*/response.json"))), 72)
        finally:
            with psycopg.connect(base, autocommit=True) as conn:
                conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
