"""Generate MuleShield_Demo.pptx — a 10-slide hackathon deck matching the app theme.

Usage: python tools/make_pptx.py [output_path]
"""

from __future__ import annotations

import sys
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

# Theme (mirrors app/static/styles.css)
NAVY = RGBColor(0x0B, 0x12, 0x20)
PANEL = RGBColor(0x12, 0x1B, 0x2E)
TEAL = RGBColor(0x2D, 0xD4, 0xBF)
TEAL_DIM = RGBColor(0x14, 0xB8, 0xA6)
WHITE = RGBColor(0xE8, 0xEE, 0xF9)
MUTED = RGBColor(0x93, 0xA4, 0xC3)
RED = RGBColor(0xF8, 0x71, 0x71)
AMBER = RGBColor(0xFB, 0xBF, 0x24)
FONT = "Segoe UI"
URL = "https://muleshield-r4zy.onrender.com"

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
BLANK = prs.slide_layouts[6]


def base_slide() -> "Slide":
    s = prs.slides.add_slide(BLANK)
    s.background.fill.solid()
    s.background.fill.fore_color.rgb = NAVY
    return s


def txbox(slide, l, t, w, h, text, size, color=WHITE, bold=False,
          align=PP_ALIGN.LEFT, font=FONT):
    box = slide.shapes.add_textbox(Inches(l), Inches(t), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.name = font
    return box


def header(slide, kicker, title):
    # teal accent bar + kicker + title
    bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.6), Inches(0.55), Inches(0.09), Inches(0.95))
    bar.fill.solid()
    bar.fill.fore_color.rgb = TEAL
    bar.line.fill.background()
    txbox(slide, 0.85, 0.5, 11.5, 0.4, kicker.upper(), 13, TEAL, bold=True)
    txbox(slide, 0.83, 0.82, 11.8, 0.8, title, 32, WHITE, bold=True)


def bullets(slide, items, top=2.0, left=0.95, width=11.5, size=17, gap=6):
    box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(4.6))
    tf = box.text_frame
    tf.word_wrap = True
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(gap)
        if isinstance(item, tuple):
            head, rest = item
        else:
            head, rest = None, item
        m = p.add_run()
        m.text = "▸  "
        m.font.size = Pt(size)
        m.font.color.rgb = TEAL
        m.font.bold = True
        m.font.name = FONT
        if head:
            r1 = p.add_run()
            r1.text = head
            r1.font.size = Pt(size)
            r1.font.bold = True
            r1.font.color.rgb = WHITE
            r1.font.name = FONT
        r2 = p.add_run()
        r2.text = rest
        r2.font.size = Pt(size)
        r2.font.color.rgb = MUTED
        r2.font.name = FONT
    return box


def stat_cards(slide, cards, top=2.15):
    """cards: list of (big, label, color)."""
    n = len(cards)
    gap, total = 0.35, 12.0
    w = (total - gap * (n - 1)) / n
    for i, (big, label, color) in enumerate(cards):
        l = 0.66 + i * (w + gap)
        card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(l), Inches(top), Inches(w), Inches(2.2))
        card.fill.solid()
        card.fill.fore_color.rgb = PANEL
        card.line.color.rgb = color
        card.line.width = Pt(1.25)
        tf = card.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        r = p.add_run()
        r.text = big
        r.font.size = Pt(40)
        r.font.bold = True
        r.font.color.rgb = color
        r.font.name = FONT
        p2 = tf.add_paragraph()
        p2.alignment = PP_ALIGN.CENTER
        r2 = p2.add_run()
        r2.text = label
        r2.font.size = Pt(14)
        r2.font.color.rgb = MUTED
        r2.font.name = FONT


def footer(slide, num):
    txbox(slide, 0.6, 7.02, 9.5, 0.35,
          "MuleShield · synthetic data · illustrative signals, not legal advice",
          10, MUTED)
    txbox(slide, 12.1, 7.02, 0.7, 0.35, f"{num}/10", 10, MUTED, align=PP_ALIGN.RIGHT)


