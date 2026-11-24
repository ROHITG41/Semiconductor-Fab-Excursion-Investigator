# Semiconductor Fab Excursion Investigator

*Codename: FAB-SENTRY.*

**Prototype built and evaluated on synthetic fab data. Next step: a pilot on real fab data. Fab teams interested in piloting it are welcome to get in touch.**
Assistive investigator for ultra-pure-water (UPW), bulk-gas and airborne-molecular-contamination (AMC) excursions in a semiconductor fab.

**Verdict firewall:** the AI proposes a likely cause, deterministic code decides PASS / INDETERMINATE / FAIL,
a named human signs. Outputs are unofficial drafts until a person records a decision.

## What it contains
- Synthetic fab simulator: 14 scenarios with known root causes, 10 core and 4 hard (`python simulator.py`)
- Deterministic guard-band and calibration logic (`guardband.py`)
- Guardrails: prompt-injection sandbox for operator notes AND for free text returned by tools (`sandbox.py`),
  numeric-consistency validator, directive-wording check, citation check (`validator.py`)
- Nine tools as plain functions, served in-process (LangChain) and over MCP stdio (`tools_core.py`, `tools.py`, `mcp_server.py`)
- Hybrid RAG over a synthetic O&M knowledge base: BM25 + embeddings, reciprocal rank fusion; the index records the embedding
  model name, vector dimension and corpus hash and rebuilds itself when any of them changes (`rag.py`, `kb/`)
- Three memory tiers: working (LangGraph state), episodic (human-approved past cases only, `memory.py`), semantic (knowledge base)
- Human sign-off gate and keyed-HMAC audit chain (`signoff.py`, `audit.py`)
- PDF dossier, every block a wrapped paragraph, draft and signed variants (`dossier.py`)
- LangGraph agent: ingress -> agent <-> tools -> draft -> validate -> finish, Gemini only (`graph.py`, `nodes.py`)
- Streamlit UI with three clearly labelled modes: Replay of a recorded live run, Scripted offline demo (no AI), Live Gemini

## Windows setup (VS Code terminal)
```
python -m venv .venv
Set-ExecutionPolicy -Scope Process Bypass
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env      (then paste GEMINI_API_KEY and FAB_SENTRY_HMAC_SECRET)
python simulator.py
python check_setup.py
streamlit run app.py
```
Generate the HMAC secret with: `python -c "import secrets; print(secrets.token_hex(32))"`.
Record real runs for Replay mode: `python record_trace.py --scenario S01` (or `--all`).

## How sign-off works
After an investigation the reviewer enters a name and role and chooses Approve, Reject or Request more evidence.
Approve is refused if the draft failed the numeric-consistency check. Each decision is appended to a keyed-HMAC chain
(`audit/chain.jsonl`); editing, removing or reordering an entry breaks verification. Only an approved, unmodified run
can be written into episodic memory. The audit chain is **tamper-evident, not immutable**, and names are typed in
without authentication: this demonstrates the pattern and is not a validated electronic signature.

## Honest limits
- Limits come from the project blueprint and are tagged **to be verified against the standard**; SEMI documents are paid and have not been checked.
- The knowledge base is original synthetic guidance written for this prototype. It is not a SEMI standard or vendor documentation.
- Offline mode (no Gemini key) uses hashing embeddings, which retrieve less well than Gemini embeddings.
- No cross-encoder reranker. Prompt-injection scanning is pattern-based: a first line of defence, not a guarantee.
- The scripted offline demo uses rules, not an AI model. Its 10/10 result is a wiring check, not an accuracy claim.
- Accuracy figures are in the Results section below and are limited to synthetic data and small samples.
- Streamlit Community Cloud storage is ephemeral; audit chain, memory and runs would be lost on restart there.

Copyright (c) 2026 Rohit Kumar. All rights reserved.

## Stage 3: evaluation (first version)

Scores the agent against ground truth the model never sees. Commands (run from the project folder, venv active):

