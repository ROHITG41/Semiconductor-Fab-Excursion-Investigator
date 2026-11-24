"""llm_router.py - thin adapter. Gemini only (langchain-google-genai). No Anthropic/OpenAI code."""
from __future__ import annotations

import os

import config


def get_chat_model(role: str):
    """role: 'fast' (tool loop) or 'reasoning' (final synthesis)."""
    if not config.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is empty. Put it in .env, or use Replay / Scripted offline mode.")
    from langchain_google_genai import ChatGoogleGenerativeAI
    model = config.FAST_LOOP_MODEL if role == "fast" else config.REASONING_MODEL
    return ChatGoogleGenerativeAI(
        model=model, google_api_key=config.GEMINI_API_KEY,
        temperature=float(os.getenv("LLM_TEMPERATURE", "0")),
        timeout=config.LLM_TIMEOUT_S, max_retries=config.LLM_MAX_RETRIES)   # exponential backoff on 429/5xx


def text_of(msg) -> str:
    """Message content may be a string or a list of parts (newer Gemini models)."""
    c = getattr(msg, "content", msg)
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "".join(p if isinstance(p, str) else p.get("text", "") for p in c)
    return str(c)


def startup_check() -> str:
    """One cheap call per configured model so a rejected model ID fails fast with a clear message."""
    out = []
    for role in ("fast", "reasoning"):
        name = config.FAST_LOOP_MODEL if role == "fast" else config.REASONING_MODEL
        try:
            reply = text_of(get_chat_model(role).invoke("Reply with the single word OK."))
            out.append(f"{role} model {name}: {reply.strip()[:20]}")
        except Exception as e:   # noqa: BLE001 - surface any provider error plainly
            msg = str(e)
            if "503" in msg or "UNAVAILABLE" in msg or "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                hint = "Temporary overload or quota limit at Google. Wait a few minutes and retry. The model ID is probably fine."
            elif "404" in msg or "NOT_FOUND" in msg:
                hint = "The model ID was not found. Fix FAST_LOOP_MODEL / REASONING_MODEL in .env."
            elif "API key" in msg or "400" in msg or "403" in msg:
                hint = "The API key was rejected. Check GEMINI_API_KEY in .env."
            else:
                hint = "See the provider message above."
            raise RuntimeError(f"Model check failed for {role} model '{name}': {msg}\n{hint}") from e
    return "; ".join(out)
