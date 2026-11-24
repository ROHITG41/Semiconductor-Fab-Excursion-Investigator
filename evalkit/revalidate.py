"""revalidate.py - free check: apply the CURRENT validator and evidence-quality rules to runs already saved on disk.
Shows which earlier 'passed' runs would now be rejected or flagged, without any new model calls."""
from __future__ import annotations

from pathlib import Path

from engine import evidence_quality, evidence_quality_notes
from evalkit.batch import load_results
from validator import validate_report


def revalidate(outdir: Path, labels: list[str]) -> dict:
    out = {}
    for label in labels:
        ok, _ = load_results(outdir, label)
        rows = []
        for r in ok:
            run = r["run"]
            now = (validate_report(run.report, run.evidence, run.triage, run.alarm) if run.report
                   else None)
            rows.append({"key": r["key"], "was_ok": bool(run.validation.ok), "now_ok": bool(now.ok) if now else False,
                         "new_violations": [] if (now is None or now.ok) else now.violations,
                         "flags_now": evidence_quality(run.evidence), "notes_now": evidence_quality_notes(run.evidence)})
        out[label] = {"runs": len(rows),
                      "newly_failing": [r for r in rows if r["was_ok"] and not r["now_ok"]],
                      "newly_flagged": [r["key"] for r in rows if r["flags_now"] and not r["key"].startswith("S13")],
                      "with_notes": [r["key"] for r in rows if r["notes_now"]]}
    return out
