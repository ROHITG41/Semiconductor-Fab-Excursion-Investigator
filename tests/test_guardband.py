import math
from datetime import date

from guardband import assess, calibration_status, classify
from schemas import SensorSpec, Verdict


def test_lower_limit_three_states():
    assert classify("lower", 18.20, 18.20, 0.05) == Verdict.PASS
    assert classify("lower", 18.19, 18.20, 0.05) == Verdict.INDETERMINATE
    assert classify("lower", 18.15, 18.20, 0.05) == Verdict.INDETERMINATE   # exactly on the band edge
    assert classify("lower", 18.14, 18.20, 0.05) == Verdict.FAIL


def test_upper_limit_three_states():
    assert classify("upper", 1.0, 1.0, 0.1) == Verdict.PASS
    assert classify("upper", 1.05, 1.0, 0.1) == Verdict.INDETERMINATE
    assert classify("upper", 1.1, 1.0, 0.1) == Verdict.INDETERMINATE
    assert classify("upper", 1.11, 1.0, 0.1) == Verdict.FAIL


def test_bad_inputs_are_indeterminate_never_pass():
    assert classify("upper", None, 1.0, 0.1) == Verdict.INDETERMINATE
    assert classify("upper", math.nan, 1.0, 0.1) == Verdict.INDETERMINATE
    assert classify("upper", 2.0, 1.0, None) == Verdict.INDETERMINATE
    assert classify("sideways", 2.0, 1.0, 0.1) == Verdict.INDETERMINATE


def _spec(due="2026-09-30"):
    return SensorSpec(tag="T", parameter="p", unit="ppb", asset_id="A", direction="upper", limit=1.0,
                      half_width=0.1, limit_source="x", last_cal="2026-01-01", cal_due=due)


def test_expired_calibration_forces_indeterminate_even_for_fail_reading():
    a = assess(_spec(due="2026-02-15"), 3.0, date(2026, 3, 10))
    assert a["reading_verdict"] == "FAIL" and a["verdict"] == "INDETERMINATE" and not a["calibration_valid"]


def test_valid_calibration_keeps_reading_verdict():
    a = assess(_spec(), 3.0, date(2026, 3, 10))
    assert a["verdict"] == "FAIL" and a["margin"] == -2.0


def test_calibration_edge_cases():
    assert calibration_status(None, "2026-01-01", date(2026, 3, 1))[0] is False
    assert calibration_status("bad", None, date(2026, 3, 1))[0] is False
    assert calibration_status("2026-03-01", "2026-01-01", date(2026, 3, 1))[0] is True
