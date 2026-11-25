# Scope and limits

- **Data:** all data is simulated. The author wrote the simulator, the scenarios and the knowledge base, which contains hints near some scenarios. Results show the method works on known cases, not how it performs in a real fab. A pilot on real data is the next step.
- **Sample:** 14 scenarios x 3 runs, one model, one day. The agent and the one-shot baseline are not statistically different.
- **Limits and standards:** alarm limits come from the project blueprint and are tagged "to be verified against the standard". SEMI documents are paid and were not checked. The knowledge base is original guidance written for this prototype, not a SEMI standard or vendor documentation.
- **Retrieval:** offline mode uses hashing embeddings, which retrieve less well than Gemini embeddings. There is no cross-encoder reranker.
- **Injection scanning:** pattern-based. It is a first line of defence, not a guarantee. Verdicts are set by code and cannot be changed by notes.
- **Sign-off:** the audit chain is tamper-evident, not immutable, and reviewer names are typed in without authentication. It demonstrates the pattern and is not a validated electronic signature.
- **Scripted offline demo:** uses rules, not AI. Its 10/10 result is a wiring check, not an accuracy claim.
- **Hosting:** Streamlit Community Cloud storage is ephemeral.
