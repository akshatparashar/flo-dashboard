"""Assistant answers for the Stock Ageing page and its Unsold Inventory Insights section.

Kept apart from the generic matcher on purpose: words like "stock", "value", "sale" and "designs" belong to other pages
too, so this answers only when the question clearly means stock waiting in the warehouse. Every figure comes from the
same GET /api/stock-ageing the page uses.

Two measures, never mixed up (see dashboards/unsold.py):
- piece age   - how long the remaining pieces have been in stock ("90 din se purana stock");
- no-sale time - how long a design's stock has sat without a sale ("90 din se nahi bika").

``read`` turns a question into an intent {kind, days, series, ...}; the intent of the last stock answer travels in the
chat context, so "aur 180 din?", "unki value?" or "kaunse designs?" keep the subject.
"""
from __future__ import annotations

import re

from . import fmt

NOT_STOCK = re.compile(r"\b(fabricators?|karigars?|fabric|po|pos|samples?|production|remaining|issued|tasks?|"
                       r"flo future|promis\w*)\b")
# words that mean the person has moved to another page, so a short message is not a stock follow-up
OTHER_PAGE = re.compile(r"\b(designers?|clients?|vendors?|target|revenue|rates?|delegation|net sale|sale pcs|incoming|"
                        r"orders?|in ?house|outsource|overdue)\b")
TRIGGER = re.compile(
    r"\b(stock age?ing|age?ing (?:of )?(?:the )?stock|(?:closing|dead|old|purana|puraana|purane|unsold|slow[- ]?moving) "
    r"(?:stock|maal|inventory|designs?)|stock value|value of (?:the )?stock|stock ki value|inventory|age of (?:the )?stock|"
    r"series[- ]?wise stock|stock series[- ]?wise)\b")
STOCK_WORD = re.compile(r"\b(stock|maal|inventory)\b")
STOCK_ASK = re.compile(r"\b(old|oldest|purana|puraana|purane|purani|age|age?ing|umar|saal|years?|days?|din|months?|mahine|"
                       r"series|average|avg|ausat|adjustment|journal|count|returns?|page|kaha|kahan|kidhar|where)\b")
UNSOLD = re.compile(r"\b(unsold|un-sold|not (?:been )?sold|nahi\s?n? (?:bik\w*|sold|sell\w*)|nhi (?:bik\w*|sold)|bik nahi|"
                    r"bika nahi|no sale|bina (?:bik\w*|bike|sale)|sale nahi h\w+|never sold|na (?:bik\w*|bike)|nahin bik\w*)\b")
NEVER = re.compile(r"\b(never (?:been )?sold|kabhi (?:bhi )?(?:nahi\s?n?|nhi) (?:bik\w*|sold)|ek bhi (?:sale|baar) nahi|"
                   r"no sale on record|zero sale)\b")
ADJUST = re.compile(r"\b(adjustment|physical (?:count|stock)|stock count|journal|sales? returns?|returned (?:pcs|pieces)|"
                    r"returns? wale)\b")
LIST = re.compile(r"\b(kaunse|konse|kaun ?sa|kon ?sa|kaunsi|which|list|dikhao|dikhaiye|naam|names?|top)\b")
OLDER = re.compile(r"\b(se (?:purana|purane|purani|zyada|jyada|upar)|over|older|more than|above)\b")
VALUE = re.compile(r"\b(value|keemat|kimat|amount|rupaye|rupees)\b")
WHERE = re.compile(r"\b(kaha|kahan|kaha pe|kidhar|where)\b")
CODE = re.compile(r"\b(?:\d{2}|[a-z]\d{2})\s*-\s*\d{3,}", re.I)
SELLING = re.compile(r"\bfast selling\b")
# a page of its own already: the Fabricators page is also called the "stock page", and summaries are the Overview's
NOT_GENERIC = re.compile(r"\b(stock page|summary|overview|dashboard|aaya|aaye|aayi|aya|aye|received|incoming|bheja|bheje|"
                         r"issue\w*)\b")        # "kitna maal aaya" is about what came in, not what is lying there
FOLLOW = re.compile(r"\b(aur|and|value|keemat|series|designs?|kaunse|konse|which|list|never|kabhi|bik\w*|sold|unsold|"
                    r"over|se zyada|se purana|saal|year|din|days?|mahine|months?|fresh|top|30|60|90|180|365|kitne|kitna)\b")

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
NUMBERS = {"ek": 1, "one": 1, "a": 1, "do": 2, "two": 2, "teen": 3, "three": 3, "che": 6, "chhe": 6, "six": 6}


