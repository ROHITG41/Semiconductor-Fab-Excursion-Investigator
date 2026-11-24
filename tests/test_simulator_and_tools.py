import json
import re
from pathlib import Path

import pytest

from config import DATA_DIR
from tools_core import SimBackend, TOOL_NAMES

ROOT = Path(__file__).resolve().parents[1]
ALL_GOLD = json.loads((DATA_DIR / "golden_excursions.json").read_text())["scenarios"]
GOLD = [g for g in ALL_GOLD if g.get("tier", "core") == "core"]   # hard-tier scenarios are covered in test_hard_scenarios.py


def test_ten_scenarios_with_ground_truth():
    assert len(GOLD) == 10 and len({g["scenario_id"] for g in GOLD}) == 10


def test_tools_never_touch_ground_truth():
    src = (ROOT / "tools_core.py").read_text() + (ROOT / "tools.py").read_text() + (ROOT / "mcp_server.py").read_text()
    assert "golden" not in src.lower()


@pytest.mark.parametrize("g", GOLD, ids=lambda g: g["scenario_id"])
def test_alarm_verdict_matches_ground_truth(g):
    b = SimBackend(g["scenario_id"])
    assert b.check_guardband_and_cal(g["alarm_tag"])["verdict"] == g["expected_verdict"]


def test_every_limit_carries_a_source_and_semi_limits_are_tagged():
    b = SimBackend("S01")
    for s in b.sensors.values():
        assert s.limit_source
        if "SEMI" in s.limit_source:
            assert "to be verified against the standard" in s.limit_source


def test_tool_errors_are_returned_not_raised():
    b = SimBackend("S01")
    assert "error" in b.query_sensor_window("NOPE")
    assert "error" in b.trace_upstream_loop("NOPE")
    assert "error" in b.get_resin_and_lamp_runtime("RO_A_NOT_THERE")
    assert set(TOOL_NAMES) == {n for n in dir(b) if n in TOOL_NAMES}


def test_upstream_trace_and_work_orders():
    b = SimBackend("S03")
    ups = [u["asset_id"] for u in b.trace_upstream_loop("POU_ETCH_1")["upstream"]]
    assert ups[0] == "VALVE_B_07" and "RO_B" in ups
    wo = b.get_recent_work_orders("VALVE_B_07", 72)
    assert wo["count"] == 1 and wo["work_orders"][0]["hours_ago"] == 2


def test_data_generation_is_deterministic(tmp_path):
    from simulator import build_all
    build_all(tmp_path)
    assert (tmp_path / "synthetic_scada.csv").read_bytes() == (DATA_DIR / "synthetic_scada.csv").read_bytes()
