"""make_architecture_Claude.py - draws docs/architecture_Claude.png with Pillow only (no browser needed).

Run from the project folder:   python docs/make_architecture_Claude.py
Layout is in units of a 1600-wide canvas, drawn at 2x. The signature is added by brand_image_Claude.py
in two quiet spots: upper left (under the subtitle) and lower right (above the evaluation box).
"""
from __future__ import annotations

import sys
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parent))
from brand_image_Claude import brand  # noqa: E402

S = 2                      # drawing scale
W, H = 1600, 922           # canvas in layout units
INK, MUTED, SLATE = "#0f172a", "#475569", "#334155"
COLS = [
    ("1", "INGRESS", "#1d4ed8", ["Alarm and sensor history", "CMMS and maintenance logs", "Operator notes (untrusted)",
                                  "Injection sandbox scans notes and tool text"]),
    ("2", "DETERMINISTIC CODE", "#b45309", ["Guard-band and calibration logic", "Limits with instrument uncertainty",
                                             "Verdict: PASS / INDETERMINATE / FAIL", "The AI cannot change the verdict"]),
    ("3", "AI AGENT (GEMINI)", "#047857", ["LangGraph: agent and tools loop", "Nine tools (in-process and MCP)",
                                            "Hybrid RAG: BM25 + embeddings", "Memory: working, episodic, semantic",
                                            "Drafts a likely root cause"]),
    ("4", "VALIDATOR", "#7c3aed", ["Numbers match the tool results", "No directive wording",
                                    "Citations exist in the knowledge base", "Cause must be a supported hypothesis",
                                    "Evidence-quality flags and notes"]),
    ("5", "HUMAN SIGN-OFF", "#be123c", ["Named reviewer approves, rejects", "or asks for more evidence",
                                         "Keyed-HMAC audit chain", "PDF dossier, draft or signed",
                                         "Approved cases feed episodic memory"]),
]
# vertical layout (units): the gap between the subtitle and the Streamlit bar holds the left signature
SUBTITLE_Y, BAR_Y, BOX_Y = 100, 150, 212
BW, BH, GAP, X0 = 292, 380, 28, 14


def font(size: int, bold: bool = False):
    names = ["arialbd.ttf", "DejaVuSans-Bold.ttf"] if bold else ["arial.ttf", "DejaVuSans.ttf"]
    for n in names:
        try:
            return ImageFont.truetype(n, int(size * S))
        except OSError:
            continue
    return ImageFont.load_default(int(size * S))


