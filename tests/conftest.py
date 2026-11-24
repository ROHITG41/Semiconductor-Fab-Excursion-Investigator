import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Keep runtime state (audit chain, memory DB, vector index) out of the real project folders during tests.
_tmp = Path(tempfile.mkdtemp(prefix="fab_sentry_tests_"))
os.environ["FAB_SENTRY_AUDIT_PATH"] = str(_tmp / "chain.jsonl")
os.environ["FAB_SENTRY_MEMORY_DB"] = str(_tmp / "episodic.db")
os.environ["FAB_SENTRY_INDEX_PATH"] = str(_tmp / "kb_index.json")
os.environ["FAB_SENTRY_EMBEDDER"] = "offline"
os.environ["GEMINI_API_KEY"] = ""
os.environ["FAB_SENTRY_HMAC_SECRET"] = "test-secret-" + "x" * 24
