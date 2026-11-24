"""app.py - FAB-SENTRY Streamlit UI (Stage 2).  Run:  streamlit run app.py
Modes: Replay (recorded live Gemini run) | Scripted offline demo (no AI) | Live Gemini.
After a run: human review and sign-off, audit chain, PDF dossier, episodic memory."""
from __future__ import annotations

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import json

import pandas as pd
import streamlit as st

import config
from audit import ACTIONS, ROLES, AuditChain, AuditKeyMissing, get_key, verify_entries
from dossier import build_dossier
from engine import run_scripted_offline
from memory import EpisodicMemory
from replay import list_traces, load_trace, save_trace
from signoff import SignoffError, decide, status_of
from store import save_run
from tools_core import SimBackend

st.set_page_config(page_title="Semiconductor Fab Excursion Investigator", layout="wide")
st.title("Semiconductor Fab Excursion Investigator")
st.caption("Ultra-pure water, bulk-gas and AMC excursions: AI proposes, code decides pass or fail, a named human signs. Codename FAB-SENTRY.")
st.warning(config.DATA_NOTICE)

alarms = json.loads((config.DATA_DIR / "alarms.json").read_text())
MODES = ["Replay (recorded live Gemini run)", "Scripted offline demo (no AI model)", "Live Gemini (needs GEMINI_API_KEY)"]
if config.PUBLIC_DEMO:
    MODES = MODES[:2]      # public deployment: no Live Gemini (it would spend the owner's API quota)

with st.sidebar:
    sid = st.selectbox("Scenario", list(alarms), format_func=lambda s: f"{s}: {alarms[s]['tag']}")
    mode = st.radio("Mode", MODES)
    st.caption(f"Fast model: {config.FAST_LOOP_MODEL}  |  Reasoning model: {config.REASONING_MODEL}")
    if config.PUBLIC_DEMO:
        st.info("Public demo. Replay shows run 1 of 3 recorded live runs for each scenario, chosen in advance and not "
                "by outcome. Live Gemini and sign-off are switched off here. Run it locally to use them.")
    save_live = False if config.PUBLIC_DEMO else st.checkbox("Save live run as a replay trace", value=True)
    go = st.button("Run investigation", type="primary")

b = SimBackend(sid)
st.subheader(f"Alarm {sid}")
st.write(alarms[sid]["description"], f"({alarms[sid]['triggered_at']})")
df = pd.DataFrame(b.series[b.alarm["tag"]], columns=["time", "value"])
df["time"] = pd.to_datetime(df["time"])
spec = b.sensors[b.alarm["tag"]]
st.line_chart(df.set_index("time"), height=200)
st.caption(f"{spec.parameter} [{spec.unit}] | limit {spec.limit} ({spec.direction}) +/- {spec.half_width} | {spec.limit_source}")

if go:
    run = None
    try:
        if mode == MODES[0]:
            traces = [p for p in list_traces() if p.name.startswith(sid + "_")]
            if not traces:
                st.error(f"No recorded live run for {sid} yet. Run:  python record_trace.py --scenario {sid}  "
                         "(uses your GEMINI_API_KEY once), then try again.")
            else:
                run = load_trace(traces[-1])
        elif mode == MODES[1]:
            run = run_scripted_offline(sid)
        else:
            with st.spinner("Calling Gemini..."):
                from runner import run_live_gemini
                run = run_live_gemini(sid)
                if save_live:
                    save_trace(run)
    except Exception as e:   # noqa: BLE001 - show provider/setup errors plainly
        st.error(f"Run failed: {e}")
    if run:
        if not config.PUBLIC_DEMO:
            save_run(run)
        st.session_state["run"] = run

