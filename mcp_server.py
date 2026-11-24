"""mcp_server.py - the same tools served by the official MCP Python SDK over stdio.

Run:  python mcp_server.py            (scenario from env FAB_SENTRY_SCENARIO, default S01)
Stage 2 adds langchain-mcp-adapters client wiring and a CLI round-trip test.
"""
from __future__ import annotations

import os

try:                                   # mcp 1.x (pinned in requirements.txt)
    from mcp.server.fastmcp import FastMCP
except ModuleNotFoundError:            # mcp 2.x renamed it
    from mcp.server.mcpserver import MCPServer as FastMCP

from tools_core import SimBackend

mcp = FastMCP("fab-sentry-simulated-fab")
_backend = SimBackend(os.getenv("FAB_SENTRY_SCENARIO", "S01"))


@mcp.tool()
def query_sensor_window(tag: str, minutes_back: int = 120) -> dict:
    """Summary statistics for a sensor over the last N minutes before the alarm."""
    return _backend.query_sensor_window(tag, minutes_back)


@mcp.tool()
def compute_rate_of_change(tag: str, minutes_back: int = 120) -> dict:
    """Least-squares slope per hour over the last N minutes."""
    return _backend.compute_rate_of_change(tag, minutes_back)


@mcp.tool()
def check_guardband_and_cal(tag: str) -> dict:
    """Deterministic verdict for the latest reading (guard band and calibration)."""
    return _backend.check_guardband_and_cal(tag)


@mcp.tool()
def trace_upstream_loop(asset_id: str) -> dict:
    """All assets upstream of an asset, nearest first, with sensor tags."""
    return _backend.trace_upstream_loop(asset_id)


@mcp.tool()
def get_asset_dependencies(asset_id: str) -> dict:
    """Direct upstream and downstream neighbours of an asset."""
    return _backend.get_asset_dependencies(asset_id)


@mcp.tool()
def get_recent_work_orders(asset_id: str = "", hours: int = 72) -> dict:
    """Maintenance work orders within the last N hours, optionally for one asset."""
    return _backend.get_recent_work_orders(asset_id, hours)


@mcp.tool()
def get_resin_and_lamp_runtime(asset_id: str) -> dict:
    """Runtime hours versus rated life for lamps, resin, membranes, purifier beds and filters."""
    return _backend.get_resin_and_lamp_runtime(asset_id)


@mcp.tool()
def search_knowledge_base(query: str, k: int = 3) -> dict:
    """Hybrid keyword + embedding search of the synthetic O&M knowledge base."""
    return _backend.search_knowledge_base(query, k)


@mcp.tool()
def find_similar_past_cases(k: int = 3) -> dict:
    """Human-approved past investigations similar to this alarm. Precedents only."""
    return _backend.find_similar_past_cases(k)


if __name__ == "__main__":
    mcp.run()