# ---------------------------------------------------------------- slide 1
s = base_slide()
accent = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.333), Inches(0.14))
accent.fill.solid(); accent.fill.fore_color.rgb = TEAL; accent.line.fill.background()
txbox(s, 0.9, 1.75, 11.5, 0.45, "HACKATHON DEMO · CYBER AWARENESS", 15, TEAL, bold=True)
txbox(s, 0.85, 2.25, 12.0, 1.3, "MuleShield", 66, WHITE, bold=True)
txbox(s, 0.9, 3.5, 11.5, 0.6, "Spot it.  Refuse it.  Report it.", 30, TEAL, bold=True)
txbox(s, 0.9, 4.35, 11.5, 0.9,
      "A local web app that helps students recognise and refuse "
      "money-mule recruitment offers — and shows the bank's side of the same story.",
      17, MUTED)
panel = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.9), Inches(5.5), Inches(7.6), Inches(0.75))
panel.fill.solid(); panel.fill.fore_color.rgb = PANEL; panel.line.color.rgb = TEAL_DIM
tf = panel.text_frame; tf.vertical_anchor = MSO_ANCHOR.MIDDLE
p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
r = p.add_run(); r.text = "LIVE:  " + URL
r.font.size = Pt(16); r.font.bold = True; r.font.color.rgb = TEAL; r.font.name = FONT
footer(s, 1)

# ---------------------------------------------------------------- slide 2
s = base_slide()
header(s, "The problem", "Money mules: students doing prison-time work for pocket money")
bullets(s, [
    ("Recruiters pay students ", "to “just forward” money that lands in their account."),
    ("The account launders stolen funds ", "— the student becomes the trail."),
    ("A few days of transfers ", "can mean years of legal risk, frozen accounts, an FIR."),
    ("The script always uses ", "secrecy, urgency and easy commission."),
    ("It targets exam season ", "— fees due, part-time jobs wanted, nobody suspicious."),
], top=2.1)
footer(s, 2)

# ---------------------------------------------------------------- slide 3
s = base_slide()
header(s, "The trap, step by step", "Simulator: the real recruitment script, replayed")
bullets(s, [
    ("7-step timeline: ", "DM → job pitch → first credit → pressure → payout promise."),
    ("Every card is factual and calm ", "— marked “illustrative scenario, not legal advice”."),
    ("A “refuse and report” branch ", "shows the safe exit — the decision the whole app is built for."),
    ("Steps are announced to screen readers ", "(aria-live) and work on a phone."),
], top=2.1)
footer(s, 3)

# ---------------------------------------------------------------- slide 4
s = base_slide()
header(s, "Product", "Six pages, one app — static frontend + FastAPI backend")
bullets(s, [
    ("Home ", "— paste an offer, get a 0–100 score with highlighted snippets."),
    ("Simulator ", "— the 7-step trap walkthrough with a safe exit."),
    ("Report ", "— anonymous, indicator-only reporting."),
    ("Campus Alerts ", "— clusters of matching reports; 3+ = ACTIVE alert."),
    ("Bank Dashboard ", "— anomaly scoring of 200 synthetic accounts."),
    ("Learn ", "— red-flag checklist, myth-busting, shareable alert text."),
    ("No build step · runs offline · ", "no CDNs, Chart.js vendored locally."),
], top=1.95, size=16, gap=5)
footer(s, 4)

# ---------------------------------------------------------------- slide 5
s = base_slide()
header(s, "Detect the offer", "Home analyzer: transparent rules + TF-IDF model")
bullets(s, [
    ("Blend: ", "0.4 × readable rules + 0.6 × ML model; High ≥ 65, Medium ≥ 30."),
    ("Evidence, not a verdict: ", "each signal shows the exact snippet + why it matters."),
    ("Multilingual ", "— Tamil offers detected with the same rigour."),
    ("Handles gracefully ", "empty, huge, and everyday-friendly input (no false alarms)."),
], top=2.1)
stat_cards(s, [
    ("98", "English scam → HIGH", RED),
    ("93", "Tamil scam → HIGH", RED),
    ("17", "Canteen chat → LOW", TEAL),
], top=4.55)
footer(s, 5)

