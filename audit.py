"""audit.py - tamper-evident keyed-HMAC audit chain for human decisions.

Each entry's HMAC covers its own fields AND the previous entry's HMAC, so editing, deleting or reordering any
entry breaks verification. This is TAMPER-EVIDENT, not immutable: someone who holds the secret key can rewrite the
chain. Names are typed in by the user in this demo: there is no real authentication, so this is a demonstration of
the pattern, not a validated electronic signature.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import config

GENESIS = "0" * 64
ACTIONS = ("APPROVE", "REJECT", "REQUEST_MORE_EVIDENCE")
FINAL = ("APPROVE", "REJECT")
ROLES = ("QA engineer", "Process engineer", "Facilities engineer", "Engineering manager")
CHAIN_PATH = config.ROOT / "audit" / "chain.jsonl"


class AuditKeyMissing(RuntimeError):
    pass


def get_key() -> str:
    k = os.getenv("FAB_SENTRY_HMAC_SECRET", "")
    if len(k) < 16:
        raise AuditKeyMissing("FAB_SENTRY_HMAC_SECRET is missing or shorter than 16 characters. Generate one with: "
                              'python -c "import secrets; print(secrets.token_hex(32))"  and put it in .env')
    return k


def canon(d: dict) -> str:
    return json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def run_digest(run) -> str:
    """SHA-256 of the full run record as it was when the human reviewed it."""
    return hashlib.sha256(canon(run.model_dump(mode="json")).encode()).hexdigest()


def _mac(key: str, entry: dict) -> str:
    body = {k: v for k, v in entry.items() if k != "hmac"}
    return hmac.new(key.encode(), canon(body).encode(), hashlib.sha256).hexdigest()


class AuditChain:
    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else config.runtime_path("FAB_SENTRY_AUDIT_PATH", CHAIN_PATH)

    def entries(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(l) for l in self.path.read_text(encoding="utf-8").splitlines() if l.strip()]

    def head(self) -> str:
        e = self.entries()
        return e[-1]["hmac"] if e else GENESIS

    def append(self, key: str, *, run_id: str, digest: str, action: str, actor: str, role: str, comment: str = "") -> dict:
        if action not in ACTIONS:
            raise ValueError(f"unknown action {action}")
        entries = self.entries()
        entry = {"seq": len(entries) + 1, "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 "run_id": run_id, "run_digest": digest, "action": action, "actor": actor.strip(), "role": role,
                 "comment": comment.strip()[:500], "prev_hmac": entries[-1]["hmac"] if entries else GENESIS}
        entry["hmac"] = _mac(key, entry)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        return entry

    def entries_for(self, run_id: str) -> list[dict]:
        return [e for e in self.entries() if e["run_id"] == run_id]

    def final_decision(self, run_id: str) -> Optional[dict]:
        f = [e for e in self.entries_for(run_id) if e["action"] in FINAL]
        return f[-1] if f else None


def verify_entries(entries: list[dict], key: str) -> tuple[bool, list[str]]:
    problems, prev = [], GENESIS
    for i, e in enumerate(entries, 1):
        if e.get("seq") != i:
            problems.append(f"entry {i}: sequence number is {e.get('seq')} (entry removed or reordered)")
        if e.get("prev_hmac") != prev:
            problems.append(f"entry {i}: link to previous entry is broken")
        if not hmac.compare_digest(str(e.get("hmac", "")), _mac(key, e)):
            problems.append(f"entry {i}: content or signature does not match (edited)")
        prev = e.get("hmac", "")
    return (not problems), problems
