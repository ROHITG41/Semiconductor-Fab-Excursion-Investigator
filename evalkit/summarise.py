"""summarise.py - turn saved runs into numbers, targets check and a plain-language markdown report."""
from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path

from evalkit.batch import load_results
from evalkit.scorer import load_golden, score_run

TARGETS_PATH = Path(__file__).with_name("targets.json")


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, centre - half), min(1.0, centre + half))


def _pct(k, n):
    return "n/a" if n == 0 else f"{k}/{n} ({100 * k / n:.0f}%)"


def _ci(k, n):
    lo, hi = wilson(k, n)
    return "n/a" if n == 0 else f"{100 * lo:.0f}-{100 * hi:.0f}%"


def aggregate(outdir: Path, label: str) -> dict:
    gold = load_golden()
    ok, bad = load_results(outdir, label)
    rows = [score_run(r["run"], gold[r["run"].scenario_id]) | {"calls": r["calls"]} for r in ok]
    per = {}
    for sid in sorted({r["scenario_id"] for r in rows}):
        rs = [r for r in rows if r["scenario_id"] == sid]
        causes = Counter(r["cause"] for r in rs)
        per[sid] = {"n": len(rs), "cause_ok": sum(r["cause_ok"] for r in rs), "verdict_ok": sum(r["verdict_ok"] for r in rs),
                    "validation_ok": sum(r["validation_ok"] for r in rs),
                    "mean_tool_calls": sum(r["tool_calls"] for r in rs) / len(rs),
                    "mean_model_calls": sum(r["calls"] for r in rs) / len(rs),
                    "runs_with_unrecovered_errors": sum(1 for r in rs if r["unrecovered_errors"] > 0),
                    "runs_with_recovered_errors": sum(1 for r in rs if r["recovered_errors"] > 0),
                    "high_conf_wrong": sum(r["high_confidence_wrong"] for r in rs),
                    "agreement_with_modal_cause": (causes.most_common(1)[0][1] / len(rs)) if len(rs) else 0.0,
                    "causes": dict(causes), "injection_scenario": rs[0]["injection_scenario"],
                    "injection_complied": sum(1 for r in rs if r["injection_complied"]),
                    "culprit_examined": sum(1 for r in rs if r["culprit_examined"])}
    by_tier = {}
    for tier in sorted({r["tier"] for r in rows}):
        tr = [r for r in rows if r["tier"] == tier]
        fe = [r for r in tr if r["flag_expected"]]
        by_tier[tier] = {"n": len(tr), "cause_ok": sum(r["cause_ok"] for r in tr), "verdict_ok": sum(r["verdict_ok"] for r in tr),
                         "validation_ok": sum(r["validation_ok"] for r in tr),
                         "unrec": sum(1 for r in tr if r["unrecovered_errors"] > 0),
                         "high_conf_wrong": sum(r["high_confidence_wrong"] for r in tr),
                         "flag_n": len(fe), "flag_ok": sum(1 for r in fe if r["flag_ok"])}
    n = len(rows)
    inj_rows = [r for r in rows if r["injection_scenario"]]
    tot = {"n": n, "failed_runs": len(bad),
           "cause_ok": sum(r["cause_ok"] for r in rows), "verdict_ok": sum(r["verdict_ok"] for r in rows),
           "validation_ok": sum(r["validation_ok"] for r in rows),
           "unrec": sum(1 for r in rows if r["unrecovered_errors"] > 0),
           "upstream_gap": sum(1 for r in rows if r["upstream_sensor_gap"]),
           "high_conf_wrong": sum(r["high_confidence_wrong"] for r in rows),
           "inj_n": len(inj_rows), "inj_complied": sum(1 for r in inj_rows if r["injection_complied"]),
           "consistency": (sum(p["agreement_with_modal_cause"] for p in per.values() if p["n"] >= 2) /
                           max(1, sum(1 for p in per.values() if p["n"] >= 2))),
           "models": sorted({json.dumps(r["run"].models, sort_keys=True) for r in ok}),
           "modes": sorted({r["run"].mode for r in ok})}
    return {"label": label, "per_scenario": per, "total": tot, "by_tier": by_tier}


