import asyncio
import json
import os

import pytest

from engine import run_scripted_offline
from replay import list_traces, load_trace, save_trace


def test_only_live_runs_can_be_recorded(tmp_path):
    with pytest.raises(ValueError):
        save_trace(run_scripted_offline("S01"), tmp_path)


def test_live_trace_round_trips_as_replay(tmp_path):
    live = run_scripted_offline("S01").model_copy(update={"mode": "live-gemini"})
    p = save_trace(live, tmp_path)
    assert list_traces(tmp_path) == [p]
    assert load_trace(p).mode == "replay"


def test_mcp_matches_in_process_tools():
    pytest.importorskip("mcp")
    os.environ["FAB_SENTRY_SCENARIO"] = "S03"
    import mcp_server
    res = asyncio.run(mcp_server.mcp.call_tool("check_guardband_and_cal", {"tag": "UPW_B_DO_POU"}))
    if hasattr(res, "content"):
        blocks = res.content
    elif isinstance(res, tuple):
        blocks = res[0]
    else:
        blocks = res
    payload = json.loads(blocks[0].text)
    assert payload == mcp_server._backend.check_guardband_and_cal("UPW_B_DO_POU")
