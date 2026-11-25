"""Approved Carbon requests use the standard persistence and recovery path."""
import contextlib
from copy import deepcopy
from datetime import datetime
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


class CarbonTests(unittest.TestCase):
    def test_reviewed_plan_and_rejection_of_changes(self):
        plan = batch.build_carbon_plan()
        self.assertEqual(len(batch.validate_plan(plan)), 12)
        for field, value in [('provider', 'openai'), ('prompt_id', 'anc-03')]:
            changed = deepcopy(plan)
            changed['executions'][0][field] = value
            with self.assertRaises(ValueError):
                batch.validate_plan(changed)
        changed = deepcopy(plan)
        changed['executions'][0]['request']['config']['max_output_tokens'] = 2200
        with self.assertRaises(ValueError):
            batch.validate_plan(changed)
        changed = deepcopy(plan)
        changed.pop('cohort')
        with self.assertRaises(ValueError):
            batch.validate_plan(changed)

    def test_carbon_rates_and_visible_completion(self):
        result = observe('gemini', 'gemini-4-carbon', carbon_response())
        self.assertTrue(result.complete and result.search_observed)
        self.assertAlmostEqual(result.estimated_usd, .0162)
        self.assertFalse(observe('gemini', 'gemini-4-carbon', carbon_response('')).complete)
        body = carbon_response()
        body['modelVersion'] = 'other'
        self.assertFalse(observe('gemini', 'gemini-4-carbon', body).complete)

    @unittest.skipUnless(os.getenv('REFERRAL_TEST_DATABASE_URL'), 'Needs temporary schema access')
    def test_database_persistence_and_duplicate_resume(self):
        base = os.environ['REFERRAL_TEST_DATABASE_URL']
        schema = 'carbon_test_' + uuid4().hex
        with psycopg.connect(base, autocommit=True) as conn:
            conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
        try:
            dsn = make_conninfo(base, options=f'-csearch_path={schema}')
            with psycopg.connect(dsn, autocommit=True) as conn:
                conn.execute(Path('migrations/002_collection_persistence.sql').read_text())
            with tempfile.TemporaryDirectory() as folder:
                data = Path(folder)
                plan = batch.build_carbon_plan()
                body = json.dumps(carbon_response()).encode()
                def respond(provider, key, options, capture):
                    self.assertEqual(options['model'], 'gemini-4-carbon')
                    self.assertEqual(options['config']['max_output_tokens'], 8192)
                    capture(body, 200)
                with patch.object(live, 'request_search', side_effect=respond) as request, contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(batch.run_batch(plan, Path('carbon-fixture'), data, {'gemini': 'fixture'}, url=dsn), 0)
                    self.assertEqual(batch.run_batch(plan, Path('carbon-fixture'), data, {'gemini': 'fixture'}, url=dsn), 0)
                    self.assertEqual(request.call_count, 12)
                with psycopg.connect(dsn) as conn:
                    self.assertEqual(conn.execute("SELECT count(*) FROM attempts WHERE status='passed' AND response IS NOT NULL AND reserved_usd=0").fetchone()[0], 12)
                self.assertEqual(len(list(data.glob('live/collection/*/*/response.json'))), 12)
        finally:
            with psycopg.connect(base, autocommit=True) as conn:
                conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