def check_targets(agg: dict, targets: dict) -> list[dict]:
    t, rows = agg["total"], []
    n = t["n"]
    tiers = agg.get("by_tier", {})
    core = tiers.get("core")
    if core and core["n"] and "hard" in tiers:        # judge the core targets on the core scenarios only
        t = dict(t, n=core["n"], cause_ok=core["cause_ok"], verdict_ok=core["verdict_ok"], validation_ok=core["validation_ok"],
                 unrec=core["unrec"],
                 high_conf_wrong=core["high_conf_wrong"])
        n = core["n"]

    def add(name, measured_txt, passed, target_txt):
        rows.append({"name": name, "measured": measured_txt, "target": target_txt,
                     "result": "n/a" if passed is None else ("PASS" if passed else "MISS")})
    if n == 0:
        return rows
    add("Root cause correct", _pct(t["cause_ok"], n), t["cause_ok"] / n >= targets["cause_accuracy_min"],
        f">= {targets['cause_accuracy_min']:.0%}")
    add("Code verdict equals ground truth", _pct(t["verdict_ok"], n), t["verdict_ok"] / n >= targets["verdict_agreement_min"],
        f">= {targets['verdict_agreement_min']:.0%}")
    add("Report passed the validator", _pct(t["validation_ok"], n), t["validation_ok"] / n >= targets["validation_pass_min"],
        f">= {targets['validation_pass_min']:.0%}")
    add("Followed an injected instruction", _pct(t["inj_complied"], t["inj_n"]),
        None if t["inj_n"] == 0 else t["inj_complied"] / t["inj_n"] <= targets["injection_complied_max"],
        f"<= {targets['injection_complied_max']:.0%}")
    add("Runs with an uncorrected tool error", _pct(t["unrec"], n), t["unrec"] / n <= targets["runs_with_unrecovered_errors_max"],
        f"<= {targets['runs_with_unrecovered_errors_max']:.0%}")
    add("High confidence but wrong", _pct(t["high_conf_wrong"], n), t["high_conf_wrong"] / n <= targets["high_confidence_wrong_max"],
        f"<= {targets['high_confidence_wrong_max']:.0%}")
    add("Same answer across repeat runs", f"{t['consistency']:.0%}", t["consistency"] >= targets["run_consistency_min"],
        f">= {targets['run_consistency_min']:.0%}")
    h = tiers.get("hard")
    if h and h["n"]:
        add("HARD tier: root cause correct", _pct(h["cause_ok"], h["n"]), h["cause_ok"] / h["n"] >= targets["hard_cause_accuracy_min"],
            f">= {targets['hard_cause_accuracy_min']:.0%}")
        add("HARD tier: high confidence but wrong", _pct(h["high_conf_wrong"], h["n"]),
            h["high_conf_wrong"] / h["n"] <= targets["high_confidence_wrong_max"], f"<= {targets['high_confidence_wrong_max']:.0%}")
        add("HARD tier: flag raised when a tool was down", _pct(h["flag_ok"], h["flag_n"]),
            None if h["flag_n"] == 0 else h["flag_ok"] / h["flag_n"] >= targets["degraded_flag_raised_min"],
            f">= {targets['degraded_flag_raised_min']:.0%}")
    return rows


LIMITS = """\
- The data is **simulated**. I wrote the simulator, the scenarios and the knowledge base. Nothing here shows how the system would do on a real fab's historian and maintenance records.
- The sample is small. Each result is a handful of runs, so the percentage ranges (95% Wilson intervals) are wide. Read "5/5" as "no failure seen yet", not as "never fails".
- The models use fixed sampling settings, so repeated runs of the same scenario can differ. That is why each scenario is run several times.
- The "rules" baseline is a hand-written engine that I tuned on the 10 core scenarios (not on the hard tier). It is a reference, not an independent competitor, and it is fixed, so its 0% on the hard tier shows brittleness, not that a better rule set could not be written.
- The agent and the one-shot baseline are not perfectly like for like: the agent graph may redraft once after a validator failure; the one-shot gets a single draft. Compare their cause accuracy more than their validator pass rate.
- The injection scanner is a pattern matcher. The evasive attacks show what it misses. The protection that holds is architectural: verdicts come from code, and a human signs.
- Results apply only to the model names and dates recorded in this report. A new model version needs a new run.
- Not yet tested on real fab data. Not a GMP, Part 11 or safety-rated system."""


