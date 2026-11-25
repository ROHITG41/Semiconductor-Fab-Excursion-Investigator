"""dossier.py - PDF investigation dossier (ReportLab platypus, every text block is a wrapped Paragraph).

Unsigned drafts carry an UNOFFICIAL DRAFT banner. A SIGNED dossier lists the human decision, the run digest and the
audit-chain head. Signed means 'a named person recorded a decision in the demo chain', not a validated e-signature.
"""
from __future__ import annotations

import json
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

import config
from audit import run_digest
from engine import run_metrics_text

SS = getSampleStyleSheet()
BODY = ParagraphStyle("body", parent=SS["BodyText"], fontSize=9, leading=12)
SMALL = ParagraphStyle("small", parent=BODY, fontSize=7.5, leading=9.5, textColor=colors.HexColor("#444444"))
CELL = ParagraphStyle("cell", parent=BODY, fontSize=8, leading=10)
H1 = ParagraphStyle("h1", parent=SS["Heading1"], fontSize=15, spaceAfter=4)
H2 = ParagraphStyle("h2", parent=SS["Heading2"], fontSize=11, spaceBefore=8, spaceAfter=3, textColor=colors.HexColor("#0F2744"))
AUTHOR_LINE = ("<b>Prepared by:</b> Rohit Kumar, PMP, CEng (India), CEA, FSEr (T\u00dcV) | Mission-Critical Infrastructure & Systems Engineering Specialist<br/>"
               "<b>Contact:</b> grohit41@gmail.com | LinkedIn: linkedin.com/in/ROHITG41 | X: @RohitG_AI | "
               "<b>Repository:</b> github.com/ROHITG41/Semiconductor-Fab-Excursion-Investigator")
FOOT_RIGHTS = "Copyright (c) 2026 Rohit Kumar. All rights reserved. For pilots or collaboration: grohit41@gmail.com | linkedin.com/in/ROHITG41 | X @RohitG_AI"
BANNER = ParagraphStyle("banner", parent=BODY, alignment=TA_CENTER, fontSize=10, leading=13, textColor=colors.white)


def P(text, style=BODY):
    return Paragraph(escape(str(text)), style)      # escape: operator text may contain < > &


def _table(rows, widths, header=True):
    data = [[P(c, CELL) for c in r] for r in rows]
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    st = [("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9CA3AF")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]
    if header:
        st.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E0F2FE")))
    t.setStyle(TableStyle(st))
    return t


