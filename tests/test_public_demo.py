import json
import subprocess
import sys
from pathlib import Path

from engine import run_scripted_offline
from replay import list_traces, load_trace, save_trace
from schemas import RunResult

ROOT = Path(__file__).resolve().parents[1]


def test_trace_dir_follows_public_demo_flag():
    code = ("import os; os.environ['FAB_SENTRY_PUBLIC_DEMO']='{v}'; os.environ.pop('FAB_SENTRY_TRACE_DIR', None); "
            "import config; print(config.PUBLIC_DEMO, config.TRACE_DIR.name)")
    for v, want in (("1", "True demo_traces"), ("0", "False traces")):
        out = subprocess.run([sys.executable, "-c", code.format(v=v)], cwd=ROOT, capture_output=True, text=True)
        assert out.stdout.strip() == want, out.stderr


def test_make_demo_traces_uses_run1_regardless_of_outcome(tmp_path):
    src = tmp_path / "agent_live"
    src.mkdir()
    base = run_scripted_offline("S01")
    live = base.model_copy(update={"mode": "live-gemini", "recorded_at": "2026-11-23T10:00:00+00:00"})
    wrong = live.model_copy(update={"report": live.report.model_copy(update={"confidence": "low"})})
    for k, r in (("run1", wrong), ("run2", live)):
        (src / f"S01_{k}.json").write_text(json.dumps({"key": f"S01_{k}", "result": r.model_dump(mode="json")}))
    dst = tmp_path / "demo_traces"
    out = subprocess.run([sys.executable, str(ROOT / "make_demo_traces.py"), "--src", str(src), "--dst", str(dst)],
                         cwd=ROOT, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    traces = list_traces(dst)
    assert len(traces) == 1
    assert load_trace(traces[0]).report.confidence == "low"        # run 1, not the 'better' run 2
