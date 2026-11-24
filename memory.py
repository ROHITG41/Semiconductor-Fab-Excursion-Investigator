"""memory.py - three memory tiers.

1. Working memory : the LangGraph state of the current investigation (messages, evidence). Lives per run.
2. Episodic memory: past investigations that a human APPROVED. This module. Writing needs a valid, matching
                    APPROVE entry in the audit chain, so the AI can never write its own conclusions into memory.
3. Semantic memory: the knowledge base searched by rag.py.

Precedents are advisory: a past case is never evidence that the same cause applies today.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import config
from audit import AuditChain, run_digest, verify_entries
from rag import HashEmbedder, HybridIndex
from sandbox import clean_free_text

DB_PATH = config.ROOT / "memory" / "episodic.db"


class MemoryWriteRefused(PermissionError):
    pass


class EpisodicMemory:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else config.runtime_path("FAB_SENTRY_MEMORY_DB", DB_PATH)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS cases (
                run_id TEXT PRIMARY KEY, scenario_id TEXT, tag TEXT, parameter TEXT, asset_id TEXT,
                root_cause TEXT, verdict TEXT, summary TEXT, approved_by TEXT, approved_role TEXT,
                approved_at TEXT, chain_seq INTEGER, source_mode TEXT, reviewer_comment TEXT)""")

    def _db(self):
        return sqlite3.connect(self.path)

    def count(self) -> int:
        with self._db() as db:
            return db.execute("SELECT COUNT(*) FROM cases").fetchone()[0]

    def remember_approved(self, run, chain: AuditChain, key: str) -> dict:
        """Store a case ONLY if the chain verifies and holds an APPROVE for exactly this run record."""
        ok, problems = verify_entries(chain.entries(), key)
        if not ok:
            raise MemoryWriteRefused(f"audit chain does not verify: {problems[0]}")
        final = chain.final_decision(run.run_id)
        if not final or final["action"] != "APPROVE":
            raise MemoryWriteRefused("no human APPROVE decision exists for this run")
        if final["run_digest"] != run_digest(run):
            raise MemoryWriteRefused("run record changed after it was approved")
        if not run.report:
            raise MemoryWriteRefused("run has no report")
        comment, hits = clean_free_text(final["comment"])
        t = run.triage
        asset = next((e.output.get("asset_id") for e in run.evidence if e.tool == "trace_upstream_loop"), "")
        row = (run.run_id, run.scenario_id, t["tag"], t["parameter"], asset, run.report.root_cause_code.value,
               t["verdict"], f"{t['parameter']} at {t['tag']}: approved cause {run.report.root_cause_code.value}, "
               f"deterministic verdict {t['verdict']}", final["actor"], final["role"], final["timestamp_utc"],
               final["seq"], run.mode, comment)
        with self._db() as db:
            db.execute("INSERT OR REPLACE INTO cases VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", row)
        return {"stored": run.run_id}

    def search(self, tag: str, k: int = 3) -> dict:
        with self._db() as db:
            db.row_factory = sqlite3.Row
            rows = [dict(r) for r in db.execute("SELECT * FROM cases")]
        if not rows:
            return {"count": 0, "cases": [], "note": "No approved past cases in memory yet."}
        items = [{"id": r["run_id"], "text": f"{r['parameter']} {r['tag']} {r['asset_id']} {r['root_cause']}", **r}
                 for r in rows]
        idx = HybridIndex(items, HashEmbedder())
        spec_query = tag.replace("_", " ")
        hits = idx.search(spec_query, k)
        cases = [{"run_id": h["run_id"], "tag": h["tag"], "root_cause": h["root_cause"], "verdict": h["verdict"],
                  "approved_by_role": h["approved_role"], "approved_at": h["approved_at"], "source_mode": h["source_mode"],
                  "reviewer_comment": h["reviewer_comment"]} for h in hits]
        return {"count": len(cases), "cases": cases,
                "note": "Precedents only. A past approved cause is not evidence for this alarm."}
