"""store.py - persist run records so a reviewer can come back to them. Files are named by run id."""
from __future__ import annotations

from pathlib import Path

import config
from schemas import RunResult

RUNS_DIR = config.ROOT / "runs"


def _dir() -> Path:
    d = config.runtime_path("FAB_SENTRY_RUNS_DIR", RUNS_DIR)
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_run(run: RunResult) -> Path:
    p = _dir() / f"{run.run_id}.json"
    p.write_text(run.model_dump_json(indent=2), encoding="utf-8")
    return p


def load_run(run_id: str) -> RunResult:
    return RunResult.model_validate_json((_dir() / f"{run_id}.json").read_text(encoding="utf-8"))
