"""Assistant answers for the Stock Ageing page (finished-goods pcs, FIFO, EasyTrade snapshot).

Kept apart from the generic matcher on purpose: words like "stock", "value" and "pieces" belong to other pages too,
so this answers only when the question clearly means old / closing / ageing stock. Every figure comes from the same
GET /api/stock-ageing the page uses.
"""
from __future__ import annotations

import re

from . import fmt

NOT_STOCK = re.compile(r"\b(fabricators?|karigars?|fabric|po|pos|samples?|production|remaining|issued)\b")
TRIGGER = re.compile(
    r"\b(stock age?ing|age?ing (?:of )?(?:the )?stock|(?:closing|dead|old|purana|puraana|purane|unsold|slow[- ]?moving) "
    r"(?:stock|maal|inventory)|stock value|value of (?:the )?stock|stock ki value|inventory)\b")
STOCK_WORD = re.compile(r"\b(stock|maal|inventory|designs?)\b")
AGE_WORD = re.compile(r"\b(old|purana|purane|puraana|age?ing|saal|years?|days?|din|months?|mahine)\b")
FOLLOW = re.compile(r"\b(over|more than|se zyada|se purana|series|365|180|90|fresh|which|kaun|top|saal|year)\b")

# (pattern, bucket indexes, words for the answer); first match wins
BANDS = [
    (r"\b(31\s*(?:-|to)\s*60)\b", [1], "31-60 days old"),
    (r"\b(61\s*(?:-|to)\s*90)\b", [2], "61-90 days old"),
    (r"\b(91\s*(?:-|to)\s*180)\b", [3], "91-180 days old"),
    (r"\b(181\s*(?:-|to)\s*365)\b", [4], "181-365 days old"),
    (r"\b365\b|\b(?:1|one|a|ek)\s*(?:saal|year|yr)\b|\bdead stock\b", [5], "over 365 days old"),
    (r"\b180\b|\b(?:6|six|che|chhe)\s*(?:months?|mahine)\b", [4, 5], "over 180 days old"),
    (r"\b90\b|\b(?:3|three|teen)\s*(?:months?|mahine)\b", [3, 4, 5], "over 90 days old"),
    (r"\bfresh\b|\bnew stock\b|\b0\s*(?:-|to)\s*30\b|\b30\s*(?:days?|din)\b", [0], "0-30 days old"),
]


def _inr(v: float) -> str:
    return f"₹{v / 1e7:,.2f} Cr" if v >= 1e7 else f"₹{v / 1e5:,.2f} L" if v >= 1e5 else f"₹{v:,.0f}"


def _rows(body: dict, name: str):
    t = (body.get("tables") or {}).get(name) or {}
    cols = [c["label"] for c in t.get("columns") or []]
    return cols, [r for r in t.get("rows") or [] if str(r[0]).upper() != "TOTAL"]


def matches(text: str, previous_page: str | None) -> bool:
    raw = text.lower()
    if NOT_STOCK.search(raw):
        return False
    if TRIGGER.search(raw):
        return True
    if STOCK_WORD.search(raw) and AGE_WORD.search(raw) and re.search(r"\b(stock|maal|inventory)\b", raw):
        return True
    return previous_page == "stock-ageing" and len(raw.split()) <= 9 and bool(FOLLOW.search(raw))


def answer(text: str, fetch) -> str:
    raw = text.lower()
    series = re.search(r"\bseries\s*(\d{2})\b", raw)
    body = fetch("stock-ageing", {})
    if body.get("empty"):
        return "The Stock Ageing page has no stock rows yet."
    scope = ""
    if series:
        name = f"Series {series.group(1)}"
        options = (body.get("options") or {}).get("type") or []
        if name not in options:
            return f"There is no {name} on the Stock Ageing page. Series available: {', '.join(options)}."
        body, scope = fetch("stock-ageing", {"type": [name]}), f" · {name}"
    s = body["summary"]
    qty = [c["value"] for c in body["charts"]["qty_by_age"]]
    val = [c["value"] for c in body["charts"]["value_by_age"]]
    labels = [c["label"] for c in body["charts"]["qty_by_age"]]
    head = f"**Stock Ageing**{scope} · as on {body['as_on']} closing · pieces, value at inward cost before GST"
    lines = [head]
    if body.get("demo"):
        lines.append("These are **made-up demo rows**: the EasyTrade snapshot is not set up on this server.")
    ages = re.sub(r"\bseries\s*\d{2}\b", " ", raw)      # "series 90" is a design series, not 90 days
    band = next(((idx, words) for pat, idx, words in BANDS if re.search(pat, ages)), None)

    if re.search(r"\bseries\b", raw) and not series and re.search(r"\b(which|kaun\w*|kis|most|highest|sabse|zyada|wise)\b", raw):
        cols, rows = _rows(body, "types")
        i, p = cols.index("Value over 180 days"), cols.index("Over 180 %")
        rows = sorted(rows, key=lambda r: -(r[i] or 0))
        lines.append(f"**{rows[0][0]}** holds the most stock over 180 days: **{_inr(rows[0][i])}** ({rows[0][p]:.0f}% of "
                     "its value).")
        lines += [f"• {r[0]}: {_inr(r[i])} over 180 days ({r[p]:.0f}%)" for r in rows[:8]]
    elif re.search(r"\b(designs?|items?|clear\w*|top|list|kaunse|konse)\b", raw):
        cols, rows = _rows(body, "stuck")
        if not rows:
            lines.append("No design has stock over 180 days.")
        else:
            q, v = cols.index("Pcs over 180 days"), cols.index("Value over 180 days")
            lines.append("Designs with the most value over 180 days (act on these first):")
            lines += [f"• **{r[0]}**: {fmt.fmt_int(r[q])} pcs, {_inr(r[v])}" for r in rows[:10]]
    elif band:
        idx, words = band
        q, v = sum(qty[i] for i in idx), sum(val[i] for i in idx)
        lines.append(f"Stock {words}: **{fmt.fmt_int(q)} pcs**, **{_inr(v)}** at cost "
                     f"({q / s['qty'] * 100 if s['qty'] else 0:.1f}% of pieces, "
                     f"{v / s['value'] * 100 if s['value'] else 0:.1f}% of value).")
    else:
        lines.append(f"Closing stock: **{fmt.fmt_int(s['qty'])} pcs** in {s['designs']:,} designs, worth **{_inr(s['value'])}**; "
                     f"average age {s['avg_age']} days.")
        lines += ["| Age | Pcs | Value |", "|---|---|---|"]
        lines += [f"| {labels[i]} | {fmt.fmt_int(qty[i])} | {_inr(val[i])} |" for i in range(len(labels))]
    return "\n".join(lines)