# ---------------------------------------------------------------- slide 6
s = base_slide()
header(s, "Report safely", "Anonymous reporting that never stores your message")
bullets(s, [
    ("Extracts indicators only ", "— phone, UPI id, URL, Telegram/WhatsApp handles."),
    ("Stores salted hashes + masks ", "like 98xxxxxx10 — the raw text is discarded, by schema."),
    ("3+ matching reports ", "= ACTIVE campus alert for the whole campus."),
    ("One click builds a redacted ", "cybercrime.gov.in summary — personal fields left blank."),
    ("Per-install salt ", "means hashes can't be linked across installs."),
], top=2.1)
footer(s, 6)

# ---------------------------------------------------------------- slide 7
s = base_slide()
header(s, "The bank's side", "Bank Dashboard: Isolation Forest + 5 readable rules")
bullets(s, [
    ("Features: ", "pass-through ratio, unique senders, time-to-forward, retained balance, new device."),
    ("Readable explanations ", "— every flag ships a plain-English “why”."),
    ("Money-flow chart ", "— teal credits in, red debits out minutes later."),
    ("Permanent banner: ", "“Synthetic data for demonstration only.”"),
], top=2.1)
stat_cards(s, [
    ("#1–10", "all 10 mules ranked here", RED),
    ("87–100", "mule scores (flag ≥ 70)", AMBER),
    ("#11 · 52", "best honest account", TEAL),
], top=4.55)
footer(s, 7)

# ---------------------------------------------------------------- slide 8
s = base_slide()
header(s, "Proven", "Working, tested, deployed — today")
stat_cards(s, [
    ("21/21", "automated tests pass", TEAL),
    ("17/17", "endpoint checks (live)", TEAL),
    ("0", "external requests at runtime", TEAL),
], top=2.2)
bullets(s, [
    ("Clean-install verified ", "— fresh venv from requirements.txt only, first-run data generation tested."),
    ("Deployed free on Render ", "— cold start auto-generates and re-seeds demo data."),
    ("Live demo: ", URL),
], top=4.95, size=16)
footer(s, 8)

# ---------------------------------------------------------------- slide 9
s = base_slide()
header(s, "Privacy by design", "Ethics built into the schema, not just the copy")
bullets(s, [
    ("No raw text anywhere: ", "the database has no column that could hold your message."),
    ("What's stored: ", "salted indicator hashes, masked indicators, campus tag, timestamp, derived numbers."),
    ("All data invented ", "— no real numbers, names, accounts or employers anywhere."),
    ("Zero network calls ", "at runtime — no CDNs, fonts, telemetry or paid APIs."),
    ("Honest framing ", "— banners and footers mark synthetic data and “not legal advice”."),
], top=2.1)
footer(s, 9)

# ---------------------------------------------------------------- slide 10
s = base_slide()
header(s, "Honest close", "What it is — and what it isn't")
bullets(s, [
    ("Is: ", "a demo-grade awareness tool that makes the invisible pattern visible."),
    ("Isn't: ", "a detector product, a reporting channel, or legal advice."),
    ("Limits: ", "heuristic detector on invented messages; synthetic bank data; single-user SQLite."),
    ("Next: ", "real message corpora, hosted DB, IITM Madras-referenced reporting flow."),
], top=2.1)
panel = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.9), Inches(5.15), Inches(11.5), Inches(1.15))
panel.fill.solid(); panel.fill.fore_color.rgb = PANEL; panel.line.color.rgb = TEAL
tf = panel.text_frame; tf.vertical_anchor = MSO_ANCHOR.MIDDLE; tf.word_wrap = True
p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
r = p.add_run(); r.text = "Try it now  →  " + URL
r.font.size = Pt(24); r.font.bold = True; r.font.color.rgb = TEAL; r.font.name = FONT
p2 = tf.add_paragraph(); p2.alignment = PP_ALIGN.CENTER
r2 = p2.add_run(); r2.text = "Source + full README on github.com/jayasuthan703-ux/MuleShield"
r2.font.size = Pt(13); r2.font.color.rgb = MUTED; r2.font.name = FONT
footer(s, 10)

out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "MuleShield_Demo.pptx"
prs.save(out)
print(f"wrote {out} ({len(prs.slides)} slides)")
