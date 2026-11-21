"""Order questions per designer ("customer"): counts, new vs repeat, rankings, comparisons and month-to-month change.

What the dashboard calls things (nothing here is a made-up business rule):
  * one *order* (a design) is one row of the tracker with a quantity above 0 - the Designers page calls the count
    "Design Count" and the Designers KPI "Total designs";
  * a row is NEW or REPEAT by the sheet's own order-type column (the Designers page's ``order_type`` filter);
  * the "customer" who owns an order is the designer named on the row (the Designers page); clients are a separate
    dimension and are left to the existing client answers.

Every figure is read from the Designers page (``fetch("designer", filters)``); this file only reads the words,
adds, subtracts and divides. The names (AYUSHI, CHARU ...) come from the dashboard's own option lists.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

from . import calc
from .text import name_key, norm

ORDER_W = re.compile(r"\b(orders?|ordr|designs?|design count)\b")
REPEAT_W = re.compile(r"\b(repeat\w*|rpt)\b")
NEW_W = re.compile(r"\bnew\b")
PCS_W = re.compile(r"\b(pcs|pc|pieces?|quantity|qty|volume|units?)\b")
DESIGN_W = re.compile(r"\bdesigns?\b")
# other dashboard figures that mention "orders" but are answered elsewhere
OTHER_METRIC = re.compile(r"\b(po|pos|fpo|fabric|fabrics|pending|received|revenue|sales|sale|samples?|vendors?|"
                          r"fabricators?|stock|target|overdue|delayed|delay|production|crore|cr|rs|rupees?|amount|"
                          r"clients?|categor\w+|date|due|delivery|delivered|status|late|lead|risk|approved|rejected|"
                          r"order by|ordered by|mtr|meters?)\b")
CUSTOMERWISE = re.compile(r"\b(customers?|designers?|each|every|wise|har|sabhi|sab|all)\b|customer wise|designer wise")
RANK_W = re.compile(r"\b(highest|most|top|maximum|max|best|lowest|least|fewest|minimum|min|sabse|zyada|jyada)\b")
WHO_W = re.compile(r"\b(which|who|whose|kaun|kaunsa|konsa|kiske|kiska|kisne|customers?|designers?)\b")
LOW_W = re.compile(r"\b(lowest|least|fewest|minimum|min|sabse kam)\b")
DETAIL_W = re.compile(r"\b(details?|detail|breakdown|show|list|dikhao|dikhaye|batao full|full)\b")
SHARE_W = re.compile(r"(%|\bpercent\w*|\bpct\b|\bprati?shat\b|\bfisadi\b)")
COMPARE_W = re.compile(r"\b(compare|comparison|vs|versus|mukabla|between)\b")
GLOBAL_W = re.compile(r"\b(total|overall|all|everyone|company|flo|sab|sabhi|kul|entire|whole|each|every|har|"
                      r"customers|designers)\b")
PRONOUN_W = re.compile(r"\b(her|his|their|she|he|they|them|its|uska|uski|uske|unka|unki|iska|inka|are|is)\b")
FOLLOW_OK = re.compile(r"\b(how much|how many|kitna|kitne|kitni|what|and|aur|also|loss|nuksan|nuksaan|change|"
                       r"difference|fark|percent\w*|growth)\b|%")


@dataclass
class Row:
    designs: int = 0
    pcs: float = 0.0
    new_pcs: float = 0.0
    repeat_pcs: float = 0.0


def n(v: float) -> str:
    return calc.num(v)


def plural(count: float, noun: str) -> str:
    """'1 order' / '27 orders' (noun is given in the plural)."""
    return f"{n(count)} {noun[:-1] if abs(count) == 1 and noun.endswith('s') else noun}"


def p2(v: float) -> str:
    return f"{abs(v):.2f}%"


def _row_of(columns: list[str], values: list) -> Row:
    pos = {c.lower(): i for i, c in enumerate(columns)}

    def at(name):
        i = pos.get(name)
        return float(values[i]) if i is not None and isinstance(values[i], (int, float)) else 0.0

    return Row(designs=int(at("design count")), pcs=at("total volume (pcs)"), new_pcs=at("new orders (pcs)"),
               repeat_pcs=at("repeat orders (pcs)"))


@dataclass
class Spec:
    mode: str                                   # value | details | rank | table | compare | share | period
    kind: str | None = None                     # None (all) | NEW | REPEAT
    unit: str = "designs"                       # designs | pcs  (which one leads the sentence)
    noun: str = "orders"                        # the word the person used: orders | designs
    designers: list = field(default_factory=list)      # Entity objects
    months: list[str] = field(default_factory=list)
    ascending: bool = False
    prior: list = field(default_factory=list)     # months already talked about in this conversation
    pct_first: bool = False                     # "what is the percentage decrease" -> lead with the percentage


class OrderAnalyst:
    def __init__(self, fetch: Callable[[str, dict], dict], running_note: Callable[[str], str] | None = None,
                 today_month: Callable[[], str | None] = lambda: None):
        self.fetch = fetch
        self.running_note = running_note or (lambda m: "")
        self.today_month = today_month
        self._tables: dict = {}

    # -------------------------------------------------------------------------------------------- understanding
    def parse(self, q, ctx: dict | None, vocab) -> Spec | None:
        """Is this an order question? Returns what is asked, or None to leave it to the other answers."""
        fy_months = vocab.months
        t = norm(q.text)
        raw = q.text.lower()
        octx = (ctx or {}).get("orders") if isinstance(ctx, dict) else None
        if "client" in t or "po" in t.split() or any(e.type in ("client", "po", "vendor", "fabricator") for e in q.entities):
            return None
        designers = [e for e in q.entities if e.type == "designer"]
        has_order = bool(ORDER_W.search(t))
        growth = bool(calc.GROWTH.search(t) or calc.DIFF.search(t) or re.search(r"\b(loss|nuksa?an|decrease\w*)\b", t))
        pct = bool(SHARE_W.search(raw))
        follow = False
        if not has_order:
            # "and November?", "how much decrease?", "what is the percentage?" after an order answer
            if not octx or OTHER_METRIC.search(t) or len(q.toks) > 8:
                return None
            if not (FOLLOW_OK.search(raw) or q.months or designers):
                return None
            if not (q.months or designers or growth or pct):
                return None
            follow = True
        elif OTHER_METRIC.search(t):
            return None
        elif octx and not designers and octx.get("designers") and not GLOBAL_W.search(t) and (
                len(q.toks) <= 5 or PRONOUN_W.search(t)):
            # "How many are repeat orders?" right after "Ayushi's orders" is still about Ayushi
            designers = self._remembered(octx, vocab)
            if not q.months:
                q.months = [m for m in ((ctx or {}).get("months") or []) if m in fy_months]

        kind = None if (REPEAT_W.search(t) and NEW_W.search(t)) else \
            "REPEAT" if REPEAT_W.search(t) else "NEW" if NEW_W.search(t) else None
        unit = "pcs" if PCS_W.search(t) and not DESIGN_W.search(t) else "designs"
        noun = "designs" if DESIGN_W.search(t) else "orders"
        months = sorted(set(q.months), key=fy_months.index)
        if follow:
            designers = designers or self._remembered(octx, vocab)
            kind = kind or octx.get("kind")
            unit = octx.get("unit", unit) if not PCS_W.search(t) else unit
            noun = octx.get("noun", noun)
            if not months and not (growth or pct):
                months = [m for m in (ctx.get("months") or []) if m in fy_months]     # "and for AYUSHI?" - same period
            if growth or pct:
                seen = [m for m in octx.get("months_seen", []) if m in fy_months]
                months = self._period_months(months, seen, fy_months)
        spec = Spec("value", kind, unit, noun, designers, months, pct_first=pct and not re.search(r"\bhow much\b", t))

        if octx:
            spec.prior = [m for m in octx.get("months_seen", []) if m in fy_months]
        two_months = len(months) >= 2
        wise = bool(CUSTOMERWISE.search(t))
        if follow and pct and not growth and len(months) < 2:
            spec.mode = "share"                 # "show percentage" after a repeat / new order answer
            spec.kind = spec.kind or "REPEAT"
            spec.months = [m for m in ((ctx or {}).get("months") or []) if m in fy_months]
        elif pct and (kind or "repeat" in t) and not growth and (has_order and not follow):
            spec.mode = "share"
            spec.kind = spec.kind or "REPEAT"
        elif growth or (COMPARE_W.search(t) and two_months) or (follow and pct):
            spec.mode = "period"
        elif RANK_W.search(t) and WHO_W.search(t) and not designers:
            spec.mode, spec.ascending = "rank", bool(LOW_W.search(t))
        elif len(designers) >= 2 or (COMPARE_W.search(t) and designers and wise):
            spec.mode = "compare" if len(designers) >= 2 else "table"
        elif wise and not designers and (COMPARE_W.search(t) or re.search(r"\b(wise|each|every|har|sabhi|all|"
                                                                          r"customers?|designers?)\b", t)):
            spec.mode = "table"
        elif designers and DETAIL_W.search(t):
            spec.mode = "details"
        return spec

    @staticmethod
    def _remembered(octx: dict, vocab) -> list:
        """The designer(s) of the previous answer, as Entity objects when the question names none."""
        found = (vocab.entities.get(("designer", name_key(str(nm)))) for nm in octx.get("designers") or [])
        return [e for e in found if e]

    @staticmethod
    def _period_months(named: list[str], seen: list[str], fy: list[str]) -> list[str]:
        """Which two months to compare: the named ones, topped up with the months of the conversation so far."""
        named = list(dict.fromkeys(named))
        if len(named) >= 2:
            return named
        others = [m for m in seen if m not in named]
        if named and others:
            base = max(others, key=fy.index) if all(fy.index(o) < fy.index(named[0]) for o in others) else others[-1]
            return sorted({named[0], base}, key=fy.index)
        if not named and len(seen) >= 2:
            return sorted(seen[-2:], key=fy.index)
        return named

    # -------------------------------------------------------------------------------------------- figures
    def table(self, months: list[str], order_type: str | None) -> tuple[dict, Row]:
        key = (tuple(months), order_type)
        if key not in self._tables:
            f: dict = {}
            if months:
                f["month"] = list(months)
            if order_type:
                f["order_type"] = [order_type]
            body = self.fetch("designer", f)
            tab = body["tables"]["designers"]
            cols = [c["label"] for c in tab["columns"]]
            rows, total = {}, Row()
            for r in tab["rows"]:
                row = _row_of(cols, r)
                if str(r[0]).upper() == "TOTAL":
                    total = row
                else:
                    rows[str(r[0])] = row
            self._tables[key] = (rows, total)
        return self._tables[key]

    def figure(self, designer, months: list[str], kind: str | None) -> Row:
        rows, total = self.table(months, kind)
        if designer is None:
            return total
        return rows.get(designer.raw.get("designer", designer.display), Row())

    # -------------------------------------------------------------------------------------------- answering
    def answer(self, spec: Spec, text: str) -> tuple[str, dict] | None:
        fn = {"value": self._value, "details": self._details, "rank": self._rank, "table": self._table,
              "compare": self._compare, "share": self._share, "period": self._period}[spec.mode]
        out = fn(spec, text)
        if out is None:
            return None
        body, seen = out
        ctx = {"page": "designer", "metric": "Design Count", "intent": "value",
               "entities": [{"type": "designer", "value": d.display} for d in spec.designers],
               "months": spec.months, "dim": None,
               "orders": {"kind": spec.kind, "unit": spec.unit, "noun": spec.noun,
                          "designers": [d.display for d in spec.designers], "months_seen": seen}}
        return body, ctx

    @staticmethod
    def _who(spec: Spec) -> str:
        return " and ".join(f"**{d.display}**" for d in spec.designers) if spec.designers else "FLO"

    @staticmethod
    def _label(spec: Spec) -> str:
        return {"NEW": "new ", "REPEAT": "repeat "}.get(spec.kind or "", "")

    def _in(self, spec: Spec) -> str:
        return f" in {' and '.join(spec.months)}" if spec.months else ""

    def _seen(self, spec: Spec) -> list[str]:
        """Months talked about so far (oldest first, last four), so "and November?" / "how much decrease?" work."""
        out = [m for m in spec.prior if m not in spec.months] + list(spec.months)
        return out[-4:]

    def _value(self, spec: Spec, text: str):
        d = spec.designers[0] if spec.designers else None
        if len(spec.designers) > 1:
            return self._compare(spec, text)
        r = self.figure(d, spec.months, spec.kind)
        who, scope, verb = self._who(spec), self._in(spec), "had" if spec.months else "has"
        if not spec.designers:
            who, verb = "FLO", "had" if spec.months else "has"
        lead_n = "**" + plural(r.designs, self._label(spec) + spec.noun) + "**"
        pcs = f"**{n(r.pcs)} pcs**"
        head = (f"{who} {verb} {lead_n}{scope}, totalling {pcs}." if spec.unit == "designs"
                else f"{who} {verb} {pcs}{scope} across {lead_n}.")
        lines = [head]
        if spec.kind is None:
            nw = self.figure(d, spec.months, "NEW")
            rp = self.figure(d, spec.months, "REPEAT")
            lines.append(f"Of these, **{n(nw.designs)} {'is' if nw.designs == 1 else 'are'} new** ({n(nw.pcs)} pcs) and "
                         f"**{n(rp.designs)} {'is' if rp.designs == 1 else 'are'} repeat** ({n(rp.pcs)} pcs).")
        else:
            tot = self.figure(d, spec.months, None)
            if tot.designs:
                lines.append(f"That is {p2(r.designs / tot.designs * 100)} of all {n(tot.designs)} orders "
                             f"({n(r.designs)} ÷ {n(tot.designs)} × 100).")
        note = self._note(spec.months)
        if note:
            lines.append(note)
        return "\n".join(lines), self._seen(spec)

    def _note(self, months: list[str]) -> str:
        for m in reversed(months):
            note = self.running_note(m)
            if note:
                return note
        return ""

    def _details(self, spec: Spec, text: str):
        d = spec.designers[0]
        first = self._value(spec, text)
        r = self.figure(d, spec.months, None)
        nw, rp = self.figure(d, spec.months, "NEW"), self.figure(d, spec.months, "REPEAT")
        body = self.fetch("designer", {"designer": [d.raw.get("designer", d.display)],
                                       **({"month": spec.months} if spec.months else {})})
        lines = [first[0], "", f"**Order details for {d.display}**",
                 f"• New orders: {n(nw.designs)} designs, {n(nw.pcs)} pcs",
                 f"• Repeat orders: {n(rp.designs)} designs, {n(rp.pcs)} pcs",
                 f"• Total: {n(r.designs)} designs, {n(r.pcs)} pcs"]
        _, total = self.table(spec.months, None)
        if total.pcs:
            lines.append(f"• Share of all FLO pcs: {p2(r.pcs / total.pcs * 100)} ({n(r.pcs)} ÷ {n(total.pcs)} × 100)")
        cat = body["tables"].get("categories")
        if cat:
            cols = [c["label"] for c in cat["columns"]]
            row = next((x for x in cat["rows"] if str(x[0]).upper() == d.display.upper()
                        or str(x[0]) == d.raw.get("designer")), None)
            if row:
                items = sorted(((c, v) for c, v in zip(cols[1:-1], row[1:-1]) if isinstance(v, (int, float)) and v),
                               key=lambda x: -x[1])
                if items:
                    lines.append("• Pcs by category: " + ", ".join(f"{c} {n(v)}" for c, v in items))
        trend = (body.get("charts") or {}).get("monthly_trend")
        if trend and not spec.months:
            s = next((x for x in trend["series"] if x["name"].upper() == d.display.upper()), None)
            if s:
                pts = [f"{m} {n(v)}" for m, v in zip(trend["categories"], s["values"]) if v]
                if pts:
                    lines.append("• Pcs by month: " + ", ".join(pts))
        return "\n".join(lines), self._seen(spec)

    def _rank(self, spec: Spec, text: str):
        kind = spec.kind
        rows, _ = self.table(spec.months, kind)
        items = [(name, r) for name, r in rows.items() if r.designs or r.pcs]
        word = {"NEW": "new orders", "REPEAT": "repeat orders"}.get(kind or "", "orders")
        if not items:
            return f"There are no {word}{self._in(spec)} on the dashboard.", self._seen(spec)
        items.sort(key=lambda x: (x[1].designs, x[1].pcs), reverse=not spec.ascending)
        best = items[0]
        tied = [i for i in items if i[1].designs == best[1].designs]
        adj = "lowest" if spec.ascending else "highest"
        if len(tied) > 1:
            lead = (f"{', '.join('**' + i[0] + '**' for i in tied)} are tied for the {adj} number of {word}"
                    f"{self._in(spec)}, with **{n(best[1].designs)}** each.")
        else:
            lead = (f"**{best[0]}** has the {adj} number of {word}{self._in(spec)}: **{n(best[1].designs)}** "
                    f"({n(best[1].pcs)} pcs).")
        lines = [lead, "", f"Top {min(5, len(items))} by {word}:"]
        lines += [f"• {name}: {n(r.designs)} orders ({n(r.pcs)} pcs)" for name, r in items[:5]]
        return "\n".join(lines), self._seen(spec)

    def _table(self, spec: Spec, text: str):
        rows, total = self.table(spec.months, spec.kind)
        nrows, _ = self.table(spec.months, "NEW")
        rrows, _ = self.table(spec.months, "REPEAT")
        items = sorted(((k, v) for k, v in rows.items() if v.designs), key=lambda x: (-x[1].designs, -x[1].pcs))
        if not items:
            return f"There are no {self._label(spec)}orders{self._in(spec)} on the dashboard.", self._seen(spec)
        lines = [f"**{(self._label(spec) + 'orders').capitalize()} by customer (designer){self._in(spec)}:**"]
        for k, v in items:
            extra = ""
            if spec.kind is None:
                extra = f" — new {n(nrows.get(k, Row()).designs)}, repeat {n(rrows.get(k, Row()).designs)}"
            lines.append(f"• {k}: {plural(v.designs, 'orders')}{extra} · {n(v.pcs)} pcs")
        lines.append(f"**Total: {n(total.designs)} orders · {n(total.pcs)} pcs**")
        return "\n".join(lines), self._seen(spec)

    def _compare(self, spec: Spec, text: str):
        figs = [(d, self.figure(d, spec.months, spec.kind)) for d in spec.designers]
        lines = [f"**{self._label(spec).capitalize()}{spec.noun.capitalize()}{self._in(spec)}:**"]
        lines += [f"• {d.display}: {n(r.designs)} {spec.noun} ({n(r.pcs)} pcs)" for d, r in figs]
        hi, lo = max(figs, key=lambda x: x[1].designs), min(figs, key=lambda x: x[1].designs)
        if hi[1].designs == lo[1].designs:
            lines.append(f"Both have the same number of {spec.noun}.")
        else:
            diff = hi[1].designs - lo[1].designs
            more = f", which is {p2(diff / lo[1].designs * 100)} more than {lo[0].display}" if lo[1].designs else ""
            lines.append(f"**{hi[0].display}** has **{n(diff)} more** {spec.noun} than {lo[0].display}{more}.")
            if lo[1].designs:
                lines.append(f"Calculation: {n(hi[1].designs)} − {n(lo[1].designs)} = {n(diff)}; "
                             f"{n(diff)} ÷ {n(lo[1].designs)} × 100 = {p2(diff / lo[1].designs * 100)}.")
        return "\n".join(lines), self._seen(spec)

    def _share(self, spec: Spec, text: str):
        d = spec.designers[0] if spec.designers else None
        part, whole = self.figure(d, spec.months, spec.kind), self.figure(d, spec.months, None)
        who = self._who(spec) if spec.designers else "FLO"
        word = self._label(spec) + "orders"
        if not whole.designs:
            return f"There are no orders{self._in(spec)} for {who}, so a percentage can't be worked out.", self._seen(spec)
        pd = part.designs / whole.designs * 100
        lines = [f"**{p2(pd)}** of {who}'s orders{self._in(spec)} are {word.strip()}: **{n(part.designs)}** of "
                 f"**{n(whole.designs)}** orders.", f"Calculation: {n(part.designs)} ÷ {n(whole.designs)} × 100 = "
                 f"{p2(pd)}."]
        if whole.pcs:
            lines.append(f"By quantity: {n(part.pcs)} ÷ {n(whole.pcs)} pcs = {p2(part.pcs / whole.pcs * 100)}.")
        return "\n".join(lines), self._seen(spec)

    def _period(self, spec: Spec, text: str):
        months = spec.months
        if len(months) < 2:
            if not months:
                return None
            return ("I need two months to compare. Tell me which other month, for example "
                    f"\"compare {months[0]} with the month before\".", self._seen(spec))
        base_m, cur_m = months[0], months[-1]
        if len(spec.designers) > 1:
            return None
        d = spec.designers[0] if spec.designers else None
        a, b = self.figure(d, [base_m], spec.kind), self.figure(d, [cur_m], spec.kind)
        who = self._who(spec) if d else "FLO"
        label = self._label(spec) + spec.noun
        lead_pcs = spec.unit == "pcs"
        av, bv = (a.pcs, b.pcs) if lead_pcs else (a.designs, b.designs)
        unit = "pcs" if lead_pcs else spec.noun
        other_unit = spec.noun if lead_pcs else "pcs"
        ov = (a.designs, b.designs) if lead_pcs else (a.pcs, b.pcs)

        def change(x, y, u):
            delta = y - x
            if delta == 0:
                return "no change", None
            word = "increase" if delta > 0 else "decrease"
            return f"{word} of {n(abs(delta))} {u}", (delta, delta / x * 100 if x else None)

        what, info = change(av, bv, unit)
        lines = [f"**{label.capitalize()}{'' if not d else ' for ' + d.display}**", f"• {base_m}: {n(av)} {unit}",
                 f"• {cur_m}: {n(bv)} {unit}"]
        if info is None:
            lines.append("• There is no change." if av == bv else "")
            summary = "no change"
        else:
            delta, pct = info
            word = "Increase" if delta > 0 else "Decrease"
            lines.append(f"• {word}: {n(abs(delta))} {unit}")
            if pct is not None:
                lines.append(f"• Percentage {word.lower()}: {p2(pct)}")
                lines.append(f"Calculation: {n(bv)} − {n(av)} = {'−' if delta < 0 else ''}{n(abs(delta))}; {n(abs(delta))} ÷ {n(av)} × 100 = {p2(pct)}.")
                summary = f"{label.capitalize()} {'increased' if delta > 0 else 'decreased'} by {n(abs(delta))} ({p2(pct)})."
            else:
                lines.append(f"{base_m} was 0, so a percentage can't be worked out.")
                summary = f"{label.capitalize()} {'increased' if delta > 0 else 'decreased'} by {n(abs(delta))}."
        lines = [x for x in lines if x]
        if spec.pct_first and info is not None and info[1] is not None:
            word = "increase" if info[0] > 0 else "decrease"
            lines.insert(0, f"{who}: a **{p2(info[1])} {word}** in {label} from {base_m} to {cur_m}.")
        elif info is not None:
            lines.insert(0, f"{who}: **{summary}**")
        if ov[0] != ov[1]:
            lines.append(f"{other_unit.capitalize()}: {n(ov[0])} → {n(ov[1])} ({'+' if ov[1] - ov[0] > 0 else '−'}"
                         f"{n(abs(ov[1] - ov[0]))}).")
        stated = self._stated(text)
        if len(stated) == 2:
            if [float(x) for x in stated] == [float(av), float(bv)]:
                lines.append("The two figures you mentioned match the dashboard.")
            else:
                lines.append(f"Note: you mentioned {n(stated[0])} and {n(stated[1])}, but the dashboard shows "
                             f"{n(av)} and {n(bv)}, so I used the dashboard figures.")
        note = self._note([cur_m])
        if note:
            lines.append(note)
        return "\n".join(lines), self._seen(spec)

    @staticmethod
    def _stated(text: str) -> list[float]:
        """Numbers the person typed in themselves (months like 'October-26' and years are ignored)."""
        s = re.sub(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[\s-]*'?\d{2}\b", " ", text.lower())
        s = re.sub(r"\b(?:19|20)\d{2}\b", " ", s)
        return [float(x.replace(",", "")) for x in re.findall(r"(?<![\d.])\d[\d,]*(?:\.\d+)?", s) if "," not in x or len(x) > 3]
