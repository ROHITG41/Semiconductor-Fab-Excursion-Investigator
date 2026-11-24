"""Hard tier (S11-S14): check the ground truth is defensible from the evidence the tools return, that the rules
engine was NOT tuned to them, and that the scorer and report handle the tier."""
import json

import pytest

from engine import rules_diagnose, run_scripted_offline
from evalkit.__main__ import expand_scenarios
from evalkit.batch import run_batch
from evalkit.budget import CallBudget
from evalkit.scorer import load_golden, score_run
from evalkit.summarise import aggregate, check_targets, TARGETS_PATH
from tools_core import SimBackend

GOLD = load_golden()
HARD = ["S11", "S12", "S13", "S14"]


def test_hard_tier_defined_with_reasons():
    assert [s for s, g in GOLD.items() if g.get("tier") == "hard"] == HARD
    assert all(GOLD[s]["why"] for s in HARD)
    assert len(expand_scenarios("core")) == 10 and expand_scenarios("hard") == HARD and len(expand_scenarios("all")) == 14
    assert expand_scenarios("S01, S05") == ["S01", "S05"]


@pytest.mark.parametrize("sid", HARD)
def test_code_verdict_matches_ground_truth(sid):
    b = SimBackend(sid)
    assert b.check_guardband_and_cal(b.alarm["tag"])["verdict"] == GOLD[sid]["expected_verdict"]


def test_s11_evidence_separates_resin_from_membrane():
    b = SimBackend("S11")
    assert b.get_resin_and_lamp_runtime("RO_A")["percent_of_rated_life"] >= 100
    assert b.get_resin_and_lamp_runtime("POLISH_A")["percent_of_rated_life"] >= 100       # both consumables are past rated life
    ro = b.query_sensor_window("UPW_A_COND_RO", 120)
    assert ro["last"] < 1.5 and ro["max"] < 3.0                                            # RO permeate is healthy: not the membrane
    assert any("chemical clean" in w["text"] for w in b.get_recent_work_orders("", 200)["work_orders"])


def test_s12_upstream_is_clean_so_the_analyzer_is_suspect():
    b = SimBackend("S12")
    tri = b.check_guardband_and_cal("UPW_A_TOC_POU")
    assert tri["calibration_valid"] and tri["verdict"] == "FAIL"
    assert b.query_sensor_window("UPW_A_TOC_EDI", 120)["last"] < 1.0
    assert b.query_sensor_window("UPW_A_UV_INT", 120)["last"] > 90
    assert b.get_resin_and_lamp_runtime("UV_A")["percent_of_rated_life"] < 90


def test_s13_runtime_tool_is_down_but_other_evidence_points_to_lamp():
    b = SimBackend("S13")
    assert "error" in b.get_resin_and_lamp_runtime("UV_B")
    uv = b.query_sensor_window("UPW_B_UV_INT", 120)
    assert uv["last"] < uv["first"] - 10
    assert b.query_sensor_window("UPW_B_TOC_EDI", 120)["last"] > 1.5
    r = run_scripted_offline("S13")
    assert r.quality_flags and any("runtime" in f.lower() for f in r.quality_flags)
    assert score_run(r, GOLD["S13"])["flag_ok"] is True


def test_s14_only_do_rose_and_valve_was_replaced_hours_earlier():
    b = SimBackend("S14")
    wos = b.get_recent_work_orders("", 72)["work_orders"]
    assert [(w["asset"], w["hours_ago"]) for w in wos] == [("VALVE_B_07", 9)]
    assert b.query_sensor_window("UPW_B_TOC_EDI", 120)["last"] < 1.0
    assert b.get_resin_and_lamp_runtime("UV_B")["percent_of_rated_life"] < 90


def test_rules_engine_was_not_tuned_to_the_hard_tier():
    """Pinned on purpose. If you change engine.rules_diagnose, re-run the rules baseline and re-label old results."""
    got = {sid: run_scripted_offline(sid).report.root_cause_code.value for sid in HARD}
    assert got == {"S11": "RO_MEMBRANE_DEGRADATION", "S12": "NO_CONFIRMED_EXCURSION",
                   "S13": "NO_CONFIRMED_EXCURSION", "S14": "NO_CONFIRMED_EXCURSION"}


def test_flag_expectation_only_applies_where_declared():
    assert score_run(run_scripted_offline("S11"), GOLD["S11"])["flag_ok"] is None


def test_report_splits_tiers_and_applies_hard_targets(tmp_path):
    items = [(f"{s}_run1", (lambda s=s: run_scripted_offline(s))) for s in ["S01", "S07", "S11", "S13"]]
    run_batch("agent_live", items, tmp_path, CallBudget(1), log=lambda *_: None)
    agg = aggregate(tmp_path, "agent_live")
    assert set(agg["by_tier"]) == {"core", "hard"}
    assert agg["by_tier"]["core"]["cause_ok"] == 2 and agg["by_tier"]["hard"]["cause_ok"] == 0
    res = {r["name"]: r["result"] for r in check_targets(agg, json.loads(TARGETS_PATH.read_text()))}
    assert res["Root cause correct"] == "PASS"                    # core judged on core only
    assert res["HARD tier: root cause correct"] == "MISS"
    assert res["HARD tier: flag raised when a tool was down"] == "PASS"
