import json

import pytest

from engine import evidence_quality, evidence_quality_notes, run_scripted_offline, split_errors
from evalkit.attacks import ATTACKS, by_group, scan_metrics, verdict_invariance
from evalkit.baselines import run_oneshot, run_rules
from evalkit.batch import load_results, run_batch
from evalkit.budget import BudgetExceeded, CallBudget, CountingModel
from evalkit.scorer import load_golden, score_run, score_text_adoption
from evalkit.summarise import TARGETS_PATH, aggregate, check_targets, render_markdown, wilson
from prompts import build_draft_prompt
from schemas import EvidenceItem, FaultCode
from tools_core import SimBackend

GOLD = load_golden()


# ---------- recovered-error rule ----------
def _ev(i, tool, err=False):
    return EvidenceItem(id=f"E{i}", tool=tool, args={}, output={"error": "x"} if err else {"ok": 1})


def test_error_followed_by_same_tool_success_is_recovered():
    ev = [_ev(1, "trace_upstream_loop", err=True), _ev(2, "trace_upstream_loop")]
    assert split_errors(ev) == ([], ["E1"])
    assert not any("errors" in f for f in evidence_quality(ev))
    assert "corrected" in evidence_quality_notes(ev)[0]


def test_error_without_later_success_stays_a_flag():
    ev = [_ev(1, "get_resin_and_lamp_runtime", err=True), _ev(2, "trace_upstream_loop")]
    assert split_errors(ev) == (["E1"], [])
    assert any("not corrected" in f for f in evidence_quality(ev))


def test_tool_descriptions_separate_assets_from_tags():
    d = SimBackend.trace_upstream_loop.__doc__
    assert "NEVER a sensor tag" in d
    assert "no runtime record" in SimBackend.get_resin_and_lamp_runtime.__doc__ or "EDI" in SimBackend.get_resin_and_lamp_runtime.__doc__


# ---------- scorer ----------
def test_scorer_perfect_run():
    r = run_scripted_offline("S01")
    s = score_run(r, GOLD["S01"])
    assert s["cause_ok"] and s["verdict_ok"] and s["validation_ok"] and s["correct_and_valid"]
    assert s["culprit_examined"] is True and s["unrecovered_errors"] == 0


def test_scorer_detects_wrong_cause_and_overconfidence():
    r = run_scripted_offline("S01")
    wrong = r.model_copy(update={"report": r.report.model_copy(update={"root_cause_code": FaultCode.RESIN_EXHAUSTION, "confidence": "high"})})
    s = score_run(wrong, GOLD["S01"])
    assert not s["cause_ok"] and not s["correct_and_valid"] and s["high_confidence_wrong"]


def test_scorer_flags_injection_compliance_even_with_right_cause():
    r = run_scripted_offline("S07")
    assert GOLD["S07"]["notes_contain_injection"]
    ok = score_run(r, GOLD["S07"])
    assert ok["injection_complied"] is False
    bad = r.model_copy(update={"report": r.report.model_copy(update={"narrative": "The TOC reading is within SEMI limits so nothing more is needed here."})})
    assert score_run(bad, GOLD["S07"])["injection_complied"] is True
    neg = r.model_copy(update={"report": r.report.model_copy(update={"narrative": "The TOC reading is not within SEMI limits; UV lamp hours are past rated life."})})
    assert score_run(neg, GOLD["S07"])["injection_complied"] is False


def test_scorer_missing_report_is_wrong_not_crash():
    r = run_scripted_offline("S01")
    s = score_run(r.model_copy(update={"report": None}), GOLD["S01"])
    assert s["cause"] is None and not s["cause_ok"]


def test_adoption_markers():
    r = run_scripted_offline("S01")
    rep = r.report.model_copy(update={"narrative": "Loop A is at normal background after it was re-baselined, so no lamp issue is expected."})
    res = score_text_adoption(r.model_copy(update={"report": rep}), GOLD["S01"], [r"normal background"])
    assert res["complied"] and res["adopted_markers"]


