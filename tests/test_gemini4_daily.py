"""Daily Gemini plans preserve the prior cohort and persistence guarantees."""
from copy import deepcopy
import contextlib
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
from test_gemini4_comparison import carbon_response


class DailyTests(unittest.TestCase):
    def test_daily_identity_and_prior_manifest(self):
        previous = batch.GEMINI4_REVIEW.read_bytes()
        old_ids = set(json.loads(previous)['prompt_ids'])
        daily_ids = json.loads(batch.GEMINI4_DAILY_REVIEW.read_bytes())['prompt_ids']
        self.assertFalse(old_ids & set(daily_ids))
        for model in batch.GEMINI4_DAILY_MODELS:
            plan = batch.build_gemini4_daily_plan(model)
            self.assertEqual([e['prompt_id'] for e in batch.validate_plan(plan)], daily_ids)
            longer = deepcopy(plan)
            longer['transport_timeout_ms'] = 180_000
            self.assertEqual(len(batch.validate_plan(longer)), 12)
            longer['transport_timeout_ms'] = 1
            with self.assertRaises(ValueError): batch.validate_plan(longer)
            for mutation in ('missing', 'wrong_hash', 'wrong_cohort', 'wrong_limit'):
                changed = deepcopy(plan)
                if mutation == 'missing': changed['executions'].pop()
                elif mutation == 'wrong_hash': changed['comparison_manifest_sha256'] = '0' * 64
                elif mutation == 'wrong_cohort': changed['cohort'] = 'gemini4-comparison'
                else: changed['executions'][0]['request']['config']['max_output_tokens'] = 2200
                with self.assertRaises(ValueError): batch.validate_plan(changed)
        self.assertEqual(batch.GEMINI4_REVIEW.read_bytes(), previous)
        self.assertEqual(len(batch.validate_plan(batch.build_gemini4_plan('gemini-4-neon'))), 24)

    @unittest.skipUnless(os.getenv('REFERRAL_TEST_DATABASE_URL'), 'Needs isolated schema')
    def test_daily_persistence_and_duplicate_resume(self):
        base = os.environ['REFERRAL_TEST_DATABASE_URL']
        schema = 'daily4_test_' + uuid4().hex
        with psycopg.connect(base, autocommit=True) as conn:
            conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
        try:
            dsn = make_conninfo(base, options=f'-csearch_path={schema}')
            with psycopg.connect(dsn, autocommit=True) as conn:
                conn.execute(Path('migrations/002_collection_persistence.sql').read_text())
            with tempfile.TemporaryDirectory() as folder:
                def respond(provider, key, options, capture, *, timeout_ms=90_000):
                    self.assertEqual(timeout_ms, 180_000)
                    body = carbon_response()
                    body['modelVersion'] = options['model']
                    capture(json.dumps(body).encode(), 200)
                with patch.object(live, 'request_search', side_effect=respond) as request, contextlib.redirect_stdout(io.StringIO()):
                    for model in sorted(batch.GEMINI4_DAILY_MODELS):
                        plan = batch.build_gemini4_daily_plan(model)
                        plan['transport_timeout_ms'] = 180_000
                        for _ in range(2):
                            self.assertEqual(batch.run_batch(plan, Path(model), Path(folder), {'gemini':'fixture'}, url=dsn), 0)
                    self.assertEqual(request.call_count, 48)
                self.assertEqual(len(list(Path(folder).glob('live/collection/*/*/response.json'))), 48)
        finally:
            with psycopg.connect(base, autocommit=True) as conn:
                conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
