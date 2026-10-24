"""Export the built-in MCP input/output JSON Schemas without credentials or health data."""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from garmin_mcp.server import create_server

async def main():
    tools = await create_server(load_local_types=False).list_tools()
    document = {'version':'0.3.0', 'transport':'stdio',
                'description':'Built-in MCP JSON interfaces; account-discovered sport tools are added at runtime.',
                'tools':[t.model_dump(mode='json', exclude_none=True) for t in tools]}
    print(json.dumps(document, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    asyncio.run(main())
