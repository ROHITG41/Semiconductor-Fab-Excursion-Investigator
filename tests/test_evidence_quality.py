import pytest

from audit import AuditChain
from engine import evidence_quality, evidence_quality_notes, run_scripted_offline
from memory import EpisodicMemory
from schemas import EvidenceItem, InvestigationReport
from signoff import SignoffError, decide
from tools_core import SimBackend
from validator import validate_report

KEY = "k" * 32


def _with_hyp(run, code, status, ids):
    d = run.report.model_dump(mode="json")
    d["hypotheses"] = d["hypotheses"] + [dict(code=code, status=status, evidence_ids=ids)]
    return InvestigationReport.model_validate(d)


def test_kb_only_evidence_cannot_rule_out_or_support_a_cause():
    r = run_scripted_offline("S01")
    kb = next(e.id for e in r.evidence if e.tool == "search_knowledge_base")
    res = validate_report(_with_hyp(r, "RESIN_EXHAUSTION", "ruled_out", [kb]), r.evidence, r.triage, r.alarm)
    assert any("RESIN_EXHAUSTION" in v and "without any sensor" in v for v in res.violations)
    data = next(e.id for e in r.evidence if e.tool == "get_resin_and_lamp_runtime")
    ok = validate_report(_with_hyp(r, "RESIN_EXHAUSTION", "ruled_out", [data]), r.evidence, r.triage, r.alarm)
    assert ok.ok, ok.violations
    unresolved = validate_report(_with_hyp(r, "RESIN_EXHAUSTION", "unresolved", [kb]), r.evidence, r.triage, r.alarm)
    assert unresolved.ok


def test_errored_evidence_does_not_count_as_data():
    r = run_scripted_offline("S01")
    ev = [EvidenceItem(id="E1", tool="trace_upstream_loop", args={}, output={"error": "unknown asset X"})]
    rep = r.report.model_copy(update={"supporting_evidence_ids": ["E1"],
                                      "hypotheses": [r.report.hypotheses[0].model_copy(update={"evidence_ids": ["E1"]})],
                                      "knowledge_base_citations": []})
    res = validate_report(rep, ev, r.triage, r.alarm)
    assert any("no successful sensor" in v for v in res.violations)


def test_flags_empty_for_a_clean_run_and_present_for_a_poor_one():
    assert run_scripted_offline("S01").quality_flags == []
    poor = [EvidenceItem(id="E1", tool="trace_upstream_loop", args={}, output={"error": "unknown asset UPW_LOOP_B"}),
            EvidenceItem(id="E2", tool="check_guardband_and_cal", args={}, output={"verdict": "FAIL"})]
    flags = evidence_quality(poor)
    assert any("1 of 2 tool calls returned errors" in f for f in flags)
    assert any("No upstream trace" in f for f in flags) and any("runtime" in f for f in flags)


def test_unknown_asset_errors_list_known_assets_so_the_agent_can_recover():
    b = SimBackend("S01")
    for out in (b.trace_upstream_loop("UPW_LOOP_B"), b.get_asset_dependencies("UPW_B_TOC_POU"),
                b.get_recent_work_orders("UPW_B_TOC_POU", 24)):
        assert "error" in out and "POU_ETCH_1" in out["known_assets"] and "hint" in out
    assert "error" not in b.get_recent_work_orders("", 72)


def test_approving_a_flagged_run_needs_acknowledgement(tmp_path):
    chain, mem = AuditChain(tmp_path / "c.jsonl"), EpisodicMemory(tmp_path / "m.db")
    run = run_scripted_offline("S01").model_copy(update={"quality_flags": ["1 of 5 tool calls returned errors (E4)."]})
    with pytest.raises(SignoffError):
        decide(run, "APPROVE", "A. Rao", "QA engineer", "ok", chain, KEY, mem)
    assert chain.entries() == [] and mem.count() == 0
    out = decide(run, "APPROVE", "A. Rao", "QA engineer", "ok", chain, KEY, mem, acknowledged_flags=True)
    assert "acknowledged 1 evidence-quality flag" in out["entry"]["comment"] and mem.count() == 1
    assert decide(run.model_copy(update={"run_id": "other"}), "REJECT", "A. Rao", "QA engineer", "", chain, KEY, mem)