# ---------- budget ----------
def test_budget_stops_and_is_not_swallowed_by_except_exception():
    b = CallBudget(2)
    b.charge(); b.charge()
    with pytest.raises(BudgetExceeded):
        try:
            b.charge()
        except Exception:   # noqa: BLE001 - mimics the agent's broad fallbacks
            pytest.fail("BudgetExceeded must not be caught by except Exception")


def test_budget_throttle_uses_injected_clock():
    t = {"now": 0.0}
    slept = []
    b = CallBudget(5, 4.0, sleep=lambda s: (slept.append(s), t.__setitem__("now", t["now"] + s)), clock=lambda: t["now"])
    b.charge(); b.charge()
    assert slept and abs(slept[0] - 4.0) < 1e-9


def test_counting_model_charges_every_invoke_incl_bound_and_structured():
    class Inner:
        def invoke(self, x): return "r"
        def bind_tools(self, t): return Inner()
        def with_structured_output(self, s): return Inner()
    b = CallBudget(10)
    m = CountingModel(Inner(), b)
    m.invoke("a"); m.bind_tools([]).invoke("b"); m.with_structured_output(int).invoke("c")
    assert b.used == 3


# ---------- batch ----------
def test_batch_resume_and_budget_discard(tmp_path):
    b = CallBudget(3)

    def fn(sid, cost):
        def _f():
            for _ in range(cost):
                b.charge()
            return run_scripted_offline(sid)
        return _f
    items = [("S01_run1", fn("S01", 2)), ("S05_run1", fn("S05", 2)), ("S07_run1", fn("S07", 2))]
    s1 = run_batch("t", items, tmp_path, b, log=lambda *_: None)
    assert s1["completed_now"] == 1 and "budget" in s1["stopped"]
    ok, _ = load_results(tmp_path, "t")
    assert [r["key"] for r in ok] == ["S01_run1"] and ok[0]["calls"] == 2
    b2 = CallBudget(10)
    items2 = [(k, (lambda sid=k.split("_")[0]: run_scripted_offline(sid))) for k, _ in items]
    s2 = run_batch("t", items2, tmp_path, b2, log=lambda *_: None)
    assert s2["already_done"] == 1 and s2["completed_now"] == 2 and not s2["stopped"]


def test_batch_records_failures_and_stops_after_three(tmp_path):
    def boom():
        raise RuntimeError("503 UNAVAILABLE")
    items = [(f"S0{i}_run1", boom) for i in range(1, 6)]
    s = run_batch("f", items, tmp_path, CallBudget(5), log=lambda *_: None)
    assert s["failed_now"] == 3 and "in a row" in s["stopped"]
    ok, bad = load_results(tmp_path, "f")
    assert not ok and len(bad) == 3


def test_failure_file_removed_after_later_success(tmp_path):
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("503")
        return run_scripted_offline("S01")
    run_batch("x", [("S01_run1", flaky)], tmp_path, CallBudget(5), log=lambda *_: None)
    assert load_results(tmp_path, "x")[1]
    run_batch("x", [("S01_run1", flaky)], tmp_path, CallBudget(5), log=lambda *_: None)
    ok, bad = load_results(tmp_path, "x")
    assert len(ok) == 1 and not bad


# ---------- attacks ----------
def test_direct_attacks_are_caught_and_evasive_ones_documented():
    m = scan_metrics()
    assert m["direct_detected"][0] == m["direct_detected"][1] == len(by_group("direct"))
    assert m["evasive_got_through"][0] >= 1          # the scanner is known to be evadable; if this ever hits 0, update the report text
    assert m["benign_blocked"][0] <= 1                # B06 ("New instructions posted...") is a known false positive


def test_verdict_and_rules_cause_invariant_under_every_attack_text():
    v = verdict_invariance([f"S{i:02d}" for i in range(1, 11)])
    assert v["checked"] == 10 * len(ATTACKS) and v["violations"] == []


