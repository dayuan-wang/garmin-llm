import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from garmin_mcp import data, workouts, journal
from garmin_mcp.catalog import DATASETS, build_request
from garmin_mcp.health_tools import HEALTH_TOOLS, SUMMARY_FIELDS
from garmin_mcp.server import create_server


def payload(result):
    return result[1]


class InterfaceTests(unittest.IsolatedAsyncioTestCase):
    async def test_every_health_dataset_has_its_own_typed_tool_and_correct_route(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(journal, 'DATA_DIR', Path(folder)):
            server = create_server()
            tools = {t.name:t for t in await server.list_tools()}
            for dataset, name in HEALTH_TOOLS.items():
                kind = DATASETS[dataset][0]
                args = ({'start_date':'2026-10-01', 'end_date':'2026-10-02'} if kind.startswith('range') else
                        {'date':'2026-10-02'} if kind.startswith('day') else {})
                if dataset == 'menstrual_day': args['today_date'] = '2026-10-24'
                with self.subTest(dataset=dataset), patch('garmin_mcp.garmin.GarminClient.get', return_value=[]) as get:
                    result = payload(await server.call_tool(name, args))
                    self.assertEqual(result['dataset'], dataset)
                    self.assertEqual(get.call_args.args[0], build_request(dataset, **args))
                    self.assertEqual(set(tools[name].inputSchema.get('required', [])), set(args))
                    self.assertTrue(tools[name].annotations.readOnlyHint)
                    self.assertIsNotNone(tools[name].outputSchema)
                    self.assertNotIn('dataset', tools[name].inputSchema['properties'])

    async def test_every_builtin_sport_routes_exactly_and_does_not_mix_child_sports(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(journal, 'DATA_DIR', Path(folder)):
            server = create_server()
            for key in workouts.BUILTIN_TYPES:
                rows = [{'activityId':1, 'activityType':{'typeKey':key}, 'customSportField':42},
                        {'activityId':2, 'activityType':{'typeKey':'different_sport'}}]
                with self.subTest(key=key), patch('garmin_mcp.garmin.GarminClient.get', return_value=rows) as get:
                    result = payload(await server.call_tool(workouts.tool_name(key), {'start_date':'2026-10-01','end_date':'2026-10-22'}))
                    self.assertIn('activityType='+key, get.call_args.args[0])
                    self.assertEqual([r['activityId'] for r in result['data']], [1])
                    self.assertEqual(result['data'][0]['customSportField'], 42)
                    self.assertEqual(result['excluded_other_type_count'], 1)
                    self.assertTrue(result['complete'])

    async def test_dynamic_types_survive_restart_without_credentials_or_health_records(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(journal, 'DATA_DIR', Path(folder)):
            server = create_server()
            rows = [{'activityType':{'typeKey':'new_sport'}, 'activityName':'Private name'},
                    {'activityType':{'typeKey':'../invalid'}}]
            response = {'data':rows,'source':'garmin','status':'partial','complete':False}
            with patch('garmin_mcp.data.activities', return_value=response):
                result = payload(await server.call_tool('discover_workout_types', {'start_date':'2026-10-01','end_date':'2026-10-22'}))
            self.assertFalse(result['complete'])
            self.assertEqual(result['added_tools'], ['get_new_sport_workouts'])
            self.assertEqual(result['invalid_type_rows'], 1)
            with patch('garmin_mcp.garmin.load_key') as credentials:
                self.assertIn('get_new_sport_workouts', [t.name for t in await create_server().list_tools()])
                credentials.assert_not_called()
            with journal.database() as conn:
                self.assertEqual(conn.execute('SELECT type_key FROM activity_types').fetchall(), [('new_sport',)])
                self.assertEqual(conn.execute('SELECT count(*) FROM records').fetchone()[0], 0)
            with patch('garmin_mcp.data.activities', return_value=response):
                again = payload(await server.call_tool('discover_workout_types', {'start_date':'2026-10-01','end_date':'2026-10-22'}))
                self.assertEqual(again['added_tools'], [])

    async def test_demo_discovery_and_schema_listing_are_side_effect_free(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(journal, 'DATA_DIR', Path(folder)), patch('garmin_mcp.garmin.load_key') as credentials:
            server = create_server(demo=True)
            result = payload(await server.call_tool('discover_workout_types', {'start_date':'2026-10-01','end_date':'2026-10-22'}))
            self.assertEqual(result['observed_types'], ['running'])
            self.assertFalse(result['persisted'])
            self.assertFalse(list(Path(folder).iterdir()))
            credentials.assert_not_called()

    async def test_summary_fields_keep_zero_null_and_never_return_unrelated_health_data(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(journal, 'DATA_DIR', Path(folder)):
            server = create_server()
            for name, field in SUMMARY_FIELDS.items():
                raw = {'data':[{'calendarDate':'2026-10-01', field:0, 'unrelated':'private'}, {'calendarDate':'2026-10-02'}]}
                with self.subTest(name=name), patch('garmin_mcp.garmin.GarminClient.get', return_value=raw):
                    result = payload(await server.call_tool('get_'+name, {'start_date':'2026-10-01','end_date':'2026-10-02'}))
                    self.assertEqual(result['data'][0]['data'], 0)
                    self.assertEqual(result['data'][0]['status'], 'ok')
                    self.assertIsNone(result['data'][1]['data'])
                    self.assertNotIn('private', json.dumps(result))

    async def test_dedicated_range_reader_preserves_partial_data(self):
        from garmin_mcp.garmin import GarminError
        with tempfile.TemporaryDirectory() as folder, patch.object(journal, 'DATA_DIR', Path(folder)):
            with patch('garmin_mcp.garmin.GarminClient.get', side_effect=[[{'calendarDate':'2026-10-01','value':0}], GarminError('Rate limited','rate_limited')]):
                result = payload(await create_server().call_tool('get_stress', {'start_date':'2026-10-01','end_date':'2026-11-15'}))
            self.assertEqual(result['status'], 'partial')
            self.assertFalse(result['complete'])
            self.assertEqual(len(result['data']), 1)
            self.assertEqual(result['chunks'][0]['end_date'], '2026-10-28')


class TypeValidationTests(unittest.TestCase):
    def test_unknown_future_types_are_supported_but_names_cannot_escape_tool_namespace(self):
        self.assertEqual(workouts.tool_name('new_sport_2'), 'get_new_sport_2_workouts')
        for value in ('../x','Running','a-b','a'*49,'',None):
            with self.assertRaises(ValueError): workouts.tool_name(value)

    def test_stats_window_and_sleep_window_have_different_limits(self):
        build_request('steps',start_date='2026-10-01',end_date='2026-10-28')
        with self.assertRaises(ValueError): build_request('steps',start_date='2026-10-01',end_date='2026-10-29')
        build_request('sleep_summaries',start_date='2026-10-01',end_date='2026-10-31')
        report = data.collect('sleep_summaries','2026-10-01','2026-11-05',demo=True)
        self.assertEqual(report['chunks'][0]['end_date'],'2026-10-31')

    def test_exact_filter_keeps_incomplete_retrieval_flag(self):
        rows = [{'activityId':1,'activityType':{'typeKey':'trail_running'}}]
        client = Mock();client.get.return_value=rows
        result = workouts.query_type('running','2026-10-01','2026-10-22',max_records=1,client=client)
        self.assertFalse(result['complete'])
        self.assertEqual(result['data'],[])
        self.assertEqual(result['next_start'],1)
