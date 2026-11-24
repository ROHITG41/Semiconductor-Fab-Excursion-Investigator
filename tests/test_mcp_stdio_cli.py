"""Full MCP round trip: start mcp_server.py as a real subprocess and talk to it over stdio."""
import asyncio
import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp")
ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {"query_sensor_window", "compute_rate_of_change", "check_guardband_and_cal", "trace_upstream_loop",
            "get_asset_dependencies", "get_recent_work_orders", "get_resin_and_lamp_runtime",
            "search_knowledge_base", "find_similar_past_cases"}


async def _roundtrip():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    import os
    env = {**os.environ, "FAB_SENTRY_SCENARIO": "S03"}
    params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "mcp_server.py")], env=env, cwd=str(ROOT))
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            names = {t.name for t in (await s.list_tools()).tools}
            g = json.loads((await s.call_tool("check_guardband_and_cal", {"tag": "UPW_B_DO_POU"})).content[0].text)
            kb = json.loads((await s.call_tool("search_knowledge_base", {"query": "dissolved oxygen after valve work", "k": 2})).content[0].text)
            return names, g, kb


def test_stdio_server_lists_and_serves_all_tools():
    names, g, kb = asyncio.run(asyncio.wait_for(_roundtrip(), 60))
    assert names == EXPECTED
    assert g["verdict"] == "FAIL" and g["tag"] == "UPW_B_DO_POU"
    assert kb["results"] and kb["results"][0]["chunk_id"]