def _inr(v: float) -> str:
    return f"₹{v / 1e7:,.2f} Cr" if v >= 1e7 else f"₹{v / 1e5:,.2f} L" if v >= 1e5 else f"₹{v:,.0f}"


def _rows(body: dict, name: str):
    t = (body.get("tables") or {}).get(name) or {}
    cols = [c["label"] for c in t.get("columns") or []]
    return cols, [r for r in t.get("rows") or [] if str(r[0]).upper() != "TOTAL"]


def days_in(text: str) -> int | None:
    """The number of days a question names: "90 din", "1 saal", "6 mahine", "180 se"."""
    t = re.sub(r"\bseries\s*\d{2}\b", " ", text.lower())
    t = CODE.sub(" ", t)
    if re.search(r"\b\d{1,3}\s*(?:-|to)\s*\d{2,3}\b", t):      # "31-60" is a band, not a number of days
        return None
    m = re.search(r"\b(\d{1,4})\s*\+?\s*(?:days?|din|d)\b", t)
    if m:
        return int(m.group(1))
    num = r"(\d{1,2}|" + "|".join(NUMBERS) + r")"
    m = re.search(rf"\b{num}\s*(?:saal|sal|years?|yr)\b", t)
    if m:
        return 365 * (NUMBERS.get(m.group(1)) or int(m.group(1)))
    m = re.search(rf"\b{num}\s*(?:months?|mahin[ae]|mhine)\b", t)
    if m:
        n = NUMBERS.get(m.group(1)) or int(m.group(1))
        return 365 if n == 12 else n * 30
    m = re.search(r"\b(30|60|90|180|365)\b", t) or re.search(r"\b(?:over|above|more than)\s+(\d{1,4})\b", t)
    return int(m.group(1)) if m else None


def band_words(text: str) -> str:
    """The age band a question names, as words ("over 365 days old"), or ""."""
    ages = re.sub(r"\bseries\s*\d{2}\b", " ", text.lower())
    return next((words for pat, _, words in BANDS if re.search(pat, ages)), "")


def matches(text: str, previous_page: str | None) -> bool:
    raw = text.lower()
    if NOT_STOCK.search(raw):
        return False
    if TRIGGER.search(raw) or UNSOLD.search(raw) or NEVER.search(raw) or SELLING.search(raw):
        return True
    if STOCK_WORD.search(raw) and (STOCK_ASK.search(raw) or not NOT_GENERIC.search(raw)):
        return True
    if CODE.search(raw) and re.search(r"\b(bik\w*|sold|sale|stock|din|kab|design|age)\b", raw):
        return True
    if previous_page != "stock-ageing" or len(raw.split()) > 9 or OTHER_PAGE.search(raw):
        return False
    return bool(FOLLOW.search(raw) or days_in(raw))


def read(text: str, previous: dict | None = None) -> dict:
    """The question as an intent. ``previous`` is the intent of the last stock answer, for follow-ups."""
    raw = text.lower()
    prev = previous or {}
    series = re.search(r"\bseries\s*(\d{2})\b", raw)
    intent = {"series": series.group(1) if series else None, "days": days_in(raw), "list": bool(LIST.search(raw)),
              "value": bool(VALUE.search(raw)), "older": bool(OLDER.search(raw)),
              "no_sale": bool(UNSOLD.search(raw))}
    if WHERE.search(raw):
        kind = "where"
    elif NEVER.search(raw):
        kind = "never"
    elif SELLING.search(raw):
        kind = "selling"
    elif ADJUST.search(raw):
        kind = "adjust"
    elif re.search(r"\b(average|avg|ausat)\b.*\b(age|umar|din|days)\b|\b(age|umar)\b.*\b(average|avg|ausat)\b|"
                   r"\baverage age\b", raw):
        kind = "avg_age"
    elif re.search(r"series[- ]?wise|\b(which|kis|kaun ?si|kaun)\s+series\b|series (?:me|mein) sabse|"
                   r"\bseries\b.*\bsabse (?:zyada|jyada)\b", raw):
        kind = "series"
    elif intent["no_sale"] and re.search(r"sabse (?:zyada|jyada|lambe|purana)|longest|sabse (?:zyada )?(?:din|time)", raw):
        kind = "longest"
    elif intent["no_sale"]:
        kind = "unsold"
    elif CODE.search(raw):
        kind = "design"
    elif re.search(r"\b(sabse (?:purana|purani|purane)|oldest)\b", raw):
        kind = "oldest"
    else:
        kind = "age"
    # a follow-up that only changes one thing keeps the rest of the earlier question
    short = len(raw.split()) <= 9
    if prev and short:
        if kind == "age" and prev.get("kind") in ("unsold", "never", "longest") and not STOCK_WORD.search(raw) \
                and not intent["older"]:
            kind = "unsold" if intent["days"] or prev.get("kind") == "unsold" else prev["kind"]
        elif kind == "age" and intent["list"] and prev.get("kind") in ("series", "oldest", "selling"):
            kind = prev["kind"]
        if intent["series"] is None and kind not in ("where", "series") and not re.search(r"\b(all|total|overall|sab|poora)\b", raw):
            intent["series"] = prev.get("series")
        if intent["days"] is None and kind in ("unsold", "age", "series") and (intent["list"] or intent["value"]
                                                                             or series):
            intent["days"] = prev.get("days")
            intent["older"] = intent["older"] or bool(prev.get("older"))
    intent["kind"] = kind
    return intent


