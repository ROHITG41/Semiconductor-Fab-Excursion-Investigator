"""batch.py - run many investigations under a call budget, saving each finished run so a stopped batch can resume.

Resume = finished runs are kept on disk and skipped next time. A run that was interrupted (budget, crash, quota)
is discarded and redone, never half-counted. Model responses are NOT cached on purpose: repeated runs must be
independent to measure run-to-run variation.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable

from evalkit.budget import BudgetExceeded, CallBudget
from schemas import RunResult


def _ok_path(d: Path, key: str) -> Path:
    return d / f"{key}.json"


def _fail_path(d: Path, key: str) -> Path:
    return d / f"{key}.failed.json"


def run_batch(label: str, items: list[tuple[str, Callable[[], RunResult]]], outdir: Path, budget: CallBudget,
              max_consecutive_failures: int = 3, log=print) -> dict:
    d = Path(outdir) / label
    d.mkdir(parents=True, exist_ok=True)
    summary = {"label": label, "planned": len(items), "already_done": 0, "completed_now": 0, "failed_now": 0,
               "stopped": "", "calls_used": 0}
    consecutive = 0
    for key, fn in items:
        if _ok_path(d, key).exists():
            summary["already_done"] += 1
            continue
        t0, before = time.time(), budget.used
        try:
            res = fn()
        except BudgetExceeded as e:
            summary["stopped"] = f"call budget reached ({e}); the unfinished run {key} was discarded"
            break
        except Exception as e:   # noqa: BLE001 - provider/network errors are recorded, not hidden
            _fail_path(d, key).write_text(json.dumps({"key": key, "error": f"{type(e).__name__}: {e}"[:1500]}, indent=2))
            summary["failed_now"] += 1
            consecutive += 1
            log(f"  {key}: FAILED ({type(e).__name__}) - {str(e)[:160]}")
            if consecutive >= max_consecutive_failures:
                summary["stopped"] = (f"{consecutive} failures in a row (probably quota or an outage); stopped to save calls")
                break
            continue
        consecutive = 0
        _ok_path(d, key).write_text(json.dumps({"key": key, "calls": budget.used - before,
                                                "elapsed_s": round(time.time() - t0, 1),
                                                "result": res.model_dump(mode="json")}, indent=2))
        if _fail_path(d, key).exists():
            _fail_path(d, key).unlink()
        summary["completed_now"] += 1
        log(f"  {key}: done ({budget.used - before} calls, {time.time() - t0:.0f}s, status {res.status})")
    summary["calls_used"] = budget.used
    return summary


def load_results(outdir: Path, label: str) -> tuple[list[dict], list[dict]]:
    """(finished runs as dicts with 'key', 'calls', 'run' (RunResult), failures)"""
    d = Path(outdir) / label
    ok, bad = [], []
    if not d.exists():
        return ok, bad
    for p in sorted(d.glob("*.json")):
        data = json.loads(p.read_text())
        if p.name.endswith(".failed.json"):
            bad.append(data)
        else:
            ok.append({"key": data["key"], "calls": data.get("calls", 0),
                       "run": RunResult.model_validate(data["result"])})
    return ok, bad
