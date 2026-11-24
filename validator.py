"""validator.py - numeric-consistency firewall for LLM-drafted reports.

Rules (all deterministic):
  * every numeric literal in narrative/actions must match a number found in the tool evidence
    (or the alarm) within the precision written;
  * every cited evidence id must exist;
  * wording must not contradict the code-computed verdict;
  * hypotheses must include the stated root cause.
"""
from __future__ import annotations

import re
from typing import Iterable

from schemas import EvidenceItem, InvestigationReport, ValidationResult

NUM_RX = re.compile(r"(?<![A-Za-z0-9_.\-])-?\d+(?:,\d{3})*(?:\.\d+)?(?![A-Za-z0-9_])")
CONTRA_FOR_FAIL = re.compile(r"\b(within (the )?(sem[i]? )?(limits?|spec)|meets? (the )?(limit|spec)|compliant|no excursion|in spec)\b", re.I)
ACTION_LINT = re.compile(r"\b(immediately|shut ?down|release (the )?lot|override|ignore (the )?alarm|approve (the )?lot|no further action)\b", re.I)
CONTRA_FOR_PASS = re.compile(r"\b(exceeds?|exceeded|out of spec|excursion confirmed|violat\w+)\b", re.I)


def _flatten(obj, out: list[float]) -> None:
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        out.append(float(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            _flatten(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _flatten(v, out)
    elif isinstance(obj, str):
        for m in NUM_RX.findall(obj):
            try:
                out.append(float(m.replace(",", "")))
            except ValueError:
                pass


def allowed_numbers(evidence: Iterable[EvidenceItem], extra: Iterable[dict] = ()) -> list[float]:
    nums: list[float] = []
    for e in evidence:
        _flatten(e.output, nums)
        _flatten(e.args, nums)
    for x in extra:
        _flatten(x, nums)
    return nums


def _decimals(s: str) -> int:
    return len(s.split(".")[1]) if "." in s else 0


def numbers_in(text: str) -> list[str]:
    return NUM_RX.findall(text or "")


def number_supported(token: str, allowed: list[float]) -> bool:
    val = float(token.replace(",", ""))
    d = _decimals(token)
    tol = 0.5 * 10 ** (-d) + 1e-9
    return any(abs(val - a) <= tol for a in allowed)


NON_DATA_TOOLS = {"search_knowledge_base", "find_similar_past_cases"}


def _has_data_evidence(ids, by_id) -> bool:
    """True if at least one cited item is a successful sensor / asset / work-order / runtime result."""
    return any(i in by_id and by_id[i].tool not in NON_DATA_TOOLS and "error" not in by_id[i].output for i in ids)


def validate_report(report: InvestigationReport, evidence: list[EvidenceItem], triage: dict,
                    alarm: dict | None = None) -> ValidationResult:
    v: list[str] = []
    allowed = allowed_numbers(evidence, [triage, alarm or {}])
    texts = [("narrative", report.narrative)] + [(f"action {i+1}", a) for i, a in enumerate(report.recommended_actions)]
    for where, text in texts:
        for tok in numbers_in(text):
            if not number_supported(tok, allowed):
                v.append(f"number {tok} in {where} is not found in any tool output")
    ids = {e.id for e in evidence}
    cited = list(report.supporting_evidence_ids) + [i for h in report.hypotheses for i in h.evidence_ids]
    for i in cited:
        if i not in ids:
            v.append(f"cited evidence id {i} does not exist")
    if report.root_cause_code not in {h.code for h in report.hypotheses}:
        v.append("root cause is not among the assessed hypotheses")
    by_id = {e.id: e for e in evidence}
    if report.root_cause_code.value != "NO_CONFIRMED_EXCURSION" and not any(
            h.code == report.root_cause_code and h.status == "supported" for h in report.hypotheses):
        v.append(f"root cause {report.root_cause_code.value} is not marked 'supported' in the hypotheses; "
                 "name as root cause only a hypothesis that the sensor, asset, work-order or runtime evidence supports")
    for h in report.hypotheses:
        if h.status in ("supported", "ruled_out") and not _has_data_evidence(h.evidence_ids, by_id):
            v.append(f"hypothesis {h.code.value} is marked {h.status} without any sensor, asset, work-order or runtime "
                     "evidence (knowledge-base text and past cases cannot support or rule out a cause)")
    if not _has_data_evidence(report.supporting_evidence_ids, by_id):
        v.append("supporting evidence contains no successful sensor, asset, work-order or runtime result")
    kb_ids = {r.get("chunk_id") for e in evidence if e.tool == "search_knowledge_base" for r in e.output.get("results", [])}
    for cid in report.knowledge_base_citations:
        if cid not in kb_ids:
            v.append(f"knowledge-base citation {cid} was not returned by any search")
    for i, a in enumerate(report.recommended_actions, 1):
        if ACTION_LINT.search(a):
            v.append(f"action {i} uses directive wording; phrase it as a recommendation for qualified engineer review")
    verdict = triage.get("verdict")
    body = report.narrative
    if verdict == "FAIL" and CONTRA_FOR_FAIL.search(body):
        v.append("narrative says the reading is within limits but the deterministic verdict is FAIL")
    if verdict == "PASS" and CONTRA_FOR_PASS.search(body):
        v.append("narrative reports an excursion but the deterministic verdict is PASS")
    return ValidationResult(ok=not v, violations=v)