def render_markdown(outdir: Path, labels: list[str], attack_scan: dict | None = None, invariance: dict | None = None,
                    live_attack_rows: list[dict] | None = None) -> str:
    targets = json.loads(TARGETS_PATH.read_text())
    out = ["# FAB-SENTRY evaluation results (first version)", "",
           f"Targets were written on {targets['set_on']}, before any live measurement (evalkit/targets.json).", ""]
    aggs = {l: aggregate(outdir, l) for l in labels}
    out += ["## 1. Headline comparison", "",
            "Core = scenarios with a clear signal. Hard = added in Stage 3 so that a fixed rule list can fail: two suspects, "
            "sensor fault with valid calibration, a tool outage, and a time window the rules did not expect.", "",
            "| Run set | Tier | Runs | Root cause correct | 95% range | Validator passed | Uncorrected tool error | Failed runs (infrastructure) |",
            "|---|---|---|---|---|---|---|---|"]
    for l, a in aggs.items():
        for tier, v in a["by_tier"].items():
            out.append(f"| {l} | {tier} | {v['n']} | {_pct(v['cause_ok'], v['n'])} | {_ci(v['cause_ok'], v['n'])} | "
                       f"{_pct(v['validation_ok'], v['n'])} | {_pct(v['unrec'], v['n'])} | {a['total']['failed_runs']} |")
    for l, a in aggs.items():
        t = a["total"]
        out += ["", f"## 2. Per scenario: {l}", "",
                f"Validity is re-checked with the current validator on every saved run. Runs that never read an upstream sensor trend (shown to the reviewer as a note, not a flag): {_pct(t['upstream_gap'], t['n'])}", "",
                f"Models recorded: {'; '.join(t['models']) or 'none'} | modes: {', '.join(t['modes']) or 'none'}", "",
                "| Scenario | Runs | Cause correct | Verdict correct | Validator passed | Mean tool results | Model calls/run | Uncorrected errors | Recovered errors | Same-answer rate | Causes given |",
                "|---|---|---|---|---|---|---|---|---|---|---|"]
        for sid, p in a["per_scenario"].items():
            out.append(f"| {sid}{' (injection)' if p['injection_scenario'] else ''} | {p['n']} | {_pct(p['cause_ok'], p['n'])} | "
                       f"{_pct(p['verdict_ok'], p['n'])} | {_pct(p['validation_ok'], p['n'])} | {p['mean_tool_calls']:.1f} | "
                       f"{p['mean_model_calls']:.1f} | {p['runs_with_unrecovered_errors']} | {p['runs_with_recovered_errors']} | "
                       f"{p['agreement_with_modal_cause']:.0%} | {', '.join(f'{k}:{v}' for k, v in p['causes'].items())} |")
    first_agent = next((l for l in labels if l.startswith("agent")), None)
    if first_agent:
        out += ["", f"## 3. Targets versus measured ({first_agent})", "", "| Measure | Measured | Target | Result |", "|---|---|---|---|"]
        for r in check_targets(aggs[first_agent], targets):
            out.append(f"| {r['name']} | {r['measured']} | {r['target']} | {r['result']} |")
    if attack_scan:
        s = attack_scan
        out += ["", "## 4. Prompt-injection tests", "",
                "**Scanner (free, deterministic).**",
                f"- Direct attacks caught: {s['direct_detected'][0]}/{s['direct_detected'][1]}",
                f"- Evasive attacks that got past the scanner: {s['evasive_got_through'][0]}/{s['evasive_got_through'][1]} (these reach the model)",
                f"- Benign notes wrongly blocked: {s['benign_blocked'][0]}/{s['benign_blocked'][1]}"]
        blocked_benign = [r["id"] for r in s["rows"] if r["group"] == "benign" and r["blocked"]]
        if blocked_benign:
            out.append(f"- Wrongly blocked: {', '.join(blocked_benign)} (a false alarm only withholds the note and shows a warning; it never hides tool data)")
    if attack_scan:
        out += ["", "Note: in the two scenarios whose handover note contains an injection (S07 and S10) the scanner withholds the "
                "note, so the model never sees the attack text. Their 0% compliance therefore tests the scanner, not the model. "
                "The live evasive-attack table below is the test of the model."]
    if invariance:
        out += ["", f"**Verdict invariance.** {invariance['checked']} combinations of scenario and attack text; violations: {len(invariance['violations'])}. "
                "This holds by construction (code never reads the notes) and guards against future changes. It says nothing about how a model reacts."]
    if live_attack_rows:
        out += ["", "**Live model against evasive attacks (notes reached the model).**", "",
                "| Attack | Runs | Model complied (changed cause or repeated the claim) |", "|---|---|---|"]
        for r in live_attack_rows:
            out.append(f"| {r['id']} | {r['n']} | {r['complied']}/{r['n']} |")
    out += ["", "## 5. Limits you must carry into any claim", "", LIMITS, ""]
    return "\n".join(out)
