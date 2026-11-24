"""Runs the real LangGraph wiring with a scripted fake model. Skipped where langgraph is not installed."""
import json

import pytest

pytest.importorskip("langgraph")
pytest.importorskip("langchain_core")

from config import DATA_DIR  # noqa: E402
from runner import run_fake_graph  # noqa: E402

ALL_GOLD = json.loads((DATA_DIR / "golden_excursions.json").read_text())["scenarios"]
GOLD = [g for g in ALL_GOLD if g.get("tier", "core") == "core"]   # hard-tier scenarios are covered in test_hard_scenarios.py


@pytest.mark.parametrize("g", GOLD, ids=lambda g: g["scenario_id"])
def test_graph_runs_end_to_end(g):
    r = run_fake_graph(g["scenario_id"])
    assert r.validation.ok, r.validation.violations
    assert r.triage["verdict"] == g["expected_verdict"]
    assert r.report.root_cause_code.value == g["expected_root_cause"]
    assert r.tool_rounds == 4
