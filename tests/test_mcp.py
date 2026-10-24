import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from garmin_mcp.garmin import GarminError
from garmin_mcp.server import create_server


class MCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_stdio_handshake_discovery_and_call(self):
        params = StdioServerParameters(command=sys.executable,
            args=["-m", "garmin_mcp", "--demo"],
            cwd=str(Path(__file__).resolve().parents[1]),
            env={"GARMIN_PERSONAL_API_KEY": ""})
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                tools = (await session.list_tools()).tools
                self.assertEqual(len(tools), 78)
                self.assertIn("prepare_coaching_context", [tool.name for tool in tools])
                self.assertEqual(tools[0].inputSchema["required"], ["date"])
                self.assertTrue(tools[0].annotations.readOnlyHint)
                result = await session.call_tool("get_steps", {"date": "2026-10-22"})
                self.assertFalse(result.isError)
                self.assertIsInstance(result.structuredContent, dict)
                self.assertEqual(result.structuredContent, json.loads(result.content[0].text))
                payload = json.loads(result.content[0].text)
                self.assertEqual(payload["source"], "demo")
                self.assertEqual(payload["data"][0]["totalSteps"], 4321)
                bad = await session.call_tool("get_steps", {"date": "2026-02-30"})
                self.assertTrue(bad.isError)
                missing = await session.call_tool("get_steps", {})
                self.assertTrue(missing.isError)
                for name, arguments in (
                    ("list_data_types", {}),
                    ("get_sleep", {"date": "2026-10-22"}),
                    ("get_stress", {"start_date": "2026-10-01", "end_date": "2026-11-05"}),
                    ("get_lap_swimming_workouts", {"start_date": "2026-10-01", "end_date": "2026-10-22"}),
                    ("list_workout_types", {}),
                    ("get_activity", {"activity_id": "123"}),
                    ("prepare_coaching_context", {"start_date": "2026-10-01", "end_date": "2026-10-22"}),
                    ("log_workout", {"record_id": "demo-log", "workout": {"date": "2026-10-22", "sport": "strength_training", "sets": [{"exercise": "squat", "reps": 5, "weight": 50}]}}),
                ):
                    with self.subTest(tool=name):
                        response = await session.call_tool(name, arguments)
                        self.assertFalse(response.isError, response.content)
                        self.assertIsInstance(response.structuredContent, dict)
                        if name == "log_workout":
                            self.assertEqual(json.loads(response.content[0].text)["status"], "not_saved")

    async def test_demo_never_calls_garmin(self):
        with patch("garmin_mcp.server.fetch_steps") as fetch:
            await create_server(demo=True).call_tool("get_steps", {"date": "2026-10-22"})
            fetch.assert_not_called()

    async def test_live_failure_never_silently_returns_demo(self):
        with patch("garmin_mcp.server.fetch_steps", side_effect=GarminError("Authentication failed")):
            with self.assertRaisesRegex(Exception, "Authentication failed"):
                await create_server().call_tool("get_steps", {"date": "2026-10-22"})

    async def test_live_missing_data_is_marked(self):
        with patch("garmin_mcp.server.fetch_steps", return_value=[]):
            content = await create_server().call_tool("get_steps", {"date": "2026-10-22"})
            structured = content[1]
            self.assertEqual(structured["status"], "no_data")
            self.assertEqual(structured["source"], "garmin")