# ------------------------------------------------------------------------------------------------ answers
def _design_lines(cols, rows, extra, limit=10) -> list[str]:
    at = {c: i for i, c in enumerate(cols)}
    return [f"• **{r[0]}**: {extra(r, at)}" for r in rows[:limit]]


def _sale_text(r, at) -> str:
    last = r[at["Last sale"]]
    return (f"{fmt.fmt_int(r[at['Days without sale']] or 0)} days without a sale, "
            f"{'last sale ' + str(last) if last else 'never sold'}, {fmt.fmt_int(r[at['Pcs']])} pcs, {_inr(r[at['Value']])}")


def answer(text: str, fetch, previous: dict | None = None) -> tuple[str, dict]:
    """(answer text, intent to remember)."""
    want = read(text, previous)
    raw = text.lower()
    body = fetch("stock-ageing", {})
    if body.get("empty"):
        return "The Stock Ageing page has no stock rows yet.", want
    if want["kind"] == "where":
        what = "Unsold Inventory Insights" if re.search(r"unsold|nahi bik|never sold", raw) else "Stock ageing"
        return (f"{what} is on the **Stock Ageing** page: sidebar → Operations → Stock Ageing. The Unsold Inventory "
                "Insights section is below Highlights.", want)
    scope = ""
    if want["series"]:
        name = f"Series {want['series']}"
        options = (body.get("options") or {}).get("type") or []
        if name not in options:
            return (f"There is no {name} on the Stock Ageing page. Series available: {', '.join(options)}.",
                    {**want, "series": None})
        body, scope = fetch("stock-ageing", {"type": [name]}), f" · {name}"
    s = body["summary"]
    u = body.get("unsold") or {}
    lines = [f"**Stock Ageing**{scope} · as on {body['as_on']} closing · pieces, value at inward cost before GST"]
    if body.get("demo"):
        lines.append("These are **made-up demo rows**: the EasyTrade snapshot is not set up on this server.")
    kind, days = want["kind"], want["days"]
    if kind in ("unsold", "never", "longest", "design", "selling") and not u.get("has_sales"):
        lines.append("Sales history is not in this stock snapshot, so I can't say what has not sold. Piece age is "
                     "available: ask \"stock 90 din se purana\".")
        return "\n".join(lines), want
    cols, rows = _rows({"tables": u}, "table") if u else ([], [])
    at = {c: i for i, c in enumerate(cols)}
    value_sum = lambda rs: sum(r[at["Value"]] or 0 for r in rs)
    pcs_sum = lambda rs: sum(r[at["Pcs"]] or 0 for r in rs)

    if kind == "unsold":
        if days is None:
            lines.append("Unsold stock (designs whose stock has waited without any sale):")
            for c in u["cards"]:
                n = c["no_sale"]
                lines.append(f"• Over {c['days']} days: **{n['designs']:,} designs**, {fmt.fmt_int(n['pcs'])} pcs, "
                             f"{_inr(n['value'])}")
            lines.append(f"Never sold: **{u['never']['designs']:,} designs**, {fmt.fmt_int(u['never']['pcs'])} pcs, "
                         f"{_inr(u['never']['value'])}. Each \"over\" figure includes the longer ones.")
        else:
            hit = [r for r in rows if (r[at["Days without sale"]] or 0) > days]
            share = value_sum(hit) / s["value"] * 100 if s["value"] else 0
            lines.append(f"No sale for over {days} days: **{len(hit):,} designs**, **{fmt.fmt_int(pcs_sum(hit))} pcs**, "
                         f"**{_inr(value_sum(hit))}** at cost ({share:.1f}% of stock value).")
            if want["list"] and hit:
                lines.append("Longest without a sale first:")
                lines += _design_lines(cols, hit, _sale_text)
    elif kind == "never":
        hit = sorted((r for r in rows if not r[at["Last sale"]]), key=lambda r: -(r[at["Value"]] or 0))
        lines.append(f"Never sold (no sale on record since April 2023): **{len(hit):,} designs**, "
                     f"**{fmt.fmt_int(pcs_sum(hit))} pcs**, **{_inr(value_sum(hit))}** at cost. Some may simply be new.")
        if want["list"] and hit:
            lines.append("Highest value first:")
            lines += _design_lines(cols, hit, _sale_text)
    elif kind == "longest":
        lines.append("Designs that have waited longest without a sale:")
        lines += _design_lines(cols, rows, _sale_text)
    elif kind == "selling":
        hit = sorted((r for r in rows if r[at["Sold in 90 days"]]), key=lambda r: -r[at["Sold in 90 days"]])
        if not hit:
            lines.append("No design in the current stock has a sale in the last 90 days.")
        else:
            lines.append("Fastest selling designs **still in stock**, by pieces sold in the last 90 days (sold-out designs "
                         "are not on this page):")
            lines += _design_lines(cols, hit, lambda r, a: f"{fmt.fmt_int(r[a['Sold in 90 days']])} pcs sold in 90 days, "
                                                             f"{fmt.fmt_int(r[a['Pcs']])} pcs in stock")
    elif kind == "design":
        squash = lambda x: re.sub(r"\s+", "", str(x)).upper()
        asked = squash(text)
        found = sorted((r for r in rows if len(squash(r[0])) >= 6 and squash(r[0]).split("/")[0] in asked),
                       key=lambda r: -len(squash(r[0])))
        if not found:
            lines.append("I can't find that design in the current stock. It may be sold out; check the code on the "
                         "Stock Ageing page.")
        for r in found[:3]:
            lines.append(f"**{r[0]}**: {_sale_text(r, at)}; oldest piece {fmt.fmt_int(r[at['Oldest piece (days)']] or 0)} "
                         f"days in stock; sold in the last 90 days: {fmt.fmt_int(r[at['Sold in 90 days']] or 0)}.")
    elif kind == "oldest":
        old = sorted(rows, key=lambda r: (-(r[at["Oldest piece (days)"]] or 0), -(r[at["Value"]] or 0)))
        lines.append("Oldest stock, by design (age of the oldest piece still in stock):")
        lines += _design_lines(cols, old, lambda r, a: f"{fmt.fmt_int(r[a['Oldest piece (days)']] or 0)} days, "
                                                         f"{fmt.fmt_int(r[a['Pcs']])} pcs, {_inr(r[a['Value']])}")
    elif kind == "avg_age":
        lines.append(f"Average age of the stock is **{s['avg_age']} days** (weighted by pieces).")
    elif kind == "adjust":
        d = u.get("dated_from") or {}
        lines.append(f"Pieces dated from a stock count or journal entry, not a purchase: **{fmt.fmt_int(d.get('adjustments', 0))} "
                     f"pcs** (they may be older than shown). Sales returns, dated from the day they came back: "
                     f"**{fmt.fmt_int(d.get('returns', 0))} pcs**.")
    elif kind == "series" and (want["no_sale"] or (previous or {}).get("kind") == "unsold") and u.get("has_sales"):
        limit = days or 90
        totals: dict = {}
        for r in rows:
            if (r[at["Days without sale"]] or 0) > limit:
                t = totals.setdefault(r[at["Series"]], [0, 0.0, 0.0])
                t[0] += 1
                t[1] += r[at["Pcs"]] or 0
                t[2] += r[at["Value"]] or 0
        ranked = sorted(totals.items(), key=lambda kv: -kv[1][2])
        if not ranked:
            lines.append(f"No design has gone over {limit} days without a sale.")
        else:
            name, (n, p, v) = ranked[0]
            lines.append(f"**{name}** has the most stock with no sale for over {limit} days: **{_inr(v)}** ({n:,} designs).")
            lines += [f"• {k}: {x[0]:,} designs, {fmt.fmt_int(x[1])} pcs, {_inr(x[2])}" for k, x in ranked[:10]]
    elif kind == "series" and re.search(r"series[- ]?wise", raw):
        tcols, trows = _rows(body, "types")
        a = {c: i for i, c in enumerate(tcols)}
        lines += ["| Design series | Designs | Pcs | Value | Value over 180 days |", "|---|---|---|---|---|"]
        lines += [f"| {r[0]} | {r[a['Designs']]:,} | {fmt.fmt_int(r[a['Pcs']])} | {_inr(r[a['Value']])} | "
                  f"{_inr(r[a['Value over 180 days']])} |" for r in trows]
    elif kind == "series":
        tcols, trows = _rows(body, "types")
        i, p = tcols.index("Value over 180 days"), tcols.index("Over 180 %")
        trows = sorted(trows, key=lambda r: -(r[i] or 0))
        lines.append(f"**{trows[0][0]}** holds the most stock over 180 days: **{_inr(trows[0][i])}** ({trows[0][p]:.0f}% of "
                     "its value).")
        lines += [f"• {r[0]}: {_inr(r[i])} over 180 days ({r[p]:.0f}%)" for r in trows[:8]]
    else:
        _age_answer(raw, want, body, lines, rows, at)
    return "\n".join(lines), want


