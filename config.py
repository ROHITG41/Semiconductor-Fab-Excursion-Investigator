"""config.py - central settings. Model IDs are overridable from .env; nothing secret lives here."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("FAB_SENTRY_DATA_DIR", ROOT / "data"))
# Public demo: a shared web deployment with no Live Gemini, no sign-off and no shared state. Set FAB_SENTRY_PUBLIC_DEMO=1.
PUBLIC_DEMO = os.getenv("FAB_SENTRY_PUBLIC_DEMO", "0").strip() == "1"
TRACE_DIR = Path(os.getenv("FAB_SENTRY_TRACE_DIR", ROOT / ("demo_traces" if PUBLIC_DEMO else "traces")))

# Model IDs supplied by Rohit/Gemini (Nov 2026). Override in .env without touching code.
FAST_LOOP_MODEL = os.getenv("FAST_LOOP_MODEL", "gemini-3.5-flash-lite")
REASONING_MODEL = os.getenv("REASONING_MODEL", "gemini-3.8-flash")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "gemini-embedding-2")  # used from Stage 2

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

MAX_AGENT_STEPS = int(os.getenv("MAX_AGENT_STEPS", "12"))   # tool-calling rounds
MAX_DRAFT_RETRIES = int(os.getenv("MAX_DRAFT_RETRIES", "1"))
LLM_TIMEOUT_S = int(os.getenv("LLM_TIMEOUT_S", "60"))
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "4"))    # exponential backoff on 429/5xx

DATA_NOTICE = ("SYNTHETIC DATA - PROTOTYPE evaluated on synthetic fab data; next step is a pilot on real fab data. "
               "Outputs are UNOFFICIAL DRAFTS that require human engineering review.")
STANDARDS_TAG = "to be verified against the standard"

# Window ends at the alarm time. 1-minute samples, 6 hours per scenario.
SAMPLE_MINUTES = 360


def runtime_path(env_name: str, default) -> Path:
    """Runtime state locations (audit chain, memory DB, vector index, saved runs). Tests point these at temp folders."""
    return Path(os.getenv(env_name, str(default)))