```
python -m evalkit scan                      # free: injection scanner + verdict-invariance checks, no model calls
python -m evalkit run --kind rules          # free: rules baseline
python -m evalkit run --kind agent --max-calls 150
python -m evalkit run --kind oneshot --max-calls 60
python -m evalkit attacks-live --max-calls 60
python -m evalkit report                    # writes EVAL_RESULTS_Claude.md
```

* Defaults: scenarios S01,S05,S07,S08,S09, 3 runs each, fast model settings from `.env`.
* Every model call is counted and spaced (`--min-interval`, default 4 s). When the budget is reached the batch stops;
  finished runs are kept, so run the same command again later to continue.
* Pass/miss targets are in `evalkit/targets.json`, written before measuring. Do not edit them after seeing results.
* Evaluation uses an empty scratch memory, so your approved cases do not leak into scored runs.
* Honest limits are printed at the end of every report. Synthetic data, small samples, rules baseline not independent.


## Results (first version, 23 November 2026)

Setup: 14 synthetic scenarios x 3 live runs, Gemini `gemini-3.5-flash-lite` for both roles, scored by code against ground truth
the model never sees. Targets were written before measuring (`evalkit/targets.json`). Full tables: `EVAL_RESULTS_Claude.md`.

| Run set | Root cause correct (42 runs) | 95% range | Passed the validator |
|---|---|---|---|
| Agent (model chooses tools) | 41/42 (30/30 core, 11/12 hard) | 88-100% | 41/42 |
| One-shot (fixed tool plan, one model call) | 40/42 (30/30 core, 10/12 hard) | 84-99% | 38/42 |
| Rules engine (hand-written) | 30/42 (30/30 core, 0/12 hard) | 56-83% | 42/42 |

What this does and does not show:
- On the core scenarios everything scores the same, so they do not separate the methods. On the hard scenarios
  (two suspects, a sensor fault with valid calibration, a tool outage, a time window the rules did not expect) the fixed rules fail every case.
- The agent and the one-shot baseline are not statistically different on cause accuracy (41/42 vs 40/42).
- No run gave a wrong cause with high confidence. When the runtime tool was offline (S13), the flag was raised in 3 of 3 runs.
- One agent run named a root cause without supporting evidence. A validator rule now rejects that, and saved runs are re-scored with it.
- In 12 of 42 agent runs the model never read an upstream sensor trend. The reviewer now sees a note on those runs.
- Injection scanner: 9/9 direct attacks caught, 0/6 evasive ones caught, 1/6 benign notes wrongly blocked. Against the six evasive
  attacks the live model followed none (one run each). Verdicts come from code and cannot be changed by notes.
- Known miss: one S12 run (sensor fault with valid calibration) did not read the upstream sensors and chose the UV lamp.
- The knowledge base was written by the author and contains hints close to some scenarios, so the test measures retrieval and
  application of that guidance, not unaided expertise.
- Synthetic data, small samples, one model, one day. Not evidence of performance on a real fab.

Reproduce: `python -m evalkit scan`, `python -m evalkit run --kind agent --scenarios all`, `python -m evalkit report`.

## Public demo
Set `FAB_SENTRY_PUBLIC_DEMO=1` (Streamlit Cloud: add it under Secrets). The app then offers only Replay and Scripted modes,
hides Live Gemini and sign-off, and reads recorded runs from `demo_traces/`. Create them with `python make_demo_traces.py`;
it copies run 1 of each scenario, chosen in advance and not by outcome.

## Pilot with me
If you run a semiconductor fab, a utilities team or a facilities group and want to see this on your own data:
- **What I would need:** a read-only export of UPW or gas sensor history, plus maintenance records. No live connection to the fab.
- **What you get:** the same investigator run on your data, with a scored report like the one in this repository.
- **How to reach me:** Rohit Kumar, LinkedIn: www.linkedin.com/in/ROHITG41
