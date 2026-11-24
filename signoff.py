"""signoff.py - the human decision gate. The AI proposes; deterministic code decided the verdict; a human signs here.

Rules enforced in code:
  * a name and a role from the allowed list are required (demo: typed, not authenticated);
  * the audit chain must verify before anything is appended;
  * APPROVE needs a report that passed the numeric-consistency validator (a flagged draft can only be rejected
    or sent back for more evidence);
  * one final decision per run; APPROVE then writes the case into episodic memory.
"""
from __future__ import annotations

from audit import ACTIONS, FINAL, ROLES, AuditChain, run_digest, verify_entries
from memory import EpisodicMemory


class SignoffError(ValueError):
    pass


def decide(run, action: str, actor: str, role: str, comment: str, chain: AuditChain, key: str,
           memory: EpisodicMemory | None = None, acknowledged_flags: bool = False) -> dict:
    if action not in ACTIONS:
        raise SignoffError(f"unknown action {action}")
    if not actor.strip():
        raise SignoffError("reviewer name is required")
    if role not in ROLES:
        raise SignoffError("choose a reviewer role from the list")
    ok, problems = verify_entries(chain.entries(), key)
    if not ok:
        raise SignoffError(f"audit chain does not verify, refusing to append: {problems[0]}")
    if chain.final_decision(run.run_id):
        raise SignoffError("this run already has a final decision")
    if action == "APPROVE":
        if run.report is None or not run.validation.ok:
            raise SignoffError("cannot approve: the draft failed the numeric-consistency check. Reject it or request more evidence.")
    if action == "APPROVE" and run.quality_flags:
        if not acknowledged_flags:
            raise SignoffError("this run has evidence-quality flags: tick the acknowledgement box to confirm you read them, "
                               "or reject / request more evidence.")
        comment = f"{comment} [reviewer acknowledged {len(run.quality_flags)} evidence-quality flag(s)]".strip()
    entry = chain.append(key, run_id=run.run_id, digest=run_digest(run), action=action, actor=actor, role=role, comment=comment)
    stored = False
    if action == "APPROVE":
        (memory or EpisodicMemory()).remember_approved(run, chain, key)
        stored = True
    return {"entry": entry, "memory_stored": stored}


def status_of(run, chain: AuditChain) -> str:
    final = chain.final_decision(run.run_id)
    if final:
        return "SIGNED_APPROVED" if final["action"] == "APPROVE" else "SIGNED_REJECTED"
    if any(e["action"] == "REQUEST_MORE_EVIDENCE" for e in chain.entries_for(run.run_id)):
        return "MORE_EVIDENCE_REQUESTED"
    return run.status
