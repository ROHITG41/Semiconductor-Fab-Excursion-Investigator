"""replay.py - record real live-Gemini runs and replay them. Replay shows a RECORDED run and is always
labelled as such; it is never presented as live reasoning."""
from __future__ import annotations

import json
from pathlib import Path

from config import TRACE_DIR
from engine import evidence_quality, evidence_quality_notes
from schemas import RunResult


def save_trace(run: RunResult, trace_dir: Path = TRACE_DIR) -> Path:
    if run.mode != "live-gemini":
        raise ValueError("Only live Gemini runs may be recorded as replay traces.")
    trace_dir.mkdir(parents=True, exist_ok=True)
    stamp = (run.recorded_at or "").replace(":", "").replace("-", "")[:15]
    path = trace_dir / f"{run.scenario_id}_{stamp}.json"
    path.write_text(run.model_dump_json(indent=2))
    return path


def list_traces(trace_dir: Path = TRACE_DIR) -> list[Path]:
    return sorted(Path(trace_dir).glob("S*.json")) if Path(trace_dir).exists() else []


def load_trace(path: Path) -> RunResult:
    run = RunResult.model_validate_json(Path(path).read_text())
    if run.mode != "live-gemini":
        raise ValueError("Trace was not recorded from a live Gemini run.")
    import uuid
    return run.model_copy(update={"mode": "replay", "run_id": uuid.uuid4().hex[:12],
                                  "quality_flags": evidence_quality(run.evidence),
                                  "quality_notes": evidence_quality_notes(run.evidence)})  # each viewing is its own reviewable run
