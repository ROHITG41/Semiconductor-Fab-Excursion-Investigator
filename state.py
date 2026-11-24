"""state.py - LangGraph state (extends MessagesState)."""
from __future__ import annotations

from typing import Optional

from langgraph.graph import MessagesState


class SentryState(MessagesState):
    scenario_id: str
    notes_scan: dict
    triage: dict
    evidence: list            # list[dict] (EvidenceItem dumps)
    seen: int                 # messages already converted to evidence
    step_count: int           # agent rounds that requested tools
    report: Optional[dict]
    validation: Optional[dict]
    draft_retries: int
    feedback: str
