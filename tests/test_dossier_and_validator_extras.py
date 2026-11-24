import subprocess
from pathlib import Path

import pytest

from audit import AuditChain, run_digest
from dossier import build_dossier
from engine import run_scripted_offline
from schemas import InvestigationReport
from validator import validate_report


def _text(pdf_bytes, tmp_path):
    p = tmp_path / "d.pdf"; p.write_bytes(pdf_bytes)
    try:
        out = subprocess.run(["pdftotext", str(p), "-"], capture_output=True, text=True, check=True).stdout
        return " ".join(out.split())          # collapse line wraps
    except (FileNotFoundError, subprocess.CalledProcessError):
        pytest.skip("pdftotext not available")


@pytest.mark.parametrize("sid", [f"S{i:02d}" for i in range(1, 11)])
def test_every_scenario_renders_a_pdf(sid):
    b = build_dossier(run_scripted_offline(sid))
    assert b[:4] == b"%PDF" and len(b) > 3000


def test_unsigned_vs_signed_labels(tmp_path):
    run = run_scripted_offline("S01")
    assert "awaiting human review" in _text(build_dossier(run), tmp_path)
    chain = AuditChain(tmp_path / "c.jsonl")
    e = chain.append("k" * 32, run_id=run.run_id, digest=run_digest(run), action="APPROVE", actor="A. Rao",
                     role="QA engineer", comment="checked")
    t = _text(build_dossier(run, e, chain.head(), True), tmp_path)
    assert "APPROVED by A. Rao" in t and "YES" in t and e["hmac"][:20] in t.replace(" ", "")


def test_record_changed_after_signing_is_shown(tmp_path):
    run = run_scripted_offline("S01")
    chain = AuditChain(tmp_path / "c.jsonl")
    e = chain.append("k" * 32, run_id=run.run_id, digest=run_digest(run), action="APPROVE", actor="A", role="QA engineer")
    changed = run.model_copy(update={"hold_advisory": "edited"})
    assert "NO - record changed" in _text(build_dossier(changed, e), tmp_path)


def test_injection_text_in_notes_does_not_break_the_pdf(tmp_path):
    run = run_scripted_offline("S07")
    assert run.notes_scan["blocked"]
    assert "withheld from the AI" in _text(build_dossier(run), tmp_path)


def test_directive_wording_and_bad_citations_are_flagged():
    r = run_scripted_offline("S01")
    d = r.report.model_dump()
    d["recommended_actions"] = ["Replace the lamp immediately."]
    d["knowledge_base_citations"] = ["ZZZ-99"]
    res = validate_report(InvestigationReport.model_validate(d), r.evidence, r.triage, r.alarm)
    assert any("directive wording" in v for v in res.violations) and any("ZZZ-99" in v for v in res.violations)


def test_scripted_report_cites_only_retrieved_chunks():
    r = run_scripted_offline("S01")
    assert r.report.knowledge_base_citations and r.validation.ok
