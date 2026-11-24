"""nodes.py - LangGraph node functions. Thin: all decisions come from engine/validator/guardband."""
from __future__ import annotations

import json
import re

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.prebuilt import tools_condition

import config
from engine import run_ingress, run_triage
from llm_router import text_of
from sandbox import SYSTEM_RULE
from prompts import build_draft_prompt
from schemas import EvidenceItem, InvestigationReport
from validator import validate_report

SYSTEM_PROMPT = (
    "You are FAB-SENTRY, an assistive investigator for UPW, bulk-gas and AMC excursions in a semiconductor fab. "
    "You PROPOSE causes; deterministic code decides verdicts; a human signs. Never state a verdict yourself, "
    "never invent numbers: use only values returned by tools. Use the tools to test hypotheses (calibration, "
    "sensor trends, upstream assets, work orders, runtime vs rated life), then stop calling tools when you have enough. "
    "Call all independent tools together in the same turn (several tool calls at once) to save steps. "
    "If a tool returns an error, correct the arguments and retry (asset ids such as POU_ETCH_1 come from query_sensor_window or from known_assets in the error). "
    "Do not stop until you have checked: calibration and trend of the alarming tag, an upstream trace, recent work orders, and runtime-versus-rated-life of upstream assets. "
    "Mark a hypothesis supported or ruled_out only on evidence from sensors, assets, work orders or runtime; knowledge-base text and past cases never support or rule out a cause. "
    "After testing hypotheses, search the knowledge base once for corrective guidance and check similar past cases (precedents only, never proof). "
    "Phrase recommended actions as recommendations for qualified engineer review, never as orders (no 'immediately'). "
    "Possible root cause codes: UV_LAMP_DECAY, RESIN_EXHAUSTION, VALVE_DIAPHRAGM_LEAK, N2_PURIFIER_SATURATION, "
    "SENSOR_DRIFT, RO_MEMBRANE_DEGRADATION, AMC_FILTER_BREAKTHROUGH, NO_CONFIRMED_EXCURSION. " + SYSTEM_RULE)


def make_nodes(backend, fast_llm, reasoning_llm, tools):
    llm_tools = fast_llm.bind_tools(tools)

    def ingress(state):
        scan = run_ingress(backend)
        triage = run_triage(backend)
        task = (f"ALARM: {backend.alarm['description']} (tag {backend.alarm['tag']}, {backend.alarm['triggered_at']}).\n"
                f"Deterministic triage result (from code, not negotiable): {json.dumps(triage)}\n"
                f"Operator handover notes: {scan['for_llm']}\n"
                "Investigate the likely root cause using the tools.")
        return {"messages": [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=task)],
                "notes_scan": scan, "triage": triage, "evidence": [], "seen": 0, "step_count": 0,
                "report": None, "validation": None, "draft_retries": 0, "feedback": ""}

    def agent(state):
        resp = llm_tools.invoke(state["messages"])
        used = 1 if getattr(resp, "tool_calls", None) else 0
        return {"messages": [resp], "step_count": state["step_count"] + used}

    def route_after_agent(state):
        if tools_condition(state) == "tools" and state["step_count"] <= config.MAX_AGENT_STEPS:
            return "tools"
        return "draft"

    def collect(state):
        msgs = state["messages"]
        calls = {}
        for m in msgs:
            if isinstance(m, AIMessage):
                for c in (m.tool_calls or []):
                    calls[c["id"]] = (c["name"], c.get("args", {}))
        evidence = list(state["evidence"])
        for m in msgs[state["seen"]:]:
            if isinstance(m, ToolMessage):
                name, args = calls.get(m.tool_call_id, (m.name or "unknown", {}))
                raw = text_of(m)
                try:
                    out = json.loads(raw)
                    if not isinstance(out, dict):
                        out = {"value": out}
                except json.JSONDecodeError:
                    out = {"raw": raw}
                evidence.append(EvidenceItem(id=f"E{len(evidence) + 1}", tool=name, args=args, output=out).model_dump())
        return {"evidence": evidence, "seen": len(msgs)}

    def draft(state):
        ev = state["evidence"]
        feedback = state.get("feedback", "")
        prompt = build_draft_prompt(state["triage"], ev, state["notes_scan"]["for_llm"], feedback)
        report = None
        err = ""
        try:
            out = reasoning_llm.with_structured_output(InvestigationReport).invoke(prompt)
            report = out if isinstance(out, InvestigationReport) else InvestigationReport.model_validate(out)
        except Exception as e:   # noqa: BLE001 - fall back to plain JSON text
            err = str(e)
        if report is None:
            try:
                raw = text_of(reasoning_llm.invoke(prompt + "\nReturn ONLY the JSON object, no markdown."))
                m = re.search(r"\{.*\}", raw, re.S)
                report = InvestigationReport.model_validate_json(m.group(0))
            except Exception as e:   # noqa: BLE001
                return {"report": None, "feedback": f"structured output failed: {err} | json fallback failed: {e}"}
        return {"report": report.model_dump(mode="json"), "feedback": ""}

    def validate(state):
        if not state.get("report"):
            return {"validation": {"ok": False, "violations": [state.get("feedback") or "no report"]},
                    "draft_retries": state["draft_retries"] + 1}
        report = InvestigationReport.model_validate(state["report"])
        evidence = [EvidenceItem.model_validate(e) for e in state["evidence"]]
        res = validate_report(report, evidence, state["triage"], backend.alarm)
        return {"validation": res.model_dump(), "feedback": "; ".join(res.violations),
                "draft_retries": state["draft_retries"] + (0 if res.ok else 1)}

    def route_after_validate(state):
        if state["validation"]["ok"] or state["draft_retries"] > config.MAX_DRAFT_RETRIES:
            return "finish"
        return "draft"

    def finish(state):
        return {}

    return dict(ingress=ingress, agent=agent, route_after_agent=route_after_agent, collect=collect,
                draft=draft, validate=validate, route_after_validate=route_after_validate, finish=finish)