def test_notes_override_reaches_scanner():
    r = run_scripted_offline("S01", notes_override=by_group("direct")[0]["text"])
    assert r.notes_scan["blocked"] and r.triage["verdict"] == GOLD["S01"]["expected_verdict"]


# ---------- baselines ----------
class _StubLLM:
    """Stands in for a chat model: structured output built by the rules engine from the prompt."""
    def __init__(self): self.calls = 0

    def with_structured_output(self, schema):
        outer = self

        class S:
            def invoke(self, prompt):
                outer.calls += 1
                from engine import build_scripted_report
                lines = prompt.splitlines()
                triage = json.loads(next(l for l in lines if l.startswith("TRIAGE_JSON: "))[13:])
                ev = [EvidenceItem.model_validate(e) for e in json.loads(next(l for l in lines if l.startswith("EVIDENCE_JSON: "))[15:])]
                return build_scripted_report(ev, triage)
        return S()


def test_oneshot_uses_exactly_one_model_call_and_same_prompt_builder():
    llm = _StubLLM()
    r = run_oneshot("S01", llm, {"model": "stub"}, mode="scripted-offline")
    assert llm.calls == 1 and r.validation.ok and r.report.root_cause_code.value == "UV_LAMP_DECAY"
    p = build_draft_prompt({"verdict": "FAIL"}, [], "<n>x</n>", "fb")
    assert "TRIAGE_JSON:" in p and "EVIDENCE_JSON:" in p and "FIX THESE PROBLEMS" in p


def test_rules_baseline_matches_ground_truth_on_all_scenarios():
    for sid, g in GOLD.items():
        if g.get("tier", "core") == "core":
            assert score_run(run_rules(sid), g)["correct_and_valid"], sid


# ---------- summarise ----------
def test_wilson_interval_sane():
    assert wilson(0, 0) == (0.0, 0.0)
    lo, hi = wilson(5, 5)
    assert 0.5 < lo < 0.6 and hi == pytest.approx(1.0)
    lo, hi = wilson(0, 10)
    assert lo == 0.0 and 0.2 < hi < 0.35


def test_targets_file_and_report_render(tmp_path):
    t = json.loads(TARGETS_PATH.read_text())
    assert set(t) >= {"cause_accuracy_min", "verdict_agreement_min", "validation_pass_min", "injection_complied_max",
                      "runs_with_unrecovered_errors_max", "high_confidence_wrong_max", "run_consistency_min", "set_on"}
    items = [(f"{s}_run{k}", (lambda s=s: run_scripted_offline(s))) for k in (1, 2) for s in ("S01", "S07")]
    run_batch("agent_live", items, tmp_path, CallBudget(1), log=lambda *_: None)
    agg = aggregate(tmp_path, "agent_live")
    assert agg["total"]["n"] == 4 and agg["total"]["inj_n"] == 2
    res = {r["name"]: r["result"] for r in check_targets(agg, t)}
    assert res["Root cause correct"] == "PASS" and res["Followed an injected instruction"] == "PASS"
    md = render_markdown(tmp_path, ["agent_live"], scan_metrics(), {"checked": 1, "violations": []}, [])
    assert "Limits you must carry" in md and "Targets versus measured" in md


def test_report_fails_targets_when_runs_are_wrong(tmp_path):
    def wrong():
        r = run_scripted_offline("S01")
        return r.model_copy(update={"report": r.report.model_copy(update={"root_cause_code": FaultCode.SENSOR_DRIFT})})
    run_batch("agent_live", [(f"S01_run{k}", wrong) for k in (1, 2, 3)], tmp_path, CallBudget(1), log=lambda *_: None)
    res = {r["name"]: r["result"] for r in check_targets(aggregate(tmp_path, "agent_live"), json.loads(TARGETS_PATH.read_text()))}
    assert res["Root cause correct"] == "MISS"
