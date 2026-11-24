"""baselines.py - what the agent is compared against.

rules   : the hand-written rules engine (run_scripted_offline). I wrote it AND the synthetic scenarios, so it is a
          reference ceiling for this synthetic data, NOT an independent competitor. On real, messy data it would not
          score like this. If the agent matches it, that says the agent can reach the same answers; it does not say
          the agent is better.
oneshot : the same fixed tool plan runs without any AI choosing tools, then ONE model call writes the report
          (same prompt, same validator, no retry). Tells you whether letting the model pick tools adds anything.
"""
from __future__ import annotations

from config import DATA_DIR, MAX_AGENT_STEPS
from engine import (add_evidence, assemble, backend_assets, execute_tool, next_tool_calls, run_ingress,
                    run_scripted_offline, run_triage)
from prompts import build_draft_prompt
from schemas import EvidenceItem, InvestigationReport
from tools_core import SimBackend


def run_rules(scenario_id: str, data_dir=DATA_DIR, notes_override=None):
    return run_scripted_offline(scenario_id, data_dir, notes_override)


def run_oneshot(scenario_id: str, llm, models: dict, data_dir=DATA_DIR, notes_override=None, mode="live-gemini"):
    b = SimBackend(scenario_id, data_dir, notes_override=notes_override)
    scan, triage = run_ingress(b), run_triage(b)
    evidence: list[EvidenceItem] = []
    assets, rounds = backend_assets(b), 0
    while rounds < MAX_AGENT_STEPS:
        calls = next_tool_calls(b.alarm["tag"], assets, evidence)
        if not calls:
            break
        rounds += 1
        for name, args in calls:
            add_evidence(evidence, name, args, execute_tool(b, name, args))
    prompt = build_draft_prompt(triage, [e.model_dump() for e in evidence], scan["for_llm"])
    report = None
    try:
        out = llm.with_structured_output(InvestigationReport).invoke(prompt)
        report = out if isinstance(out, InvestigationReport) else InvestigationReport.model_validate(out)
    except Exception:   # noqa: BLE001 - one-shot has no fallback: a failed draft is a failed run
        report = None
    return assemble(b, mode, models, scan, triage, evidence, report, rounds)
