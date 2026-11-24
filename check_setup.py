"""check_setup.py - the 10-minute Windows smoke test (steps 1-4; step 5 is manual: streamlit run app.py).
Usage:  python check_setup.py            (add --no-live to skip the Gemini call)"""
import asyncio
import importlib
import subprocess
import sys

NO_LIVE = "--no-live" in sys.argv


def step(n, title):
    print(f"\n=== Step {n}: {title}")


step(1, "import all modules")
for m in ["config", "schemas", "guardband", "simulator", "tools_core", "sandbox", "validator", "engine",
          "state", "tools", "nodes", "graph", "llm_router", "fake_llm", "replay", "runner", "mcp_server",
          "rag", "audit", "memory", "signoff", "store", "dossier"]:
    importlib.import_module(m)
    print("  ok", m)

step(2, "pytest (offline, includes the LangGraph fake-model test)")
r = subprocess.run([sys.executable, "-m", "pytest", "-q"])
print("  pytest exit code", r.returncode)

step(3, "one live Gemini call per configured model")
if NO_LIVE:
    print("  skipped (--no-live)")
else:
    from llm_router import startup_check
    print(" ", startup_check())

step("3b", "embedding model (knowledge-base index)")
if NO_LIVE:
    print("  skipped (--no-live)")
else:
    from rag import GeminiEmbedder
    try:
        emb = GeminiEmbedder()
        v = emb.embed_query("UV lamp ageing")
        print(f"  ok: {emb.name} returns {len(v)}-dimension vectors")
    except Exception as e:  # noqa: BLE001
        print(f"  embedding check failed: {e}\n  The app will fall back to offline hashing embeddings until this is fixed.")

step(4, "one tool call through MCP stdio from the command line")


async def mcp_roundtrip():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    params = StdioServerParameters(command=sys.executable, args=["mcp_server.py"], env={"FAB_SENTRY_SCENARIO": "S01"})
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()
            res = await s.call_tool("check_guardband_and_cal", {"tag": "UPW_B_TOC_POU"})
            print(" ", res.content[0].text[:160].replace("\n", " "))

asyncio.run(mcp_roundtrip())
print("\nStep 5 (manual): streamlit run app.py  -> run S01 in Scripted offline mode, then Live Gemini.")