def _age_answer(raw: str, want: dict, body: dict, lines: list[str], rows: list, at: dict) -> None:
    """Piece age: the summary, one age band, "older than N days", or the designs to act on."""
    s = body["summary"]
    qty = [c["value"] for c in body["charts"]["qty_by_age"]]
    val = [c["value"] for c in body["charts"]["value_by_age"]]
    labels = [c["label"] for c in body["charts"]["qty_by_age"]]
    ages = re.sub(r"\bseries\s*\d{2}\b", " ", raw)      # "series 90" is a design series, not 90 days
    band = next(((idx, words) for pat, idx, words in BANDS if re.search(pat, ages)), None)
    days = want["days"]
    over = {30: ([1, 2, 3, 4, 5], "over 30 days old"), 90: ([3, 4, 5], "over 90 days old"),
            180: ([4, 5], "over 180 days old"), 365: ([5], "over 365 days old")}
    if days in over and (want["older"] or days != 30):
        band = over[days]                              # "30 din se purana" is older than 30, not the 0-30 band
    designs = re.search(r"\b(designs?|items?|clear\w*|top|list|kaunse|konse)\b", raw) or want["list"]
    if designs and band and band[1].startswith("over") and rows:
        limit = re.search(r"\d+", band[1]).group(0)
        i, v = at[f"Pcs over {limit}d"], at["Value"]
        hit = sorted((r for r in rows if r[i]), key=lambda r: (-(r[i] or 0), -(r[v] or 0)))
        lines.append(f"**{len(hit):,} designs** hold pieces over {limit} days old; the most such pieces:")
        lines += [f"• **{r[0]}**: {fmt.fmt_int(r[i])} pcs over {limit} days" for r in hit[:10]]
    elif designs and re.search(r"\b(designs?|items?|clear\w*|top|list|kaunse|konse)\b", raw):
        cols, stuck = _rows(body, "stuck")
        if not stuck:
            lines.append("No design has stock over 180 days.")
        else:
            q, v = cols.index("Pcs over 180 days"), cols.index("Value over 180 days")
            lines.append("Designs with the most value over 180 days (act on these first):")
            lines += [f"• **{r[0]}**: {fmt.fmt_int(r[q])} pcs, {_inr(r[v])}" for r in stuck[:10]]
    elif band:
        idx, words = band
        q, v = sum(qty[i] for i in idx), sum(val[i] for i in idx)
        lines.append(f"Stock {words}: **{fmt.fmt_int(q)} pcs**, **{_inr(v)}** at cost "
                     f"({q / s['qty'] * 100 if s['qty'] else 0:.1f}% of pieces, "
                     f"{v / s['value'] * 100 if s['value'] else 0:.1f}% of value).")
    elif days is not None:
        lines.append(f"Piece age is kept in bands, so I can't count \"over {days} days\" exactly. Ask for over 30, 90, "
                     "180 or 365 days, or ask what has not sold for that long.")
    else:
        lines.append(f"Closing stock: **{fmt.fmt_int(s['qty'])} pcs** in {s['designs']:,} designs, worth **{_inr(s['value'])}**; "
                     f"average age {s['avg_age']} days.")
        lines += ["| Age | Pcs | Value |", "|---|---|---|"]
        lines += [f"| {labels[i]} | {fmt.fmt_int(qty[i])} | {_inr(val[i])} |" for i in range(len(labels))]
