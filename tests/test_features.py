import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from pydantic import ValidationError

from garmin_mcp import catalog, data, analysis, journal, dashboard
from garmin_mcp.garmin import GarminError, GarminClient
from garmin_mcp.server import create_server


class RetrievalTests(unittest.TestCase):
    def test_catalog_builds_all_routes_and_validates_before_network(self):
        self.assertEqual(len(catalog.DATASETS), 25)
        for name, (kind, _, _) in catalog.DATASETS.items():
            kwargs = {'date': '2026-10-22', 'today_date': '2026-10-23', 'activity_id': '123'}
            path = catalog.build_request(name, **kwargs)
            self.assertTrue(path.startswith('/'), name)
            self.assertNotIn('{', path)
        self.assertIn('calendarDate=2026-10-22', catalog.build_request('daily_summary', date='2026-10-22'))
        self.assertIn('includeAll=true', catalog.build_request('weight', date='2026-10-22'))
        client = Mock()
        cases = [('unknown', {}), ('sleep', {'date': '2026-02-30'}),
                 ('steps', {'start_date': '2026-01-01', 'end_date': '2026-02-01'}),
                 ('activities', {'limit': 101}), ('activities', {'start_date': '2026-10-01'}),
                 ('activity', {'activity_id': '../secret'}), ('menstrual_day', {'date': '2026-10-22'})]
        for name, args in cases:
            with self.subTest(name=name, args=args), self.assertRaises(ValueError):
                data.query(name, client=client, **args)
        client.get.assert_not_called()

    def test_chunk_boundaries_no_overlap_and_no_data(self):
        got = data.collect('steps', '2026-01-01', '2026-03-05', demo=True)
        self.assertEqual(len(got['rows']), 64)
        self.assertEqual(len({r['calendarDate'] for r in got['rows']}), 64)
        self.assertEqual([(c['start_date'], c['end_date']) for c in got['chunks']],
                         [('2026-01-01', '2026-01-28'), ('2026-01-29', '2026-02-25'), ('2026-02-26', '2026-03-05')])
        self.assertTrue(got['complete'])
        self.assertEqual(data.collect('weight', '2026-10-01', '2026-10-02', demo=True)['status'], 'no_data')

    def test_partial_failure_preserves_previous_chunk_and_stops_rate_limit(self):
        client = Mock()
        client.get.side_effect = [[{'calendarDate': '2026-01-01', 'totalSteps': 0}], GarminError('Rate limit', 'rate_limited')]
        result = data.collect('steps', '2026-01-01', '2026-03-30', client=client)
        self.assertEqual(result['status'], 'partial')
        self.assertFalse(result['complete'])
        self.assertEqual(result['rows'][0]['totalSteps'], 0)
        self.assertEqual(client.get.call_count, 2)

    def test_activity_pagination_deduplicates_and_reports_cap(self):
        client = Mock()
        first = [{'activityId': n} for n in range(1, 101)]
        client.get.side_effect = [first, [{'activityId': 100}, {'activityId': 101}]]
        got = data.activities('2026-10-01', '2026-10-22', client=client)
        self.assertTrue(got['complete'])
        self.assertEqual(len(got['data']), 101)
        self.assertIn('start=100', client.get.call_args.args[0])
        client.get.side_effect = [first]
        got = data.activities('2026-10-01', '2026-10-22', client=client, max_records=100)
        self.assertFalse(got['complete'])
        self.assertEqual(got['next_start'], 100)
        client.get.side_effect = [first, GarminError('Unavailable', 'connection_error')]
        got = data.activities('2026-10-01', '2026-10-22', client=client)
        self.assertEqual(got['status'], 'partial')
        self.assertEqual(len(got['data']), 100)

    def test_token_reused_only_within_client(self):
        with patch('garmin_mcp.garmin.load_key', return_value='test'), patch('garmin_mcp.garmin.request_text', side_effect=['token', '[]', '[]']) as request:
            client = GarminClient()
            client.get('/one')
            client.get('/two')
            self.assertEqual(request.call_count, 3)


