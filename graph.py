"""graph.py - LangGraph wiring: ingress -> agent <-> tools -> draft -> validate -> finish.
Human sign-off (interrupt + keyed HMAC chain) is added in Stage 2."""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from nodes import make_nodes
from state import SentryState
from tools import build_tools


def build_graph(backend, fast_llm, reasoning_llm):
    tools = build_tools(backend)
    n = make_nodes(backend, fast_llm, reasoning_llm, tools)
    g = StateGraph(SentryState)
    g.add_node("ingress", n["ingress"])
    g.add_node("agent", n["agent"])
    g.add_node("tools", ToolNode(tools))
    g.add_node("collect", n["collect"])
    g.add_node("draft", n["draft"])
    g.add_node("validate", n["validate"])
    g.add_node("finish", n["finish"])
    g.add_edge(START, "ingress")
    g.add_edge("ingress", "agent")
    g.add_conditional_edges("agent", n["route_after_agent"], {"tools": "tools", "draft": "draft"})
    g.add_edge("tools", "collect")
    g.add_edge("collect", "agent")
    g.add_edge("draft", "validate")
    g.add_conditional_edges("validate", n["route_after_validate"], {"draft": "draft", "finish": "finish"})
    g.add_edge("finish", END)
    return g.compile()
