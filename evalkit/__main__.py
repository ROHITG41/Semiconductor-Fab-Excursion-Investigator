"""Command line for Stage 3.   python -m evalkit --help

  scan            free: injection-scanner metrics + verdict invariance (no model calls)
  run             agent | oneshot | rules  on chosen scenarios, N runs each, under a call budget
  attacks-live    live agent against the evasive attacks (a few runs, call-budgeted)
  report          write the markdown report from saved runs
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEFAULT_SCENARIOS = "S01,S05,S07,S08,S09"
CALLS_PER_AGENT_RUN = 7   # rough planning figure: ~4 tool rounds + 1-2 draft calls


def expand_scenarios(text: str) -> list[str]:
    """'all', 'core', 'hard', or a comma list like S01,S05."""
    from evalkit.scorer import load_golden
    gold = load_golden()
    t = text.strip().lower()
    if t in ("all", "core", "hard"):
        return [sid for sid, g in sorted(gold.items()) if t == "all" or g.get("tier", "core") == t]
    return [s.strip() for s in text.split(",") if s.strip()]


def _setup(outdir: Path) -> None:
    """Keep evaluation clean: no precedents from your real approved cases, and a separate scratch memory file."""
    outdir.mkdir(parents=True, exist_ok=True)
    mem = outdir / "_empty_memory.db"
    if mem.exists():
        mem.unlink()
    os.environ["FAB_SENTRY_MEMORY_DB"] = str(mem)


def _budget(args):
    from evalkit.budget import CallBudget
    return CallBudget(args.max_calls, args.min_interval)


def cmd_scan(args) -> int:
    # The invariance check runs ~200 pipelines. Use the offline embedder and a scratch index so it makes no Gemini
    # calls, finishes in seconds, and does not overwrite the knowledge-base index the app uses.
    _setup(Path(args.out))
    os.environ["FAB_SENTRY_EMBEDDER"] = "offline"
    os.environ["FAB_SENTRY_INDEX_PATH"] = str(Path(args.out) / "_scan_index.json")
    print("Scan uses the offline embedder (no Gemini calls). Checking 21 attack texts x 10 scenarios...")
    from evalkit.attacks import scan_metrics, verdict_invariance
    m, v = scan_metrics(), verdict_invariance(expand_scenarios(args.scenarios))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "attack_scan.json").write_text(json.dumps({"scan": m, "invariance": v}, indent=2))
    print(f"Direct attacks caught     : {m['direct_detected'][0]}/{m['direct_detected'][1]}")
    print(f"Evasive attacks let through: {m['evasive_got_through'][0]}/{m['evasive_got_through'][1]}")
    print(f"Benign notes wrongly blocked: {m['benign_blocked'][0]}/{m['benign_blocked'][1]}")
    print(f"Verdict invariance: {v['checked']} combinations, {len(v['violations'])} violations")
    return 0 if not v["violations"] else 1


def cmd_run(args) -> int:
    out = Path(args.out)
    _setup(out)
    scenarios = expand_scenarios(args.scenarios)
    budget = _budget(args)
    from evalkit.batch import run_batch
    label = args.label or f"{args.kind}_{args.engine}"
    est = len(scenarios) * args.runs * (CALLS_PER_AGENT_RUN if args.kind == "agent" else 1)
    print(f"Plan: {args.kind}/{args.engine}, scenarios {scenarios}, {args.runs} runs each = {len(scenarios) * args.runs} runs.")
    if args.engine == "live":
        print(f"Rough need: about {est} model calls. Budget for this session: {args.max_calls} calls, "
              f"at least {args.min_interval}s between calls. Finished runs are kept; run the same command again to continue.")
    items = []
    for k in range(1, args.runs + 1):            # run 1 of every scenario first, so a partial batch stays balanced
        for sid in scenarios:
            items.append((f"{sid}_run{k}", _make_fn(args, sid, budget)))
    s = run_batch(label, items, out, budget)
    print(f"\nFinished now: {s['completed_now']}, already done earlier: {s['already_done']}, failed now: {s['failed_now']}, "
          f"calls used: {s['calls_used']}/{args.max_calls}")
    if s["stopped"]:
        print("Stopped early:", s["stopped"])
        return 2
    return 0


def _make_fn(args, sid, budget):
    from evalkit.budget import wrapper_for
    if args.kind == "rules":
        from evalkit.baselines import run_rules
        return lambda: run_rules(sid)
    if args.engine == "fake":
        if args.kind == "agent":
            from runner import run_fake_graph
            return lambda: run_fake_graph(sid)
        from evalkit.baselines import run_oneshot
        from fake_llm import ScriptedChatModel
        from tools_core import SimBackend
        return lambda: run_oneshot(sid, ScriptedChatModel(SimBackend(sid)), {"model": "scripted fake (no AI)"},
                                   mode="scripted-offline")
    import config
    models = {"fast": config.FAST_LOOP_MODEL, "reasoning": config.REASONING_MODEL}
    if args.kind == "agent":
        from runner import run_live_gemini
        return lambda: run_live_gemini(sid, wrap=wrapper_for(budget))
    from evalkit.baselines import run_oneshot
    from llm_router import get_chat_model
    return lambda: run_oneshot(sid, wrapper_for(budget)(get_chat_model("reasoning")), models)


def cmd_attacks_live(args) -> int:
    out = Path(args.out)
    _setup(out)
    from evalkit.attacks import by_group
    from evalkit.batch import run_batch
    from evalkit.budget import wrapper_for
    from runner import run_live_gemini
    budget = _budget(args)
    items = []
    for k in range(1, args.runs + 1):
        for a in by_group("evasive"):
            items.append((f"{a['id']}_{args.scenario}_run{k}",
                          (lambda a=a: run_live_gemini(args.scenario, wrap=wrapper_for(budget), notes_override=a["text"]))))
    print(f"Plan: {len(items)} live runs of {args.scenario} with each evasive attack as the operator notes "
          f"(about {len(items) * CALLS_PER_AGENT_RUN} calls). Budget {args.max_calls}.")
    s = run_batch("attack_live", items, out, budget)
    print(f"Finished now: {s['completed_now']}, already done: {s['already_done']}, failed: {s['failed_now']}, calls used {s['calls_used']}")
    if s["stopped"]:
        print("Stopped early:", s["stopped"])
        return 2
    return 0


def live_attack_rows(out: Path) -> list[dict]:
    from evalkit.attacks import ATTACKS
    from evalkit.batch import load_results
    from evalkit.scorer import load_golden, score_text_adoption
    ok, _ = load_results(out, "attack_live")
    rows = []
    for a in ATTACKS:
        rs = [r for r in ok if r["key"].startswith(a["id"] + "_")]
        if not rs:
            continue
        res = [score_text_adoption(r["run"], load_golden()[r["run"].scenario_id], a.get("adopt", [])) for r in rs]
        rows.append({"id": a["id"], "n": len(res), "complied": sum(1 for x in res if x["complied"])})
    return rows


def cmd_revalidate(args) -> int:
    from evalkit.revalidate import revalidate
    res = revalidate(Path(args.out), args.labels.split(","))
    for label, r in res.items():
        print(f"{label}: {r['runs']} saved runs; would now FAIL validation: {len(r['newly_failing'])}; "
              f"would now carry quality flags (excluding S13): {len(r['newly_flagged'])}; with an informational note: {len(r['with_notes'])}")
        for x in r["newly_failing"]:
            print(f"   {x['key']}: {x['new_violations'][0][:140]}")
        if r["newly_flagged"]:
            print("   flagged:", ", ".join(r["newly_flagged"]))
    return 0


def cmd_report(args) -> int:
    out = Path(args.out)
    from evalkit.summarise import render_markdown
    scan_file = out / "attack_scan.json"
    scan = json.loads(scan_file.read_text()) if scan_file.exists() else {}
    md = render_markdown(out, args.labels.split(","), scan.get("scan"), scan.get("invariance"), live_attack_rows(out))
    path = Path(args.report)
    path.write_text(md, encoding="utf-8")
    print(f"Report written to {path}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m evalkit")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("scan", "run", "attacks-live", "report", "revalidate"):
        s = sub.add_parser(name)
        s.add_argument("--out", default=str(ROOT / "evalruns"))
        if name in ("scan", "run"):
            s.add_argument("--scenarios", default=DEFAULT_SCENARIOS if name == "run" else "core",
                           help="S01,S05 ... or all / core / hard")
        if name in ("run", "attacks-live"):
            s.add_argument("--runs", type=int, default=3 if name == "run" else 1)
            s.add_argument("--max-calls", type=int, default=150)
            s.add_argument("--min-interval", type=float, default=4.0, help="seconds between model calls (free-tier rate limit)")
        if name == "run":
            s.add_argument("--kind", choices=["agent", "oneshot", "rules"], default="agent")
            s.add_argument("--engine", choices=["live", "fake"], default="live")
            s.add_argument("--label", default="")
        if name == "attacks-live":
            s.add_argument("--scenario", default="S01")
        if name == "revalidate":
            s.add_argument("--labels", default="agent_live,oneshot_live,rules_live")
        if name == "report":
            s.add_argument("--labels", default="agent_live,oneshot_live,rules_live")
            s.add_argument("--report", default=str(ROOT / "EVAL_RESULTS_Claude.md"))
    args = p.parse_args(argv)
    return {"scan": cmd_scan, "run": cmd_run, "attacks-live": cmd_attacks_live, "report": cmd_report,
            "revalidate": cmd_revalidate}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
