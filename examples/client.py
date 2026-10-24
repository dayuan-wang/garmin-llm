"""A real MCP client that launches our server; no LLM needed.

Run from the project root: .venv/bin/python examples/client.py
Add --live --date YYYY-MM-DD only when you want to query your Garmin account.
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def run(live: bool, day: str, tool: str = "get_steps", arguments: dict | None = None):
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "garmin_mcp"] + ([] if live else ["--demo"]),
        cwd=str(Path(__file__).resolve().parents[1]),
        env={name: os.environ[name] for name in ("GARMIN_PERSONAL_API_KEY",) if name in os.environ},
    )
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            print("1. Connected to MCP server")
            listed = await session.list_tools()
            print("2. Discovered tools:", [tool.name for tool in listed.tools])
            selected = next((t for t in listed.tools if t.name == tool), None)
            if selected is None:
                print("Unknown tool:", tool)
                return 1
            print("   Tool input schema:", json.dumps(selected.inputSchema))
            result = await session.call_tool(tool, arguments if arguments is not None else ({"date": day} if tool == "get_steps" else {}))
            print("3. Tool result:")
            for content in result.content:
                if content.type == "text":
                    print(content.text)
            failed = result.isError
    return 1 if failed else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Query real Garmin data; default is demo")
    parser.add_argument("--date", default="2026-10-22")
    parser.add_argument("--tool", default="get_steps")
    parser.add_argument("--arguments", type=json.loads, help="JSON object of tool arguments; never include credentials")
    args = parser.parse_args()
    if args.arguments is not None and not isinstance(args.arguments, dict):
        parser.error("--arguments must be a JSON object")
    raise SystemExit(asyncio.run(run(args.live, args.date, args.tool, args.arguments)))
