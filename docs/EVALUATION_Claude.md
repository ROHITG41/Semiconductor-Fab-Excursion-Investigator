# Evaluation method and commands

Scores the agent against ground truth the model never sees (`data/golden_excursions.json`). Run from the project folder with the virtual environment active.

```
python -m evalkit scan                      # free: injection scanner + verdict-invariance checks
python -m evalkit run --kind rules          # free: rules baseline
python -m evalkit run --kind agent --scenarios all --max-calls 150
python -m evalkit run --kind oneshot --scenarios all --max-calls 60
python -m evalkit attacks-live --max-calls 60
python -m evalkit report                    # writes EVAL_RESULTS_Claude.md
```

- 14 scenarios (10 core, 4 hard), 3 runs each, scored by code. Wilson 95% intervals. Targets in `evalkit/targets.json` were written before measuring.
- Every model call is counted and spaced; when the budget is reached the batch stops and finished runs are kept. Run the same command later to continue.
- Evaluation uses an empty scratch memory so approved cases do not leak into scored runs.
- Baselines: `rules` (hand-written rules engine) and `oneshot` (fixed tool plan, one structured model call, no retry).
