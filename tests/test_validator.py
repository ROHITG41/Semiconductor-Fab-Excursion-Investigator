from engine import run_scripted_offline
from schemas import FaultCode, HypothesisAssessment, InvestigationReport
from validator import number_supported, validate_report


def _run():
    return run_scripted_offline("S01")


def _with(report, **kw):
    d = report.model_dump(); d.update(kw)
    return InvestigationReport.model_validate(d)


def test_scripted_report_is_consistent():
    r = _run()
    assert r.validation.ok, r.validation.violations


def test_invented_number_is_caught():
    r = _run()
    bad = _with(r.report, narrative=r.report.narrative + " The lamp had 12345 hours of use.")
    res = validate_report(bad, r.evidence, r.triage, r.alarm)
    assert not res.ok and any("12345" in v for v in res.violations)


def test_missing_evidence_id_is_caught():
    r = _run()
    res = validate_report(_with(r.report, supporting_evidence_ids=["E99"]), r.evidence, r.triage, r.alarm)
    assert any("E99" in v for v in res.violations)


def test_verdict_contradiction_is_caught():
    r = _run()
    bad = _with(r.report, narrative="The reading is within limits and compliant, so no action is needed at all.")
    res = validate_report(bad, r.evidence, r.triage, r.alarm)
    assert any("FAIL" in v for v in res.violations)


def test_root_cause_must_be_among_hypotheses():
    r = _run()
    h = [HypothesisAssessment(code=FaultCode.SENSOR_DRIFT, status="unresolved", evidence_ids=["E1"])]
    res = validate_report(_with(r.report, hypotheses=[x.model_dump() for x in h]), r.evidence, r.triage, r.alarm)
    assert any("hypotheses" in v for v in res.violations)


def test_number_precision_rules():
    assert number_supported("3.83", [3.8326])
    assert not number_supported("3.9", [3.8326])
    assert number_supported("8,420", [8420.0])