run = st.session_state.get("run")
if run and run.scenario_id == sid:
    chain = AuditChain()
    label = {"replay": f"REPLAY of a recorded live Gemini run ({run.recorded_at}). Not live reasoning.",
             "scripted-offline": "SCRIPTED OFFLINE DEMO: no AI model was used. Wiring demonstration only.",
             "live-gemini": "LIVE GEMINI RUN"}[run.mode]
    st.info(f"{label}  Models: {run.models}  |  run id {run.run_id}")
    c1, c2, c3 = st.columns(3)
    v = run.triage["verdict"]
    (c1.success if v == "PASS" else c1.error if v == "FAIL" else c1.warning)(f"Deterministic verdict (code): {v}")
    c2.metric("Latest reading", f"{run.triage['measured']} {run.triage['unit']}", f"limit {run.triage['limit']}")
    c3.write(("Calibration: valid" if run.triage["calibration_valid"] else f"Calibration: {run.triage['calibration_note']}"))
    st.write(run.hold_advisory)

    st.subheader("Operator notes (untrusted data)")
    if run.notes_scan["blocked"]:
        st.error(f"Possible prompt injection detected {run.notes_scan['hits']}. Notes were withheld from the model.")
    st.text_area("Original text as typed", run.notes_scan["original"], height=90, disabled=True)

    st.subheader("Draft investigation (UNOFFICIAL, needs human review)")
    if run.report:
        st.markdown(f"**Most likely cause:** `{run.report.root_cause_code.value}`  |  confidence: {run.report.confidence}")
        st.write(run.report.narrative)
        st.write("Recommended actions (for qualified engineer review):")
        for a in run.report.recommended_actions:
            st.markdown(f"- {a}")
        if run.report.knowledge_base_citations:
            st.caption("Knowledge-base citations: " + ", ".join(run.report.knowledge_base_citations))
        with st.expander("Hypotheses"):
            st.json([h.model_dump(mode="json") for h in run.report.hypotheses])
    (st.success if run.validation.ok else st.error)(
        "Numeric-consistency check passed" if run.validation.ok else f"Validation failed: {run.validation.violations}")
    with st.expander(f"Evidence ({len(run.evidence)} tool results in {run.tool_rounds} rounds)"):
        for e in run.evidence:
            st.markdown(f"**{e.id}** `{e.tool}` {e.args}")
            st.json(e.output, expanded=False)

    if run.quality_notes:
        st.caption("Note (computed by code): " + " ".join(run.quality_notes))
    if run.quality_flags:
        st.warning("Evidence-quality flags (computed by code):\n\n" + "\n".join(f"- {f}" for f in run.quality_flags))

    # ---------------- human review ----------------
    st.subheader("Human review and sign-off")
    status = status_of(run, chain)
    st.write(f"Status: **{status}**")
    final = chain.final_decision(run.run_id)
    try:
        key = None if config.PUBLIC_DEMO else get_key()
    except AuditKeyMissing as e:
        key = None
        st.warning(f"Sign-off is disabled. {e}")
    if final:
        st.success(f"{final['action']} by {final['actor']} ({final['role']}) at {final['timestamp_utc']}. Comment: {final['comment'] or '(none)'}")
    elif config.PUBLIC_DEMO:
        st.info("Sign-off is switched off in the public demo because it is a shared deployment. "
                "The draft PDF below shows what a reviewer would receive. Run the project locally to try approve, reject and the audit chain.")
    elif key:
        with st.form(f"signoff_{run.run_id}"):
            st.caption("Demo only: the name is typed in and not authenticated.")
            name = st.text_input("Reviewer name")
            role = st.selectbox("Reviewer role", ROLES)
            action = st.radio("Decision", ["APPROVE", "REJECT", "REQUEST_MORE_EVIDENCE"], horizontal=True)
            comment = st.text_area("Comment (optional, max 500 characters)", max_chars=500)
            ack = st.checkbox("I have read the evidence-quality flags above", value=False) if run.quality_flags else False
            if st.form_submit_button("Record decision"):
                try:
                    out = decide(run, action, name, role, comment, chain, key, EpisodicMemory(), acknowledged_flags=ack)
                    st.success("Decision recorded." + (" Case saved to episodic memory." if out["memory_stored"] else ""))
                    st.rerun()
                except SignoffError as e:
                    st.error(str(e))

    final = chain.final_decision(run.run_id)
    ok = verify_entries(chain.entries(), key)[0] if key else None
    d1, d2 = st.columns(2)
    d1.download_button("Download DRAFT dossier (PDF)", build_dossier(run), file_name=f"Fab-Excursion-Investigator_{run.run_id}_draft.pdf",
                       mime="application/pdf")
    if final and final["action"] == "APPROVE":
        d2.download_button("Download SIGNED dossier (PDF)", build_dossier(run, final, chain.head(), ok),
                           file_name=f"Fab-Excursion-Investigator_{run.run_id}_signed.pdf", mime="application/pdf")

    if not config.PUBLIC_DEMO:           # shared state (audit chain, episodic memory) is local-only
        with st.expander("Audit chain (tamper-evident, not immutable)"):
            entries = chain.entries()
            if key and entries:
                good, problems = verify_entries(entries, key)
                (st.success if good else st.error)("Chain verifies" if good else f"Chain FAILED: {problems}")
            st.dataframe(pd.DataFrame(entries) if entries else pd.DataFrame({"info": ["No decisions recorded yet"]}))
        with st.expander("Memory and retrieval"):
            mem = EpisodicMemory()
            st.write(f"Approved past cases in episodic memory: {mem.count()}")
            st.json(mem.search(run.triage["tag"]))
            try:
                st.caption(f"Knowledge-base retrieval: {b.retrieval_note()}")
            except Exception as e:   # noqa: BLE001
                st.caption(f"Retrieval status unavailable: {e}")
