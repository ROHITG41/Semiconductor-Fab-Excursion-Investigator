"""rag.py - hybrid retrieval: BM25 (sparse) + embeddings (dense), fused with reciprocal rank fusion.

* The vector index stores the embedding model name, vector dimension and a corpus hash.
  If any of them changes, the index is rebuilt automatically (never mix vectors from two models).
* Dense embeddings come from Gemini (EMBEDDING_MODEL) when a key is available; otherwise a deterministic
  offline hashing embedder is used and the status line says so. Offline mode is weaker at paraphrases.
* No cross-encoder reranker in this prototype: reciprocal rank fusion only.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Optional

import config

KB_DIR = config.ROOT / "kb"
INDEX_PATH = config.ROOT / "index" / "kb_index.json"
_TOKEN = re.compile(r"[a-z0-9]+")
STOP = {"the", "a", "an", "of", "to", "and", "or", "in", "on", "is", "are", "at", "for", "with", "by", "it", "as", "be"}


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in STOP]


# ---------------- sparse ----------------
class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.docs, self.k1, self.b = docs, k1, b
        self.n = len(docs)
        self.avg = (sum(len(d) for d in docs) / self.n) if self.n else 0.0
        df: dict[str, int] = {}
        for d in docs:
            for t in set(d):
                df[t] = df.get(t, 0) + 1
        self.idf = {t: math.log(1 + (self.n - c + 0.5) / (c + 0.5)) for t, c in df.items()}

    def scores(self, query: list[str]) -> list[float]:
        out = []
        for d in self.docs:
            tf: dict[str, int] = {}
            for t in d:
                tf[t] = tf.get(t, 0) + 1
            s = 0.0
            for t in query:
                if t in tf:
                    f = tf[t]
                    s += self.idf.get(t, 0) * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * len(d) / (self.avg or 1)))
            out.append(s)
        return out


# ---------------- dense ----------------
def _norm(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


class HashEmbedder:
    """Deterministic offline embedder (feature hashing of words and word pairs). A fallback, not a language model."""
    dim = 256
    name = "offline-hash-256"

    def _embed(self, text: str) -> list[float]:
        toks = tokenize(text)
        feats = toks + [a + "_" + b for a, b in zip(toks, toks[1:])]
        v = [0.0] * self.dim
        for f in feats:
            h = int(hashlib.md5(f.encode()).hexdigest(), 16)
            v[h % self.dim] += 1.0 if (h >> 100) & 1 else -1.0
        return _norm(v)

    def embed_documents(self, texts): return [self._embed(t) for t in texts]
    def embed_query(self, text): return self._embed(text)


class GeminiEmbedder:
    """Dense embeddings through google-genai. Raises on any provider error so the caller can fall back."""

    def __init__(self, model: str | None = None):
        from google import genai
        self.name = model or config.EMBEDDING_MODEL
        self.client = genai.Client(api_key=config.GEMINI_API_KEY)
        self.dim: Optional[int] = None

    def _call(self, texts: list[str], task: str) -> list[list[float]]:
        from google.genai import types
        out = []
        for i in range(0, len(texts), 50):
            batch = texts[i:i + 50]
            try:
                r = self.client.models.embed_content(model=self.name, contents=batch,
                                                     config=types.EmbedContentConfig(task_type=task))
            except Exception:   # noqa: BLE001 - some models reject task_type; retry without it
                r = self.client.models.embed_content(model=self.name, contents=batch)
            out += [_norm(list(e.values)) for e in r.embeddings]
        if out:
            self.dim = len(out[0])
        return out

    def embed_documents(self, texts): return self._call(texts, "RETRIEVAL_DOCUMENT")
    def embed_query(self, text): return self._call([text], "RETRIEVAL_QUERY")[0]


def get_embedder():
    """Gemini when a key is configured, else offline hashing. Returns (embedder, note)."""
    import os
    if config.GEMINI_API_KEY and os.getenv("FAB_SENTRY_EMBEDDER", "gemini") != "offline":
        try:
            return GeminiEmbedder(), f"dense: Gemini {config.EMBEDDING_MODEL}"
        except Exception as e:   # noqa: BLE001
            return HashEmbedder(), f"dense: offline hashing (Gemini embedder unavailable: {e})"
    return HashEmbedder(), "dense: offline hashing (no GEMINI_API_KEY)"


# ---------------- hybrid index ----------------
def _cos(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _rrf(rankings: list[list[int]], k: int = 60) -> dict[int, float]:
    fused: dict[int, float] = {}
    for r in rankings:
        for pos, idx in enumerate(r):
            fused[idx] = fused.get(idx, 0.0) + 1.0 / (k + pos + 1)
    return fused


class HybridIndex:
    def __init__(self, items: list[dict], embedder, vectors: Optional[list[list[float]]] = None, note: str = ""):
        """items: dicts with at least 'id' and 'text'."""
        self.items, self.embedder, self.note = items, embedder, note
        self.bm25 = BM25([tokenize(i["text"]) for i in items])
        self.vectors = vectors if vectors is not None else embedder.embed_documents([i["text"] for i in items])

    def search(self, query: str, k: int = 3) -> list[dict]:
        if not self.items:
            return []
        sparse = self.bm25.scores(tokenize(query))
        qv = self.embedder.embed_query(query)
        dense = [_cos(qv, v) for v in self.vectors]
        order = lambda sc: [i for i, s in sorted(enumerate(sc), key=lambda x: -x[1]) if s > 0]
        r_s, r_d = order(sparse), order(dense)
        fused = _rrf([r_s, r_d])
        top = sorted(fused, key=lambda i: -fused[i])[:k]
        return [{**self.items[i], "score": round(fused[i], 5),
                 "sparse_rank": (r_s.index(i) + 1) if i in r_s else None,
                 "dense_rank": (r_d.index(i) + 1) if i in r_d else None} for i in top]


def load_kb_chunks(kb_dir: Path = KB_DIR) -> list[dict]:
    chunks = []
    for f in sorted(Path(kb_dir).glob("*.md")):
        text = f.read_text(encoding="utf-8")
        for block in re.split(r"(?m)^## ", text)[1:]:
            head, _, body = block.partition("\n")
            cid, _, title = head.strip().partition(" ")
            chunks.append({"id": cid, "title": title.strip(), "source": f.name, "text": body.strip()})
    return chunks


def corpus_hash(chunks: list[dict]) -> str:
    return hashlib.sha256(json.dumps([(c["id"], c["text"]) for c in chunks]).encode()).hexdigest()[:16]


def build_or_load(embedder, note: str = "", kb_dir: Path = KB_DIR, index_path: Path = INDEX_PATH) -> tuple[HybridIndex, str]:
    """Load the saved vector index if model name, dimension and corpus hash all match; else rebuild and save."""
    chunks = load_kb_chunks(kb_dir)
    h = corpus_hash(chunks)
    reason = "built (no saved index)"
    index_path = Path(index_path)
    if index_path.exists():
        try:
            saved = json.loads(index_path.read_text())
            dim = saved["dimension"]
            if saved["embedding_model"] != embedder.name:
                reason = f"rebuilt (embedding model changed: {saved['embedding_model']} -> {embedder.name})"
            elif saved["corpus_hash"] != h:
                reason = "rebuilt (knowledge base text changed)"
            elif getattr(embedder, "dim", None) not in (None, dim):
                reason = f"rebuilt (vector dimension changed: {dim} -> {embedder.dim})"
            else:
                return HybridIndex(chunks, embedder, saved["vectors"], note), "loaded saved index"
        except (KeyError, ValueError):
            reason = "rebuilt (saved index unreadable)"
    idx = HybridIndex(chunks, embedder, None, note)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps({"embedding_model": embedder.name, "dimension": len(idx.vectors[0]),
                                      "corpus_hash": h, "vectors": idx.vectors}))
    return idx, reason


_CACHE: dict = {}


def default_index() -> HybridIndex:
    """Process-wide index. Falls back to offline hashing if Gemini embedding fails at build time."""
    if "idx" not in _CACHE:
        emb, note = get_embedder()
        try:
            idx, why = build_or_load(emb, note, index_path=config.runtime_path("FAB_SENTRY_INDEX_PATH", INDEX_PATH))
        except Exception as e:   # noqa: BLE001
            emb = HashEmbedder()
            idx, why = build_or_load(emb, f"dense: offline hashing (Gemini embedding failed: {e})",
                                     index_path=config.runtime_path("FAB_SENTRY_INDEX_PATH", INDEX_PATH))
        idx.note = f"{idx.note}; index {why}"
        _CACHE["idx"] = idx
    return _CACHE["idx"]