def test_dossier_lists_flags(tmp_path):
    import subprocess
    from dossier import build_dossier
    run = run_scripted_offline("S01").model_copy(update={"quality_flags": ["No upstream trace succeeded."]})
    p = tmp_path / "d.pdf"; p.write_bytes(build_dossier(run))
    try:
        text = " ".join(subprocess.run(["pdftotext", str(p), "-"], capture_output=True, text=True, check=True).stdout.split())
    except (FileNotFoundError, subprocess.CalledProcessError):
        pytest.skip("pdftotext not available")
    assert "Evidence-quality flags" in text and "No upstream trace succeeded" in text


def test_step_limit_is_flagged_and_rounds_are_capped():
    import config
    from engine import assemble
    run = run_scripted_offline("S01")
    b = SimBackend("S01")
    r = assemble(b, "scripted-offline", {}, run.notes_scan, run.triage, run.evidence, run.report, config.MAX_AGENT_STEPS + 1)
    assert r.tool_rounds == config.MAX_AGENT_STEPS
    assert any("step limit" in f for f in r.quality_flags)
    ok = assemble(b, "scripted-offline", {}, run.notes_scan, run.triage, run.evidence, run.report, 4)
    assert ok.tool_rounds == 4 and not any("step limit" in f for f in ok.quality_flags)


def _ev2(i, tool, args, out):
    return EvidenceItem(id=f"E{i}", tool=tool, args=args, output=out)


def test_note_when_upstream_sensors_exist_but_none_were_read():
    trace = {"asset_id": "POU_LITHO_1", "upstream": [{"asset_id": "UV_A", "sensor_tags": ["UPW_A_UV_INT"]}]}
    base = [_ev2(1, "query_sensor_window", {"tag": "UPW_A_TOC_POU"}, {"last": 1.4}),
            _ev2(2, "trace_upstream_loop", {"asset_id": "POU_LITHO_1"}, trace),
            _ev2(3, "get_recent_work_orders", {}, {"work_orders": []}),
            _ev2(4, "get_resin_and_lamp_runtime", {"asset_id": "UV_A"}, {"hours": 1})]
    assert any("No upstream sensor trend" in n for n in evidence_quality_notes(base))
    assert not evidence_quality(base)                       # informational note only: no acknowledgement needed
    with_up = base + [_ev2(5, "query_sensor_window", {"tag": "UPW_A_UV_INT"}, {"last": 95.0})]
    assert not any("No upstream sensor trend" in n for n in evidence_quality_notes(with_up))
    failed_up = base + [_ev2(5, "query_sensor_window", {"tag": "UPW_A_UV_INT"}, {"error": "x"})]
    assert any("No upstream sensor trend" in n for n in evidence_quality_notes(failed_up))


def test_root_cause_must_be_a_supported_hypothesis():
    r = run_scripted_offline("S01")
    assert r.validation.ok
    unresolved = [h.model_copy(update={"status": "unresolved"}) if h.code == r.report.root_cause_code else h
                  for h in r.report.hypotheses]
    bad = r.report.model_copy(update={"hypotheses": unresolved})
    res = validate_report(bad, r.evidence, r.triage, r.alarm)
    assert any("is not marked 'supported'" in v for v in res.violations)


def test_no_confirmed_excursion_is_exempt_from_the_supported_rule():
    r = run_scripted_offline("S09")
    assert r.report.root_cause_code.value == "NO_CONFIRMED_EXCURSION" and r.validation.ok
    hyps = [h.model_copy(update={"status": "unresolved"}) for h in r.report.hypotheses]
    res = validate_report(r.report.model_copy(update={"hypotheses": hyps}), r.evidence, r.triage, r.alarm)
    assert not any("is not marked 'supported'" in v for v in res.violations)


def test_revalidate_finds_a_saved_run_the_new_rule_rejects(tmp_path):
    from evalkit.batch import run_batch
    from evalkit.budget import CallBudget
    from evalkit.revalidate import revalidate

    def placeholder():
        r = run_scripted_offline("S01")
        hyps = [h.model_copy(update={"status": "unresolved"}) for h in r.report.hypotheses]
        return r.model_copy(update={"report": r.report.model_copy(update={"hypotheses": hyps})})   # saved with validation.ok = True
    run_batch("x", [("S01_run1", placeholder)], tmp_path, CallBudget(1), log=lambda *_: None)
    res = revalidate(tmp_path, ["x"])["x"]
    assert len(res["newly_failing"]) == 1
