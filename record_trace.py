"""record_trace.py - run real Gemini investigations and save them as replay traces.
Usage:  python record_trace.py --scenario S01      |   python record_trace.py --all
Needs GEMINI_API_KEY in .env. Each run makes several Gemini calls; --all uses the most."""
import argparse

from llm_router import startup_check
from replay import save_trace
from runner import run_live_gemini

ap = argparse.ArgumentParser()
ap.add_argument("--scenario")
ap.add_argument("--all", action="store_true")
a = ap.parse_args()
print(startup_check())
ids = [f"S{i:02d}" for i in range(1, 11)] if a.all else [a.scenario or "S01"]
for sid in ids:
    r = run_live_gemini(sid)
    p = save_trace(r)
    print(sid, r.report.root_cause_code.value if r.report else None, r.triage["verdict"],
          "valid" if r.validation.ok else r.validation.violations, "->", p.name)
