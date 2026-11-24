"""tools.py - in-process LangChain tool wrappers over tools_core (default path for Streamlit on Windows).
The identical functions are served over MCP stdio by mcp_server.py."""
from __future__ import annotations

from langchain_core.tools import StructuredTool

from tools_core import SimBackend, TOOL_NAMES


def build_tools(backend: SimBackend) -> list[StructuredTool]:
    tools = []
    for name in TOOL_NAMES:
        fn = getattr(backend, name)
        tools.append(StructuredTool.from_function(func=fn, name=name, description=(fn.__doc__ or name).strip()))
    return tools
