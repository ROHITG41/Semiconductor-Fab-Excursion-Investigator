"""tools_core.py - plain-Python tool functions over the synthetic fab (the single source of truth).

The same functions are exposed (a) as in-process LangChain tools (tools.py, default for Streamlit
on Windows) and (b) as an official-SDK MCP stdio server (mcp_server.py). Swapping the simulator for
a real historian/CMMS later means replacing this adapter only.
This module never reads the ground-truth file.
"""
from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path
from typing import Optional

from config import DATA_DIR
from guardband import assess
from sandbox import clean_free_text
from schemas import SensorSpec


class SimBackend:
    def __init__(self, scenario_id: str, data_dir: Path = DATA_DIR, kb=None, memory=None, notes_override=None):
        self.scenario_id = scenario_id
        self.kb = kb            # HybridIndex; default built lazily from rag.default_index()
        self.memory = memory    # EpisodicMemory; default opened lazily
        d = Path(data_dir)
        self.sensors = {s["tag"]: SensorSpec(**s) for s in json.loads((d / "sensors.json").read_text())}
        graph = json.loads((d / "pid_graph.json").read_text())
        self.down: dict[str, list[str]] = {}
        self.up: dict[str, list[str]] = {}
        for a, b in graph["edges"]:
            self.down.setdefault(a, []).append(b)
            self.up.setdefault(b, []).append(a)
        cm = json.loads((d / "cmms_logs.json").read_text())[scenario_id]
        self.work_orders = cm["work_orders"]
        self.runtime = cm["runtime"]
        self.outages = set(cm.get("tool_outages", []))      # scenario-defined tool failures (degraded-operation tests)
        for tag, ov in cm["calibration_overrides"].items():
            self.sensors[tag] = self.sensors[tag].model_copy(update=ov)
        self.alarm = json.loads((d / "alarms.json").read_text())[scenario_id]
        self.notes = (notes_override if notes_override is not None
                      else json.loads((d / "handover_notes.json").read_text())[scenario_id])   # override: evaluation attack tests only
        self.series: dict[str, list[tuple[str, float]]] = {}
        with open(d / "synthetic_scada.csv", newline="") as f:
            for r in csv.DictReader(f):
                if r["scenario_id"] == scenario_id:
                    self.series.setdefault(r["tag"], []).append((r["timestamp"], float(r["value"])))
        self.today = date.fromisoformat(self.alarm["triggered_at"][:10])

    # ---- helpers ----
    def _known_assets(self) -> list[str]:
        return sorted(set(self.up) | set(self.down))

    def _asset_error(self, asset_id: str) -> dict:
        return {"error": f"unknown asset {asset_id}", "known_assets": self._known_assets(),
                "hint": "use an asset_id returned by query_sensor_window (not a sensor tag) or one from known_assets"}

    def _vals(self, tag: str, minutes_back: int) -> Optional[list[tuple[str, float]]]:
        if tag not in self.series:
            return None
        return self.series[tag][-max(1, int(minutes_back)):]

    @staticmethod
    def _r(x: float) -> float:
        return round(float(x), 4)

    # ---- tools ----
    def query_sensor_window(self, tag: str, minutes_back: int = 120) -> dict:
        """Summary statistics for one SENSOR over the last N minutes before the alarm.
        tag: a sensor tag such as UPW_B_TOC_POU or UPW_B_UV_INT (starts with UPW_/N2_/AMC_). The result includes the asset_id the sensor sits on."""
        v = self._vals(tag, minutes_back)
        if v is None:
            return {"error": f"unknown tag {tag}", "known_tags": sorted(self.series)}
        xs = [p[1] for p in v]
        spec = self.sensors[tag]
        return {"tag": tag, "parameter": spec.parameter, "unit": spec.unit, "asset_id": spec.asset_id,
                "minutes_back": len(xs), "first": self._r(xs[0]), "last": self._r(xs[-1]),
                "min": self._r(min(xs)), "max": self._r(max(xs)), "mean": self._r(sum(xs) / len(xs)),
                "window_start": v[0][0], "window_end": v[-1][0]}

    def compute_rate_of_change(self, tag: str, minutes_back: int = 120) -> dict:
        """Least-squares slope per hour over the last N minutes, plus first-half vs second-half means."""
        v = self._vals(tag, minutes_back)
        if v is None:
            return {"error": f"unknown tag {tag}"}
        xs = [p[1] for p in v]
        n = len(xs)
        if n < 3:
            return {"error": "need at least 3 samples"}
        t = list(range(n))
        mt, mx = sum(t) / n, sum(xs) / n
        slope = sum((a - mt) * (b - mx) for a, b in zip(t, xs)) / sum((a - mt) ** 2 for a in t)
        h = n // 2
        return {"tag": tag, "unit": self.sensors[tag].unit, "minutes_back": n,
                "slope_per_hour": self._r(slope * 60), "mean_first_half": self._r(sum(xs[:h]) / h),
                "mean_second_half": self._r(sum(xs[h:]) / (n - h))}

    def check_guardband_and_cal(self, tag: str) -> dict:
        """Deterministic verdict for the latest reading (guard band + calibration). Verdicts come only from here."""
        if tag not in self.sensors or tag not in self.series:
            return {"error": f"unknown tag {tag}", "known_tags": sorted(self.series)}
        return assess(self.sensors[tag], self.series[tag][-1][1], self.today)

    def trace_upstream_loop(self, asset_id: str) -> dict:
        """All assets upstream of an ASSET, nearest first, with the sensor tags installed on each.
        asset_id: an equipment id such as POU_LITHO_1, UV_B or POLISH_A. NEVER a sensor tag (UPW_..._POU is a tag, not an asset); get the asset_id from query_sensor_window."""
        if asset_id not in self.up and asset_id not in self.down:
            return self._asset_error(asset_id)
        order, frontier, seen = [], [asset_id], {asset_id}
        while frontier:
            nxt = []
            for a in frontier:
                for u in self.up.get(a, []):
                    if u not in seen:
                        seen.add(u); order.append(u); nxt.append(u)
            frontier = nxt
        return {"asset_id": asset_id, "upstream": [{"asset_id": a, "sensor_tags": self._tags_on(a)} for a in order]}

    def get_asset_dependencies(self, asset_id: str) -> dict:
        """Direct upstream and downstream neighbours of an ASSET.
        asset_id: an equipment id such as POU_LITHO_1 or UV_B, never a sensor tag."""
        if asset_id not in self.up and asset_id not in self.down:
            return self._asset_error(asset_id)
        return {"asset_id": asset_id, "upstream": self.up.get(asset_id, []),
                "downstream": self.down.get(asset_id, []), "sensor_tags": self._tags_on(asset_id)}

    def get_recent_work_orders(self, asset_id: str = "", hours: int = 72) -> dict:
        """Maintenance work orders within the last N hours (optionally for one asset).
        asset_id: optional equipment id (not a sensor tag); leave empty for all assets."""
        if asset_id and asset_id not in self.up and asset_id not in self.down:
            return self._asset_error(asset_id)
        wos = []
        for w in self.work_orders:
            if w["hours_ago"] <= hours and (not asset_id or w["asset"] == asset_id):
                text, hits = clean_free_text(w["text"])      # work-order text is untrusted free text
                wos.append({**w, "text": text, "flagged": bool(hits)})
        return {"asset_id": asset_id or "ALL", "hours": hours, "count": len(wos), "work_orders": wos}

    def get_resin_and_lamp_runtime(self, asset_id: str) -> dict:
        """Runtime hours versus rated life for consumable assets only: UV lamps (UV_A, UV_B), resin beds (POLISH_A, POLISH_B), RO membranes (RO_A, RO_B), N2_PURIFIER, CHEM_FILTER_01.
        asset_id: one of those equipment ids. EDI units, valves, sensors and points of use have no runtime record."""
        if "get_resin_and_lamp_runtime" in self.outages:
            return {"error": "runtime service unavailable (maintenance system offline); try again later or use other evidence"}
        r = self.runtime.get(asset_id)
        if r is None:
            return {"error": f"no runtime record for {asset_id}", "assets_with_records": sorted(self.runtime)}
        return {"asset_id": asset_id, **r, "percent_of_rated_life": round(100.0 * r["hours"] / r["rated_hours"], 1)}

    def search_knowledge_base(self, query: str, k: int = 3) -> dict:
        """Hybrid keyword + embedding search of the synthetic O&M knowledge base. Returns cited chunks."""
        import rag
        idx = self.kb or rag.default_index()
        out = []
        for h in idx.search(str(query), max(1, min(int(k), 5))):
            text, hits = clean_free_text(h["text"])
            out.append({"chunk_id": h["id"], "title": h["title"], "source": h["source"], "text": text,
                        "flagged": bool(hits)})
        return {"query": str(query), "results": out}

    def retrieval_note(self) -> str:
        import rag
        return (self.kb or rag.default_index()).note

    def find_similar_past_cases(self, k: int = 3) -> dict:
        """Human-approved past investigations similar to this alarm tag. Precedents only, never proof."""
        from memory import EpisodicMemory
        mem = self.memory or EpisodicMemory()
        res = mem.search(self.alarm["tag"], max(1, min(int(k), 5)))
        for c in res["cases"]:
            c["reviewer_comment"], _ = clean_free_text(c.get("reviewer_comment", ""))
        return res

    def _tags_on(self, asset_id: str) -> list[str]:
        return sorted(t for t, s in self.sensors.items() if s.asset_id == asset_id and t in self.series)


TOOL_NAMES = ["query_sensor_window", "compute_rate_of_change", "check_guardband_and_cal",
              "trace_upstream_loop", "get_asset_dependencies", "get_recent_work_orders",
              "get_resin_and_lamp_runtime", "search_knowledge_base", "find_similar_past_cases"]