def _banner(text, color):
    t = Table([[Paragraph(escape(text), BANNER)]], colWidths=[180 * mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(color)),
                           ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    return t


_WM_CACHE = {}


def _watermark_image():
    """A transparent page-sized PNG with the author's name and X handle tiled diagonally (cached)."""
    if "img" not in _WM_CACHE:
        from PIL import Image, ImageDraw, ImageFont
        w, h = 827, 1169                                    # A4 at 100 dpi
        font = None
        for n in ("arialbd.ttf", "DejaVuSans-Bold.ttf"):
            try:
                font = ImageFont.truetype(n, 34)
                break
            except OSError:
                continue
        font = font or ImageFont.load_default(34)
        layer = Image.new("RGBA", (int(w * 1.6), int(h * 1.6)), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        for row, y in enumerate(range(0, layer.size[1], 230)):
            for x in range(-300, layer.size[0], 520):
                d.text((x + (260 if row % 2 else 0), y), "Rohit Kumar | @RohitG_AI", font=font, fill=(71, 85, 105, 24))
        layer = layer.rotate(30, resample=Image.BICUBIC)
        ox, oy = (layer.size[0] - w) // 2, (layer.size[1] - h) // 2
        buf = BytesIO()
        layer.crop((ox, oy, ox + w, oy + h)).save(buf, format="PNG")
        buf.seek(0)
        _WM_CACHE["img"] = ImageReader(buf)
    return _WM_CACHE["img"]


def _footer(signed: bool):
    label = "SIGNED (demo chain) - SIMULATED DATA PORTFOLIO PROTOTYPE" if signed else "UNOFFICIAL DRAFT - NOT SIGNED - SIMULATED DATA"

    def draw(canvas, doc):
        canvas.saveState()
        # faint diagonal signature across the page, drawn first so the content sits on top (an image, so it
        # never mixes into the page's selectable text)
        canvas.drawImage(_watermark_image(), 0, 0, width=210 * mm, height=297 * mm, mask="auto")
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#555555"))
        canvas.drawString(15 * mm, 11.5 * mm, f"Semiconductor Fab Excursion Investigator | {label}")
        canvas.drawRightString(195 * mm, 11.5 * mm, f"Page {doc.page}")
        canvas.setFont("Helvetica", 6.5)
        canvas.drawString(15 * mm, 7.5 * mm, FOOT_RIGHTS)
        if not signed:
            canvas.setFont("Helvetica-Bold", 54)
            canvas.setFillColor(colors.Color(0.8, 0.1, 0.1, alpha=0.08))
            canvas.translate(105 * mm, 148 * mm)
            canvas.rotate(45)
            canvas.drawCentredString(0, 0, "UNOFFICIAL COPY")
        canvas.restoreState()
    return draw


def build_dossier(run, final_entry: dict | None = None, chain_head: str | None = None, chain_ok: bool | None = None) -> bytes:
    signed = bool(final_entry and final_entry["action"] == "APPROVE")
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=14 * mm, bottomMargin=20 * mm,
                            title=f"Fab excursion dossier {run.run_id}", author="Semiconductor Fab Excursion Investigator (prototype)")
    t, a = run.triage, run.alarm
    s = [P("Fab excursion investigation dossier", H1), Paragraph(AUTHOR_LINE.replace('&', '&amp;'), SMALL), Spacer(1, 3), P(config.DATA_NOTICE, SMALL), Spacer(1, 4)]
    if signed:
        s.append(_banner(f"APPROVED by {final_entry['actor']} ({final_entry['role']}) at {final_entry['timestamp_utc']}", "#166534"))
    elif final_entry:
        s.append(_banner(f"{final_entry['action']} by {final_entry['actor']} ({final_entry['role']})", "#991B1B"))
    else:
        s.append(_banner("UNOFFICIAL DRAFT - awaiting human review", "#B45309"))
    s += [Spacer(1, 6), _table([["Run", run.run_id], ["Scenario", run.scenario_id], ["Mode", run.mode],
                                ["Models", json.dumps(run.models)], ["Alarm", f"{a['description']} ({a['triggered_at']})"]],
                               [30 * mm, 150 * mm], header=False)]

    s.append(P("1. Deterministic assessment (computed by code, not by AI)", H2))
    s.append(_table([["Parameter", "Reading", "Limit", "Uncertainty band", "Margin", "Calibration", "Verdict"],
                     [t["parameter"], f"{t['measured']} {t['unit']}", f"{t['limit']} ({t['direction']})",
                      f"{t['band_lower']} to {t['band_upper']}", t["margin"],
                      t["calibration_note"], t["verdict"]]],
                    [32 * mm, 22 * mm, 22 * mm, 30 * mm, 14 * mm, 38 * mm, 22 * mm]))
    s.append(P(f"Limit source: {t['limit_source']}", SMALL))
    s.append(P(run.hold_advisory))

    s.append(P("2. Draft investigation (written by the AI, checked by code)", H2))
    if run.report:
        r = run.report
        s.append(P(f"Most likely cause: {r.root_cause_code.value} | confidence: {r.confidence}"))
        s.append(P(r.narrative))
        s.append(P("Recommended actions (for qualified engineer review):"))
        s += [P(f"- {x}") for x in r.recommended_actions]
        s.append(_table([["Hypothesis", "Status", "Evidence"]] +
                        [[h.code.value, h.status, ", ".join(h.evidence_ids)] for h in r.hypotheses], [70 * mm, 35 * mm, 75 * mm]))
        if r.knowledge_base_citations:
            s.append(P("Knowledge-base citations: " + ", ".join(r.knowledge_base_citations), SMALL))
    else:
        s.append(P("No report was produced."))
    s.append(P(("Numeric-consistency check: PASSED" if run.validation.ok else
                "Numeric-consistency check: FAILED - " + "; ".join(run.validation.violations))))

    if run.quality_flags:
        s.append(P("Evidence-quality flags (computed by code)", H2))
        s += [P(f"- {f}") for f in run.quality_flags]

    if run.quality_notes:
        s += [P(f"Note: {n}", SMALL) for n in run.quality_notes]
    s.append(P(run_metrics_text(run), SMALL))

    s.append(P("3. Operator notes (untrusted data)", H2))
    if run.notes_scan["blocked"]:
        s.append(P(f"Possible prompt injection detected ({', '.join(run.notes_scan['hits'])}). Text was withheld from the AI.", BODY))
    s.append(P(run.notes_scan["original"] or "(none)", SMALL))

    s.append(P("4. Evidence appendix (verbatim tool results)", H2))
    for e in run.evidence:
        out = json.dumps(e.output, ensure_ascii=True)
        out = out if len(out) <= 900 else out[:900] + " ... [truncated in PDF]"
        s.append(KeepTogether([P(f"{e.id}  {e.tool}  {json.dumps(e.args)}", BODY), P(out, SMALL), Spacer(1, 3)]))

    s.append(P("5. Record integrity", H2))
    rows = [["Run digest (SHA-256)", run_digest(run)]]
    if final_entry:
        rows += [["Decision", f"{final_entry['action']} by {final_entry['actor']} ({final_entry['role']})"],
                 ["Reviewer comment", final_entry["comment"] or "(none)"], ["Audit entry", f"#{final_entry['seq']}  HMAC {final_entry['hmac']}"],
                 ["Digest at signing", final_entry["run_digest"]],
                 ["Digest matches signed record", "YES" if final_entry["run_digest"] == run_digest(run) else "NO - record changed after signing"]]
    if chain_head:
        rows.append(["Audit chain head", chain_head])
    if chain_ok is not None:
        rows.append(["Chain verification", "OK" if chain_ok else "FAILED"])
    s.append(_table(rows, [45 * mm, 135 * mm], header=False))
    s.append(P("The audit chain is tamper-evident, not immutable, and reviewer names are typed in without authentication. "
               "This is a demonstration of the pattern, not a validated electronic signature or a GMP/fab-qualified record.", SMALL))
    doc.build(s, onFirstPage=_footer(signed), onLaterPages=_footer(signed))
    return buf.getvalue()
