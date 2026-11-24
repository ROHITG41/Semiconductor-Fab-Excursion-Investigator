"""make_demo_traces.py - copy RUN 1 of each scenario from your saved evaluation runs into demo_traces/ for the public demo.
Run 1 is used for every scenario, chosen in advance and NOT by outcome, so the demo is not cherry-picked.
Usage:  python make_demo_traces.py            (reads evalruns/agent_live, writes demo_traces/)"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from replay import save_trace
from schemas import RunResult

ap = argparse.ArgumentParser()
ap.add_argument("--src", default="evalruns/agent_live")
ap.add_argument("--dst", default="demo_traces")
ap.add_argument("--run", default="run1")
a = ap.parse_args()

src, dst = Path(a.src), Path(a.dst)
files = sorted(src.glob(f"S*_{a.run}.json"))
if not files:
    raise SystemExit(f"No {a.run} files found in {src}. Run the agent evaluation first.")
for f in files:
    run = RunResult.model_validate(json.loads(f.read_text())["result"])
    p = save_trace(run, dst)
    print(f"{run.scenario_id}: {run.report.root_cause_code.value if run.report else None} -> {p.name}")
print(f"\nWrote {len(files)} traces to {dst}/. Commit this folder to the repository.")
