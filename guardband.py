"""guardband.py - deterministic simple-acceptance guard-band verdicts (no third-party deps).

Rule: meets the nominal limit -> PASS; fails nominal but is inside the instrument
uncertainty band -> INDETERMINATE; beyond the band -> FAIL. Unknown/NaN input -> INDETERMINATE.
Calibration: expired or missing -> the reading cannot be trusted -> INDETERMINATE overall.
"""
from __future__ import annotations

import math
from datetime import date
from typing import Optional

from schemas import SensorSpec, Verdict

ROUND = 6


def _ok(*xs) -> bool:
    return all(x is not None and isinstance(x, (int, float)) and math.isfinite(x) for x in xs)


def classify(direction: str, measured: Optional[float], limit: float, half_width: Optional[float]) -> Verdict:
    if not _ok(measured, limit):
        return Verdict.INDETERMINATE
    m, lim = round(float(measured), ROUND), round(float(limit), ROUND)
    if direction == "lower":
        if m >= lim:
            return Verdict.PASS
        edge = round(lim - (half_width or 0), ROUND)
        if half_width is None or not _ok(half_width) or half_width < 0:
            return Verdict.INDETERMINATE
        return Verdict.INDETERMINATE if m >= edge else Verdict.FAIL
    if direction == "upper":
        if m <= lim:
            return Verdict.PASS
        if half_width is None or not _ok(half_width) or half_width < 0:
            return Verdict.INDETERMINATE
        edge = round(lim + half_width, ROUND)
        return Verdict.INDETERMINATE if m <= edge else Verdict.FAIL
    return Verdict.INDETERMINATE


def calibration_status(cal_due: Optional[str], last_cal: Optional[str], on: date) -> tuple[bool, str]:
    """Return (valid, reason) for an instrument on a given date."""
    try:
        due = date.fromisoformat(cal_due) if cal_due else None
        last = date.fromisoformat(last_cal) if last_cal else None
    except ValueError:
        return False, "calibration dates unreadable"
    if due is None:
        return False, "calibration due date missing"
    if due < on:
        return False, f"calibration expired {due.isoformat()}"
    if last is not None and last > on:
        return False, "last calibration date is after the event; verify record"
    return True, "calibration valid"


def assess(spec: SensorSpec, measured: Optional[float], on: date) -> dict:
    """Full deterministic assessment of one reading. This is the ONLY source of verdicts."""
    reading_verdict = classify(spec.direction, measured, spec.limit, spec.half_width)
    cal_ok, cal_reason = calibration_status(spec.cal_due, spec.last_cal, on)
    verdict = reading_verdict if cal_ok else Verdict.INDETERMINATE
    if spec.direction == "lower":
        band_lo, band_hi = round(spec.limit - spec.half_width, ROUND), round(spec.limit, ROUND)
        margin = None if not _ok(measured) else round(measured - spec.limit, ROUND)
    else:
        band_lo, band_hi = round(spec.limit, ROUND), round(spec.limit + spec.half_width, ROUND)
        margin = None if not _ok(measured) else round(spec.limit - measured, ROUND)
    return {
        "tag": spec.tag, "parameter": spec.parameter, "unit": spec.unit,
        "measured": measured, "limit": spec.limit, "direction": spec.direction,
        "uncertainty_half_width": spec.half_width,
        "band_lower": band_lo, "band_upper": band_hi, "margin": margin,
        "reading_verdict": reading_verdict.value,
        "calibration_valid": cal_ok, "calibration_note": cal_reason,
        "verdict": verdict.value, "limit_source": spec.limit_source,
    }