def main(out: str = "docs/architecture_Claude.png") -> None:
    img = Image.new("RGB", (W * S, H * S), "#f8fafc")
    d = ImageDraw.Draw(img)

    def box(x, y, w, h, r, **kw):
        d.rounded_rectangle([x * S, y * S, (x + w) * S, (y + h) * S], radius=r * S, **kw)

    def text(x, y, s, size, fill, bold=False, anchor="ls", max_w=None):
        # shrink the font a little if the line would be wider than max_w (fonts differ between PCs)
        while max_w and size > 11 and d.textlength(s, font=font(size, bold)) > max_w * S:
            size -= 0.5
        d.text((x * S, y * S), s, font=font(size, bold), fill=fill, anchor=anchor)

    def line(pts, fill, width=3, dash=None):
        pts = [(x * S, y * S) for x, y in pts]
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            if not dash:
                d.line([(x1, y1), (x2, y2)], fill=fill, width=int(width * S))
                continue
            length = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
            n = int(length // (dash[0] * S + dash[1] * S)) + 1
            for i in range(n):
                a = i * (dash[0] + dash[1]) * S / length
                b = min(1.0, a + dash[0] * S / length)
                d.line([(x1 + (x2 - x1) * a, y1 + (y2 - y1) * a), (x1 + (x2 - x1) * b, y1 + (y2 - y1) * b)],
                       fill=fill, width=int(width * S))

    def head(x, y, direction, fill=SLATE, size=13):
        tri = {"right": [(x, y), (x - 2 * size, y - size), (x - 2 * size, y + size)],
               "up": [(x, y), (x - size, y + 2 * size), (x + size, y + 2 * size)]}[direction]
        d.polygon([(px * S, py * S) for px, py in tri], fill=fill)

    text(W / 2, 62, "Semiconductor Fab Excursion Investigator: System Architecture", 40, INK, True, "ms")
    text(W / 2, SUBTITLE_Y, "AI proposes the cause. Code decides pass or fail. A named human signs.", 22, MUTED, False, "ms")
    box(40, BAR_Y, W - 80, 42, 8, fill="#e2e8f0")
    text(W / 2, BAR_Y + 28, "Streamlit UI: Replay of a recorded run | Scripted offline demo | Live Gemini (local only)", 19, INK, False, "ms")

    for i, (n, title, col, lines) in enumerate(COLS):
        x = X0 + i * (BW + GAP)
        box(x, BOX_Y, BW, BH, 14, fill="white", outline=col, width=3 * S)
        d.rounded_rectangle([x * S, BOX_Y * S, (x + BW) * S, (BOX_Y + 62) * S], radius=14 * S, fill=col,
                            corners=(True, True, False, False))
        text(x + BW / 2, BOX_Y + 40, f"{n}. {title}", 21, "white", True, "ms", max_w=BW - 24)
        y = BOX_Y + 100
        for item in lines:
            for k, part in enumerate(textwrap.wrap(item, 29)):
                text(x + 18 + (0 if k == 0 else 14), y, ("• " if k == 0 else "") + part, 17, "#1e293b", max_w=BW - 36 - (0 if k == 0 else 14))
                y += 24
            y += 14
        if i < 4:
            ax = x + BW
            line([(ax + 4, BOX_Y + BH / 2), (ax + GAP - 26, BOX_Y + BH / 2)], SLATE)
            head(ax + GAP - 4, BOX_Y + BH / 2, "right")

    bot = BOX_Y + BH
    x3, x4 = X0 + 2 * (BW + GAP) + BW / 2, X0 + 3 * (BW + GAP) + BW / 2
    yy = bot + 34
    line([(x4, bot), (x4, yy), (x3, yy), (x3, bot + 30)], SLATE, 2.5, dash=(8, 6))
    head(x3, bot + 4, "up", size=11)
    text((x3 + x4) / 2, yy + 26, "failed check: feedback and one retry", 16, SLATE, False, "ms")
    x2, x5 = X0 + 1 * (BW + GAP) + BW / 2, X0 + 4 * (BW + GAP) + BW / 2
    line([(x2, bot), (x2, yy + 70), (x5, yy + 70), (x5, bot + 30)], "#b45309", 2.5)
    head(x5, bot + 4, "up", fill="#b45309", size=11)
    text((x2 + x5) / 2, yy + 96, "the verdict goes straight to the dossier: no AI step in between", 16, "#b45309", False, "ms")

    ey = H - 110
    box(40, ey, W - 80, 80, 12, fill="white")
    line([(40, ey), (W - 40, ey), (W - 40, ey + 80), (40, ey + 80), (40, ey)], "#64748b", 2, dash=(8, 6))
    text(W / 2, ey + 38, "Evaluation harness (evalkit): 14 simulated scenarios scored by code against hidden ground truth",
         19, INK, True, "ms")
    text(W / 2, ey + 66, "Agent vs one-shot vs rules baseline | injection scanner tests | verdict-invariance checks | "
         "run metrics: tool calls, errors, rounds, seconds", 17, MUTED, False, "ms")

    tmp = Path(out).with_name("_architecture_unsigned.png")
    img.save(tmp)
    brand(str(tmp), out, left=(40, 130), right=(1560, 802))     # two quiet spots, no dark blocks
    tmp.unlink()
    print("written", out)


if __name__ == "__main__":
    main(*(sys.argv[1:2]))
