"""runner.py - run one investigation through the LangGraph app (live Gemini or scripted fake model)."""
from __future__ import annotations

import time

from config import DATA_DIR
from engine import assemble
from schemas import EvidenceItem, InvestigationReport, RunResult, ValidationResult
from tools_core import SimBackend


def run_graph(scenario_id: str, fast_llm, reasoning_llm, mode: str, models: dict, data_dir=None,
              notes_override=None) -> RunResult:
    from graph import build_graph
    backend = SimBackend(scenario_id, data_dir or DATA_DIR, notes_override=notes_override)
    graph = build_graph(backend, fast_llm, reasoning_llm)
    t0 = time.time()
    st = graph.invoke({"messages": [], "scenario_id": scenario_id}, config={"recursion_limit": 60})
    evidence = [EvidenceItem.model_validate(e) for e in st["evidence"]]
    report = InvestigationReport.model_validate(st["report"]) if st.get("report") else None
    validation = ValidationResult.model_validate(st["validation"]) if st.get("validation") else None
    res = assemble(backend, mode, models, st["notes_scan"], st["triage"], evidence, report,
                   st["step_count"], validation)
    res.elapsed_s = round(time.time() - t0, 1)
    return res


def run_live_gemini(scenario_id: str, data_dir=None, wrap=None, notes_override=None) -> RunResult:
    """wrap: optional function applied to each chat model (used by the evaluation runner to count calls)."""
    import config
    from llm_router import get_chat_model
    fast, reasoning = get_chat_model("fast"), get_chat_model("reasoning")
    if wrap:
        fast, reasoning = wrap(fast), wrap(reasoning)
    return run_graph(scenario_id, fast, reasoning, "live-gemini",
                     {"fast": config.FAST_LOOP_MODEL, "reasoning": config.REASONING_MODEL}, data_dir, notes_override)


def run_fake_graph(scenario_id: str, notes_override=None) -> RunResult:
    from fake_llm import ScriptedChatModel
    fake = ScriptedChatModel(SimBackend(scenario_id, notes_override=notes_override))
    return run_graph(scenario_id, fake, fake, "scripted-offline", {"model": "scripted fake (no AI)"},
                     notes_override=notes_override)
