"""fake_llm.py - scripted stand-in for Gemini, used ONLY for offline tests of the graph wiring.
It proves wiring, state flow, tool schemas and validators. It does not prove Gemini reasons well."""
from __future__ import annotations

import json
import uuid

from langchain_core.messages import AIMessage, ToolMessage

from engine import backend_assets, build_scripted_report, next_tool_calls
from schemas import EvidenceItem


class _Structured:
    def __init__(self, schema):
        self.schema = schema

    def invoke(self, prompt):
        text = prompt if isinstance(prompt, str) else str(prompt)
        triage = json.loads(next(l for l in text.splitlines() if l.startswith("TRIAGE_JSON: "))[13:])
        ev = [EvidenceItem.model_validate(e) for e in json.loads(
            next(l for l in text.splitlines() if l.startswith("EVIDENCE_JSON: "))[15:])]
        return build_scripted_report(ev, triage)


class ScriptedChatModel:
    def __init__(self, backend):
        self.backend = backend
        self.assets = backend_assets(backend)

    def bind_tools(self, tools, **kwargs):
        return self

    def with_structured_output(self, schema, **kwargs):
        return _Structured(schema)

    def invoke(self, messages, **kwargs):
        calls_by_id, evidence = {}, []
        for m in messages:
            if isinstance(m, AIMessage):
                for c in (m.tool_calls or []):
                    calls_by_id[c["id"]] = (c["name"], c.get("args", {}))
            elif isinstance(m, ToolMessage):
                name, args = calls_by_id.get(m.tool_call_id, (m.name, {}))
                evidence.append(EvidenceItem(id=f"E{len(evidence) + 1}", tool=name, args=args,
                                             output=json.loads(m.content)))
        nxt = next_tool_calls(self.backend.alarm["tag"], self.assets, evidence)
        if not nxt:
            return AIMessage(content="Evidence gathered. Ready to draft.")
        return AIMessage(content="", tool_calls=[{"name": n, "args": a, "id": f"call_{uuid.uuid4().hex[:8]}"}
                                                 for n, a in nxt])