class AnalysisTests(unittest.TestCase):
    def test_missing_and_sentinels_not_counted_as_zero(self):
        rows = [{'calendarDate': '2026-10-01', 'value': 0},
                {'calendarDate': '2026-10-02', 'value': -1},
                {'calendarDate': '2026-10-03', 'value': None},
                {'calendarDate': '2026-10-04', 'value': float('nan')},
                {'calendarDate': '2026-10-05', 'value': 100},
                {'calendarDate': '2026-10-05', 'value': 200}]
        result = analysis.describe(analysis.series(rows, ['value']), '2026-10-01', '2026-10-05', 'steps')
        self.assertEqual(result['observed_days'], 2)
        self.assertEqual(result['missing_days'], 3)
        self.assertEqual(result['mean'], 100)

    def test_pace_is_distance_weighted_and_sports_separate(self):
        rows = [{'activityType': {'typeKey': 'running'}, 'distance': 1000, 'duration': 300},
                {'activityType': {'typeKey': 'running'}, 'distance': 9000, 'duration': 3600},
                {'activityType': {'typeKey': 'running'}, 'duration': 200},
                {'activityType': {'typeKey': 'cycling'}, 'distance': 10000, 'duration': 1000}]
        got = analysis.summarize_activities(rows)
        self.assertEqual(got['running']['pace_seconds_per_km'], 390)
        self.assertIsNone(got['cycling']['pace_seconds_per_km'])
        self.assertEqual(got['running']['missing_distance_count'], 1)

    def test_strength_units_assistance_and_missing_previous_period(self):
        sets = [{'exercise': 'Squat', 'reps': 5, 'weight': 100, 'unit': 'lb'},
                {'exercise': 'Squat', 'reps': 5, 'weight': 20, 'load_type': 'assisted'}]
        workout = journal.WorkoutLog(date='2026-10-22', sport='strength', sets=sets).model_dump()
        got = analysis.strength_progress([{'id': 'a', 'data': workout}])
        external = next(r for r in got['exercises'] if r['load_type'] == 'external')['sessions'][0]
        assisted = next(r for r in got['exercises'] if r['load_type'] == 'assisted')['sessions'][0]
        self.assertAlmostEqual(external['external_volume_kg_reps'], 226.8, places=2)
        self.assertIsNone(assisted['external_volume_kg_reps'])
        self.assertIsNone(assisted['estimated_1rm_kg'])
        report = analysis.overview('2026-10-20', '2026-10-22', demo=True)
        comparison = analysis.compare_periods(report)['metrics']['steps']
        self.assertEqual(comparison['previous_observed_days'], 0)
        self.assertIsNone(comparison['difference'])


class JournalAndDashboardTests(unittest.TestCase):
    def test_idempotent_writes_explicit_correction_and_history(self):
        with tempfile.TemporaryDirectory() as directory:
            payload = {'date': '2026-10-22', 'sport': 'strength'}
            self.assertEqual(journal.read('workout', root=directory), [])
            self.assertFalse((Path(directory)/'coach.sqlite3').exists())
            self.assertEqual(journal.save('workout', 'one', payload, root=directory)['revision'], 1)
            self.assertEqual(journal.save('workout', 'one', payload, root=directory)['status'], 'unchanged')
            payload['notes'] = 'Correction'
            with self.assertRaises(ValueError):
                journal.save('workout', 'one', payload, root=directory)
            self.assertEqual(journal.save('workout', 'one', payload, replace=True, root=directory)['revision'], 2)
            self.assertEqual(journal.read('workout', '2026-10-22', '2026-10-22', root=directory)[0]['data']['notes'], 'Correction')
            with journal.database(directory) as conn:
                self.assertEqual(conn.execute('SELECT count(*) FROM history').fetchone()[0], 2)
            self.assertEqual((Path(directory)/'coach.sqlite3').stat().st_mode & 0o777, 0o600)

    def test_models_reject_ambiguous_or_invalid_records(self):
        for fields in ({'reps': True}, {'weight': float('inf')}, {'unit': 'stone'}, {'rpe': 11}):
            with self.assertRaises(ValidationError):
                journal.ExerciseSet.model_validate({'exercise': 'squat', 'reps': 5, 'weight': 20, **fields})
        with self.assertRaises(ValidationError):
            journal.CoachProfile(timezone='wrong')
        with self.assertRaises(ValidationError):
            journal.CoachProfile(available_days=['Mon', 'Mon'])
        with self.assertRaises(ValidationError):
            journal.WorkoutLog(date='2026-02-30', sport='run')
        with self.assertRaises(ValueError):
            journal.record_id('../escape')

    def test_plan_roundtrip_is_draft(self):
        with tempfile.TemporaryDirectory() as directory:
            plan = {'goal': 'Consistency', 'rationale': 'User preference', 'evidence_start': '2026-10-01',
                    'evidence_end': '2026-10-22', 'sessions': [{'date': '2026-10-24', 'sport': 'running',
                    'duration_minutes': 20, 'description': 'Easy conversational effort'}]}
            journal.save('plan', 'week1', plan, root=directory)
            self.assertEqual(journal.read('plan', root=directory)[0]['data']['status'], 'draft')

    def test_dashboard_escapes_notes_and_saves_valid_snapshot(self):
        report = analysis.overview('2026-10-01', '2026-10-22', demo=True)
        report['workout_logs'] = [{'data': {'date': '2026-10-22', 'sport': 'strength', 'notes': '<script>alert(1)</script>'}}]
        with tempfile.TemporaryDirectory() as directory:
            saved = dashboard.save(report, root=directory)
            html = Path(saved['files']['html']).read_text()
            self.assertIn('SYNTHETIC DEMO', html)
            self.assertNotIn('<script>alert(1)</script>', html)
            self.assertIn('&lt;script&gt;', html)
            self.assertFalse(saved['published'])
            self.assertEqual(json.loads(Path(saved['files']['json']).read_text())['metrics']['sleep_hours']['mean'], 7.5)

    def test_dashboard_embedded_data_cannot_escape_script_or_expose_gps(self):
        import re
        report = analysis.overview('2026-10-01', '2026-10-22', demo=True)
        row = report['activities']['data'][0]
        row.update(activityName='</script><script>alert(2)</script>', startLatitude=29.6, ownerId=12345)
        rendered = dashboard.render(report)
        payload = re.search(r'<script id="report-data" type="application/json">(.*?)</script>', rendered, re.S).group(1)
        self.assertNotIn('<', payload)
        parsed = json.loads(payload)
        self.assertEqual(parsed['activities']['data'][0]['activityName'], row['activityName'])
        self.assertNotIn('startLatitude', payload)
        self.assertNotIn('ownerId', payload)


class LocalMCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_typed_write_read_and_strength_analysis_through_mcp(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(journal, 'DATA_DIR', Path(directory)), patch('garmin_mcp.garmin.load_key') as credentials:
            server = create_server()
            result = await server.call_tool('log_workout', {'record_id': 'one', 'workout': {
                'date': '2026-10-22', 'sport': 'strength', 'sets': [{'exercise': 'squat', 'weight': 60, 'reps': 5}]}})
            self.assertEqual(result[1]['status'], 'saved')
            result = await server.call_tool('analyze_strength_progress', {'start_date': '2026-10-01', 'end_date': '2026-10-22'})
            self.assertEqual(result[1]['exercises'][0]['sessions'][0]['external_volume_kg_reps'], 300)
            credentials.assert_not_called()

    async def test_activity_download_validates_zip_and_never_extracts(self):
        import io
        import zipfile
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, 'w') as stream:
            stream.writestr('../unsafe.fit', b'synthetic bytes')
        with tempfile.TemporaryDirectory() as directory, patch.object(journal, 'DATA_DIR', Path(directory)), patch.object(GarminClient, 'download', return_value=archive.getvalue()):
            server = create_server()
            result = await server.call_tool('download_activity', {'activity_id': '123'})
            payload = result[1]
            self.assertFalse(payload['extracted'])
            self.assertTrue(Path(payload['path']).exists())
            self.assertEqual(payload['members'], ['../unsafe.fit'])
            self.assertEqual(len(list(Path(directory).rglob('*'))), 2)
            again = await server.call_tool('download_activity', {'activity_id': '123'})
            self.assertEqual(again[1]['path'], payload['path'])
        with patch.object(GarminClient, 'download', return_value=b'not a ZIP'):
            with self.assertRaisesRegex(Exception, 'valid ZIP'):
                await create_server().call_tool('download_activity', {'activity_id': '123'})

    async def test_profile_plan_and_dashboard_tools(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(journal, 'DATA_DIR', Path(directory)):
            server = create_server()
            await server.call_tool('save_coach_profile', {'profile': {'goals': ['5K'], 'available_days': ['Tue']}})
            got = await server.call_tool('get_coach_profile', {})
            self.assertEqual(got[1]['data'][0]['data']['goals'], ['5K'])
            plan = {'goal': '5K', 'rationale': 'User goal', 'evidence_start': '2026-10-01', 'evidence_end': '2026-10-22',
                    'sessions': [{'date': '2026-10-24', 'sport': 'running', 'duration_minutes': 20, 'description': 'Easy'}]}
            await server.call_tool('save_training_plan', {'record_id': 'p1', 'plan': plan})
            got = await server.call_tool('list_training_plans', {})
            self.assertEqual(got[1]['data'][0]['data']['status'], 'draft')
            with patch.object(GarminClient, 'get', side_effect=AssertionError('Demo must not access Garmin')):
                got = await create_server(demo=True).call_tool('create_dashboard', {'start_date': '2026-10-01', 'end_date': '2026-10-22'})
            payload = got[1]
            self.assertEqual(payload['source'], 'demo')
            self.assertTrue(Path(payload['files']['html']).exists())
