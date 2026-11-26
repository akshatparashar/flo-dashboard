"""Quantity status questions: total, completed, pending, completion % and pending % - for one designer, several
designers, or everyone - on the Production page and the FLO Future page, kept strictly apart.

The two pages measure different things and are never mixed:
  * Production  - all orders in production (all months, or the months asked): total = "In production" pcs,
                  completed = "Received" pcs, pending = "Pending" pcs (pcs still to come back from fabricators).
  * FLO Future  - this month's promised samples: total = "Target Qty (Promised)", completed = "Completed",
                  pending = "Pending" (Qty Promised - Completed).
Which KPI is which comes from ``SOURCES`` below (the pages' own KPI labels); every figure is read from the page's API
with the designer / month filters applied, exactly as the dashboard shows it. Percentages are worked out here:
completion % = completed / total x 100 and pending % = pending / total x 100, and completed + pending is checked
against the total.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

from .text import name_key, norm

# page -> (what the page calls it, role -> the start of the KPI label on that page)
SOURCES = {
    "production": ("Production (all orders in production)",
                   {"total": "In production", "completed": "Received", "pending": "Pending"}),
    "flo-future": ("FLO Future (this month's promised samples)",
                   {"total": "Target Qty", "completed": "Completed", "pending": "Pending"}),
}
ROLE_NAMES = {"total": "Total quantity", "completed": "Completed", "pending": "Pending", "completion": "Completion %",
              "pending_pct": "Pending %", "d_total": "Total designs", "d_ready": "Ready designs",
              "d_pending": "Pending designs", "d_completion": "Completion % (designs)",
              "d_pending_pct": "Pending % (designs)", "pcs_pending": "Pending quantity"}
# pcs role -> the same idea counted in designs
TO_DESIGNS = {"total": "d_total", "completed": "d_ready", "pending": "d_pending", "completion": "d_completion",
              "pending_pct": "d_pending_pct"}
DESIGN_ROLES = set(TO_DESIGNS.values())
READY_STATUSES = {"DONE", "COMPLETED", "COMPLETE"}      # the Production Status values that mean the design is finished
# what "designs" are on each page, in the page's own words (used in the answer)
DESIGN_DEFS = {"production": "a design is one order row in production; Ready = Status DONE (finished), Pending = Status not DONE "
                             "(the Production page's Status filter)",
               "flo-future": "a design is one promised item; Ready = items marked done (the page's \"items done\"), "
                             "Pending = items with pcs still to complete"}
ROLE_NAMES_PAGE = {"production": {"total": "Total in production", "completed": "Received (completed)",
                                  "completion": "Received % (completion)"}}

_TOTAL = re.compile(r"\b(total|target|kul|overall|promised)\b")
_DONE = re.compile(r"\b(completed|complete|done|received|ready|finished|pura|poora|mila|aaya|aaye|tayar|taiyar|"
                   r"tayyar)\b")
_PEND = re.compile(r"\b(pending|baki|baaki|bacha|bache|bachi)\b")
_PCT = re.compile(r"(%|\bpercent\w*|\bpct\b|\bprati?shat\b)")
_COMPLETION = re.compile(r"\bcompletion\b|\b(complete|completed|done)\s*(%|percent\w*|rate)|(%|percent\w*)\s+(complete|"
                         r"completed|done)")
_PENDPCT = re.compile(r"\bpending\s*(%|percent\w*|rate)|(%|percent\w*)\s+(of\s+)?pending")
_BOTH_PAGES = re.compile(r"\b(both pages|both the pages|dono page\w*|dono pages?|separately|alag alag|alag-alag|"
                         r"each page|both sections|donon page\w*)\b")
# words that name another figure: leave those questions to the other answers
_OTHER = re.compile(r"\b(po|pos|fpo|fabric|mtr|meters?|revenue|sales|sale|vendors?|rates?|overdue|delay\w*|late|"
                    r"approved|rejected|samples page|stock|fabricators?|clients?|orders?|designs?|items?|due|"
                    r"visits?|meetings?|outsource|incoming|came|sale|sold|net)\b")
_RANK = re.compile(r"\b(which|who|whose|highest|lowest|most|least|top|bottom|kaun|kiska|kiske|sabse|rank\w*|"
                   r"each|every|har|all designers|sab designers)\b")
_COMPARE_M = re.compile(r"\b(vs|versus)\b")
_BOTH_D = re.compile(r"\b(dono|both|compare (?:them|both)|kiska|kaun|kon|kaunsa|better|behtar|aage|performance|"
                     r"higher|lower|zyada|jyada|kam)\b")
_DIFF_W = re.compile(r"\b(difference|diff|fark|farak|antar|gap|points?)\b")
_FOLLOW_OK = {"compare", "both", "designer", "designers", "dono", "karo", "show", "about", "same", "wise", "kiska", "kaun",
              "better", "behtar", "aage", "performance", "difference", "diff", "fark", "percentage", "points", "point",
              "kitna", "kitne", "higher", "lower", "ab", "bhi", "batao", "dikhao", "mein", "page", "pages", "alag",
              "comparison", "data", "separately", "ka", "ki", "ke", "hai", "hain", "zyada", "kam", "jyada", "kon",
              "kaunsa", "percent", "percentage", "rate", "point", "alag-alag", "alag", "dikhao", "dono", "perform", "performing",
              "performance", "perform", "too", "also", "now", "raha", "rahi", "kar", "saath", "sath", "with", "mukabla", "pichhle", "pichle", "se", "hua"}
_WITH = re.compile(r"\b(saath|sath|with|vs|versus|mukabla)\b")
_FOLLOW_ONLY = re.compile(r"^\s*(what about|how about|and|aur|or|for|same for|uska|unka)?\s*[\w\s]*\??\s*$")


@dataclass
class Ask:
    roles: list[str]
    pages: list[str]
    designers: list = field(default_factory=list)       # Entity objects (type designer)
    months: list[str] = field(default_factory=list)
    compare: bool = False
    unit: str = "pcs"
    diff_only: bool = False                              # "kitna difference hai?": just the values and the gap
    side_by_side: bool = False                           # "dono pages ka data alag-alag": one table, a column per page


_PCS_W = re.compile(r"\b(pcs|pc|pieces?|quantity|qty|mtr)\b")
_DES_W = re.compile(r"\b(designs?|items?|collections?)\b")
_COUNT_W = re.compile(r"\b(kitne|kitni|how many)\b")


def unit_of(t: str, prior: str | None) -> str:
    """Designs (a count of designs / items) or pcs (a quantity): the words decide, then the conversation."""
    if _PCS_W.search(t):
        return "pcs"
    if _DES_W.search(t) or re.search(r"\b(ready|tayar|taiyar|tayyar)\b", t):
        return "designs"
    if prior:
        return prior
    return "designs" if _COUNT_W.search(t) else "pcs"


def roles_in(t: str) -> list[str]:
    """Which of total / completed / pending / completion % / pending % the words ask for, in the order asked."""
    found = []
    if _COMPLETION.search(t):
        found.append(("completion", _COMPLETION.search(t).start()))
    if _PENDPCT.search(t):
        found.append(("pending_pct", _PENDPCT.search(t).start()))
    for role, rx in (("total", _TOTAL), ("completed", _DONE), ("pending", _PEND)):
        m = rx.search(t)
        if m:
            found.append((role, m.start()))
    if _PCT.search(t) and not any(r in ("completion", "pending_pct") for r, _ in found) and \
            any(r == "completed" for r, _ in found):
        found.append(("completion", _PCT.search(t).start()))
    roles = [r for r, _ in sorted(found, key=lambda x: x[1])]
    if "completion" in roles and "completed" in roles and not re.search(r"\b(completed|received|done)\b(?!\s*(%|perc))",
                                                                         _COMPLETION.sub(" ", t)):
        roles.remove("completed")
    if "pending_pct" in roles and "pending" in roles and not _PEND.search(_PENDPCT.sub(" ", t)):
        roles.remove("pending")
    return list(dict.fromkeys(roles))


class StatusAnalyst:
    def __init__(self, fetch: Callable[[str, dict], dict], page_labels: dict[str, str]):
        self.fetch = fetch
        self.page_labels = page_labels
        self._cache: dict = {}

    # ------------------------------------------------------------------------------------------------ understanding
    def _base(self, ctx) -> dict | None:
        """What the last answer was about: a status answer's own memory, or (from an orders answer) the designer(s)."""
        if not isinstance(ctx, dict):
            return None
        if ctx.get("status"):
            return ctx["status"]
        o = ctx.get("orders")
        if o and o.get("designers"):
            return {"roles": [], "unit": "designs", "pages": list(SOURCES), "designers": o["designers"],
                    "months": ctx.get("months") or []}
        return None

    def parse(self, q, ctx: dict | None, history: list[dict], vocab) -> Ask | None:
        t = norm(q.text)
        if re.search(r"\b(came|incoming|sold|sale|net sale)\b", t):
            return None                              # In/Out Sale figures
        if re.search(r"\b(tasks?|delegat\w*|awaiting|responsible)\b", t):
            return None                              # Daily Delegation
        sctx = self._base(ctx)
        designers = [e for e in q.entities if e.type == "designer"]
        if any(e.type not in ("designer", "month") for e in q.entities):
            return None
        unit = unit_of(t, (sctx or {}).get("unit"))
        roles = roles_in(t)
        if unit == "designs":
            roles = [TO_DESIGNS.get(r, r) for r in roles]
        named = [p for p in q.explicit if p in SOURCES]
        if _BOTH_PAGES.search(t) or ("production" in t and re.search(r"\bflo future\b|\bfuture\b", t)):
            named = list(SOURCES)
        both = bool(_BOTH_D.search(t)) or bool(re.search(r"\b(compare|vs|versus|mukabla)\b", t))
        side = bool(_BOTH_PAGES.search(t)) and len(named) > 1

        # ---- "Show Charu's production", "Compare Production and FLO Future for Charu": every status figure
        if not roles and designers and named and not _OTHER.search(t) and not re.search(r"\b(volume|repeat\w*)\b", t) \
                and re.search(r"\b(show|data|details?|compare|comparison|batao|dikhao|status|summary|overview|"
                              r"production|future|kya|what|how)\b", t):
            roles = ["d_total", "d_ready", "d_pending", "total", "completed", "pending", "completion"]
            return Ask(roles, named, designers, list(q.months), compare=len(designers) > 1, unit="designs",
                       side_by_side=len(named) > 1 and len(designers) == 1)

        # ---- a follow-up that names no figure: "What about Ayushi?", "Dono mein kaun aage hai?", "Kitna difference?"
        if not roles:
            if not sctx or not sctx.get("roles"):
                return None
            left = {x for x in q.metric_toks if "wise" not in x} - _FOLLOW_OK
            if _OTHER.search(t) or left:
                return None
            roles = list(sctx["roles"])
            prior = self._names(sctx.get("designers"), vocab)
            if (_BOTH_D.search(t) or _DIFF_W.search(t)) and len(designers) < 2 and not designers:
                designers = self._last_two(history or [ctx], vocab)
            elif designers and _WITH.search(t) and prior:          # "Ab Kirti ke saath compare karo": add to the pair
                designers = self._uniq([*prior, *designers])
            if not designers and not q.months and not named and not (_BOTH_D.search(t) or _DIFF_W.search(t)):
                return None
            designers = designers or prior
            pages = named or list(sctx.get("pages") or [])
            months = q.months or list(sctx.get("months") or [])
            return Ask(roles, pages, designers, months, compare=len(designers) > 1, unit=sctx.get("unit", unit),
                       side_by_side=side or (bool(sctx.get("side")) and not q.explicit),
                       diff_only=bool(_DIFF_W.search(t)) and len(designers) > 1)

        if re.search(r"\bsamples?\b", t) and not re.search(r"\b(promis\w*|flo future|future|vaada|commit\w*)\b", t):
            return None                              # the Samples page's own figures
        # ---- a question that names its figures
        if re.search(r"\b(volume|repeat\w*|new orders?|orders?)\b", t):
            return None                              # order figures belong to the Designers page
        design_status = unit == "designs" and any(r in DESIGN_ROLES and r != "d_total" for r in roles)
        if _OTHER.search(_DES_W.sub(" ", t) if design_status else t) and not re.search(r"\b(qty|quantity|pcs|pieces)\b", t):
            return None
        if (_RANK.search(t) and len(designers) < 2) or (re.search(r"\b(percent\w*|%)\s+of\b", t) and "completion" not in t) or \
                re.search(r"\bof\b.*\b(is|are)\s+pending\b|\bme\s*$", t) or \
                (re.search(r"\btarget\b", t) and not designers and len(named) < 2):
            return None
        if len(designers) < 2 and sctx and (both or _DIFF_W.search(t) or _WITH.search(t)):
            prior = self._last_two(history or [ctx], vocab)
            designers = self._uniq([*prior, *designers]) if designers else prior
        if unit == "designs" and not design_status and not (designers and sctx):
            return None                              # plain "total designs" is the Designers page's order count
        if not designers and len(named) < 2 and not (named and (len(roles) >= 2 or roles == ["total"]) and not _COMPARE_M.search(t)) \
                and not design_status:
            return None                              # page-wide single figures: the normal answers handle them
        if not designers and sctx and len(q.toks) <= 6 and not re.search(r"\b(total|overall|all|sab|sabhi)\b", t) \
                and not named:
            designers = self._names(sctx.get("designers"), vocab)
        pages = named or self._pages_for(roles, t, unit)
        return Ask(roles, pages, designers, list(q.months) or list((sctx or {}).get("months") or []),
                   compare=len(designers) > 1, unit=unit, side_by_side=side)

    @staticmethod
    def _pages_for(roles: list[str], t: str, unit: str = "pcs") -> list[str]:
        """No page named: the words decide when they belong to one page only, otherwise both pages are shown."""
        if unit == "designs":
            return list(SOURCES)
        if re.search(r"\b(promis\w*|target|this month'?s? samples|vaada|vada|wada|commit\w*)\b", t) or \
                (re.search(r"\b(completed|complete|done)\b", t) and not re.search(r"\bcompletion\b", t)):
            return ["flo-future"]
        if re.search(r"\b(received|in production|fabricator|production)\b", t):
            return ["production"]
        return list(SOURCES)

    @staticmethod
    def _uniq(ents: list) -> list:
        seen, out = set(), []
        for e in ents:
            if e.key not in seen:
                seen.add(e.key)
                out.append(e)
        return out

    @staticmethod
    def _names(names, vocab) -> list:
        out = []
        for nm in names or []:
            e = vocab.entities.get(("designer", name_key(str(nm))))
            if e:
                out.append(e)
        return out

    def _last_two(self, history: list[dict], vocab) -> list:
        """The two designers talked about last, in the order they were first named (older one first)."""
        seen: list = []
        for c in reversed([h for h in history if isinstance(h, dict)]):
            names = ((c.get("status") or {}).get("designers")) or [e.get("value") for e in c.get("entities") or []
                                                                      if e.get("type") == "designer"]
            seen = [n for n in names if n not in seen] + seen
            if len(seen) >= 2:
                break
        return self._names(seen[-2:], vocab)

    # ------------------------------------------------------------------------------------------------ figures
    def _get(self, page: str, f: dict) -> dict:
        key = (page, repr(sorted((k, tuple(v)) for k, v in f.items())))
        if key not in self._cache:
            self._cache[key] = self.fetch(page, f)
        return self._cache[key]

    @staticmethod
    def _kpi(body: dict, start: str):
        k = next((k for k in body.get("kpis") or [] if str(k.get("label", "")).startswith(start)), None)
        return float(k["value"]) if k and isinstance(k.get("value"), (int, float)) else None

    def figures(self, page: str, designer, months: list[str], designs: bool = False) -> dict:
        """total / completed / pending pcs for one page and one designer (None = everyone), from the page's KPIs;
        with ``designs`` also the design counts (Production: its Status filter; FLO Future: its items)."""
        f: dict = {}
        if designer is not None:
            raw = designer.raw.get(page)
            if raw is None:
                return {"missing": True}
            f["designer"] = [raw]
        if months and page == "production":
            f["month"] = list(months)
        body = self._get(page, f)
        out = {role: self._kpi(body, start) for role, start in SOURCES[page][1].items()}
        out["period"] = (body.get("period") if page == "flo-future" else
                         (" and ".join(months) if months else "all months so far"))
        out["flo"] = page == "flo-future"
        if designs:
            out.update(self._design_counts(page, f, body))
        return out

    def _design_counts(self, page: str, f: dict, body: dict) -> dict:
        if page == "production":
            total = self._kpi(body, "Designs in production")
            statuses = (body.get("options") or {}).get("status") or []
            done = [s for s in statuses if str(s).upper() in READY_STATUSES]
            ready = self._kpi(self._get(page, {**f, "status": done}), "Designs in production") if done else None
            return {"d_total": total, "d_ready": ready,
                    "d_pending": None if total is None or ready is None else total - ready}
        summ = body.get("summary") or {}
        rows = (body.get("tables") or {}).get("items") or {}
        cols = [c["label"] for c in rows.get("columns") or []]
        pend_i = cols.index("Pending") if "Pending" in cols else None
        stat_i = cols.index("Status") if "Status" in cols else None
        rem_i = cols.index("Remark") if "Remark" in cols else None
        name_i = 0
        items = [r for r in rows.get("rows") or [] if r and not str(r[0]).startswith(("TOTAL", "("))
                 and not re.search(r"items?$", str(r[-1]) if r else "")] if pend_i is not None else []
        items = [r for r in items if isinstance(r[pend_i], (int, float)) and "% done" not in str(r[0])]
        d_total = summ.get("items")
        zero = [r for r in items if r[pend_i] <= 0 and (stat_i is None or str(r[stat_i]).lower() != "complete")]
        zero_info = [{"name": str(r[name_i]), "remark": str(r[rem_i] or "") if rem_i is not None else "",
                      "status": str(r[stat_i]) if stat_i is not None else ""} for r in zero]
        return {"d_total": float(d_total) if d_total is not None else None,
                "d_ready": float(summ["items_done"]) if summ.get("items_done") is not None else None,
                "d_pending": float(sum(1 for r in items if r[pend_i] > 0)) if pend_i is not None else None,
                "d_zero": zero_info if pend_i is not None else None}

    # ------------------------------------------------------------------------------------------------ answering
    def answer(self, ask: Ask) -> tuple[str, dict]:
        blocks = []
        if ask.side_by_side and len(ask.pages) > 1 and len(ask.designers) <= 1:
            blocks.append(self._pages_table(ask))
        else:
            for page in ask.pages:
                blocks.append(self._compare_block(page, ask) if ask.compare else
                              self._card(page, ask, ask.designers[0] if ask.designers else None))
            if len(ask.pages) > 1:
                blocks.append("These are two different measures: Production counts pcs of orders still with "
                              "fabricators; FLO Future counts this month's promised samples. They are shown "
                              "separately and never added.")
        defs = [f"{self.page_labels[p]}: {DESIGN_DEFS[p]}." for p in ask.pages
                if ask.unit == "designs" and any(r in DESIGN_ROLES for r in ask.roles)]
        if defs:
            blocks.append("How designs are counted - " + " ".join(defs))
        ctx = {"page": ask.pages[0], "metric": ROLE_NAMES[ask.roles[0]], "intent": "status",
               "entities": [{"type": "designer", "value": d.display} for d in ask.designers],
               "months": ask.months, "dim": None,
               "status": {"roles": ask.roles, "pages": ask.pages, "designers": [d.display for d in ask.designers],
                          "months": ask.months, "unit": ask.unit, "side": ask.side_by_side}}
        return "\n\n".join(b for b in blocks if b), ctx

    def _role_name(self, page: str, role: str) -> str:
        return ROLE_NAMES_PAGE.get(page, {}).get(role, ROLE_NAMES[role])

    @staticmethod
    def _pct(part, whole):
        return None if part is None or not whole else part / whole * 100

    def _value(self, fig: dict, role: str):
        if role == "completion":
            return self._pct(fig.get("completed"), fig.get("total"))
        if role == "pending_pct":
            return self._pct(fig.get("pending"), fig.get("total"))
        if role == "d_completion":
            return self._pct(fig.get("d_ready"), fig.get("d_total"))
        if role == "d_pending_pct":
            return self._pct(fig.get("d_pending"), fig.get("d_total"))
        if role == "pcs_pending":
            return fig.get("pending")
        return fig.get(role)

    @staticmethod
    def _show(role: str, v) -> str:
        if v is None:
            return "not available"
        if role in ("completion", "pending_pct", "d_completion", "d_pending_pct"):
            return f"{v:.2f}%"
        if role in DESIGN_ROLES:
            return f"{v:,.0f} {'design' if abs(v) == 1 else 'designs'}"
        return f"{v:,.0f} pcs"

    def _wants_designs(self, ask: Ask) -> bool:
        return any(r in DESIGN_ROLES for r in ask.roles)

    @staticmethod
    def _wants_completion(ask: Ask) -> bool:
        return any(r in ("completion", "d_completion") for r in ask.roles)

    def _card(self, page: str, ask: Ask, designer) -> str:
        label = SOURCES[page][0]
        fig = self.figures(page, designer, ask.months, designs=self._wants_designs(ask) or self._wants_completion(ask))
        who = designer.display if designer else "All designers"
        if fig.get("missing"):
            return f"**{label}**\n{who} does not appear on the {self.page_labels[page]} page, so it has no figures there."
        lines = [f"**{label}**", f"Designer: **{who}** · Period: {fig['period']}"]
        for role in ask.roles:
            v = self._value(fig, role)
            line = f"• {self._role_name(page, role)}: **{self._show(role, v)}**"
            if role == "completion" and v is not None:
                line += f" ({fig['completed']:,.0f} ÷ {fig['total']:,.0f} × 100)"
            if role == "pending_pct" and v is not None:
                line += f" ({fig['pending']:,.0f} ÷ {fig['total']:,.0f} × 100)"
            if role == "d_completion" and v is not None:
                line += f" ({fig['d_ready']:,.0f} ÷ {fig['d_total']:,.0f} × 100)"
            if role == "d_pending_pct" and v is not None:
                line += f" ({fig['d_pending']:,.0f} ÷ {fig['d_total']:,.0f} × 100)"
            if role in ("completion", "pending_pct", "d_completion", "d_pending_pct") and v is None:
                line += " (total is 0, so a percentage can't be worked out)"
            lines.append(line)
        if self._wants_designs(ask) and "d_pending" in ask.roles and "pending" not in ask.roles:
            lines.append(f"• Pending quantity: **{self._show('pending', fig.get('pending'))}**")
        if self._wants_completion(ask):
            by_pcs, by_des = self._value(fig, "completion"), self._value(fig, "d_completion")
            if "completion" in ask.roles and by_des is not None:
                lines.append(f"• Same figure counted in designs: {by_des:.2f}% ({fig['d_ready']:,.0f} ÷ {fig['d_total']:,.0f}); "
                             "the percentage above counts pcs, so the two differ.")
            if "d_completion" in ask.roles and by_pcs is not None:
                lines.append(f"• Same figure counted in pcs: {by_pcs:.2f}% ({fig['completed']:,.0f} ÷ {fig['total']:,.0f}); "
                             "the percentage above counts designs, so the two differ.")
        lines.append(self._check(fig, designs=self._wants_designs(ask), pcs=not self._wants_designs(ask) or
                                 any(r in ask.roles for r in ("pending", "total", "completed", "completion"))))
        if ask.months and page == "production":
            lines.append("Note: on the Production page a month means the order's month (client order date). The "
                         "dashboard has no completion date, so this counts orders from that month that are now finished, "
                         "not designs finished during that month.")
            if fig.get("d_total") == 0 or fig.get("total") == 0:
                lines.append(f"{who} has no Production rows for {' and '.join(ask.months)}.")
        if ask.months and page == "flo-future":
            lines.append(f"Note: FLO Future only holds {fig['period']}; the month you asked for doesn't apply to it.")
        return "\n".join(x for x in lines if x)

    def _check(self, fig: dict, designs: bool = False, pcs: bool = True) -> str:
        out = []
        tot, done, pend = fig.get("total"), fig.get("completed"), fig.get("pending")
        if pcs and None not in (tot, done, pend):
            if abs(done + pend - tot) < 0.5:
                out.append(f"Check: completed {done:,.0f} + pending {pend:,.0f} = total {tot:,.0f} pcs ✓")
            else:
                out.append(f"Check: completed {done:,.0f} + pending {pend:,.0f} = {done + pend:,.0f}, not the total "
                           f"{tot:,.0f} - the page counts {abs(tot - done - pend):,.0f} pcs in neither (for example "
                           f"cancelled or extra received pcs), so the figures are shown as the dashboard has them.")
        dt, dr, dp = fig.get("d_total"), fig.get("d_ready"), fig.get("d_pending")
        if designs and None not in (dt, dr, dp):
            if abs(dr + dp - dt) < 0.5:
                out.append(f"Check: ready {dr:,.0f} + pending {dp:,.0f} = total {dt:,.0f} designs ✓")
            else:
                out.append(f"Check: ready {dr:,.0f} + pending {dp:,.0f} = {dr + dp:,.0f}, not the total {dt:,.0f} "
                           f"designs - the dashboard's definitions overlap or leave some out; shown as it has them.")
            zero = fig.get("d_zero")
            if zero is not None and fig.get("flo"):
                out.append(self._categories(dt, dr, dp, zero))
        return "\n".join(out)

    @staticmethod
    def _categories(dt, dr, dp, zero: list) -> str:
        lines = ["Item categories (FLO Future):", f"  • Total promised items: {dt:,.0f}",
                 f"  • Items marked done: {dr:,.0f}",
                 f"  • Items with pcs still remaining: {dp:,.0f}",
                 f"  • Items with zero remaining pcs but not marked done: {len(zero)}"]
        for z in zero:
            why = z["remark"] or "no pcs are left to complete"
            lines.append(f"      - {z['name']} (status: {z['status'] or 'blank'}; {why})")
        rest = dt - dr - dp - len(zero)
        if abs(rest) < 0.5:
            lines.append(f"  So {dr:,.0f} done + {dp:,.0f} with pcs remaining + {len(zero)} zero-remaining = {dt:,.0f} items.")
        return "\n".join(lines)

    def _pages_table(self, ask: Ask) -> str:
        """One designer (or everyone), the pages side by side: a column per page, same rows."""
        designer = ask.designers[0] if ask.designers else None
        wants_d = self._wants_designs(ask) or ask.unit == "designs"
        figs = {p: self.figures(p, designer, ask.months, designs=wants_d) for p in ask.pages}
        who = designer.display if designer else "All designers"
        cols = [SOURCES[p][0].split(" (")[0] for p in ask.pages]
        rows = [("Designer", [who] * len(ask.pages))]
        roles = list(ask.roles)
        if wants_d and "d_pending" in roles and "pending" not in roles:
            roles.append("pending")
        for role in roles:
            name = "Pending quantity" if (role == "pending" and wants_d) else ROLE_NAMES[role]
            rows.append((name, ["—" if figs[p].get("missing") else self._show(role, self._value(figs[p], role))
                                for p in ask.pages]))
        rows.append(("Period", [figs[p].get("period", "—") if not figs[p].get("missing") else "—" for p in ask.pages]))
        lines = ["| Metric | " + " | ".join(cols) + " |", "|---|" + "---|" * len(cols)]
        lines += [f"| {m} | " + " | ".join(v) + " |" for m, v in rows]
        gone = [self.page_labels[p] for p in ask.pages if figs[p].get("missing")]
        if gone:
            lines.append(f"{who} does not appear on the {', '.join(gone)} page, so there are no figures there.")
        lines.append("Each column comes from its own page; nothing is carried over from one page to the other.")
        return "\n".join(lines)

    def _compare_block(self, page: str, ask: Ask) -> str:
        label = SOURCES[page][0]
        figs = [(d, self.figures(page, d, ask.months, designs=True)) for d in ask.designers]
        names = [d.display for d, _ in figs]
        period = next((f["period"] for _, f in figs if not f.get("missing")), "")
        # same rows for every designer: the asked figures first, then the usual ones (only those the page has)
        usual = ["d_ready", "d_pending", "d_total", "pcs_pending", "completion", "d_completion"]
        roles = list(ask.roles) if ask.diff_only else list(dict.fromkeys(list(ask.roles) + usual))
        if "pending" in roles and "pcs_pending" in roles:
            roles.remove("pcs_pending")
        ok = [(d, f) for d, f in figs if not f.get("missing")]
        roles = [r for r in roles if r in ask.roles or any(self._value(f, r) is not None for _, f in ok)]
        lines = [f"**{label}** · Period: {period}", "| Metric | " + " | ".join(names) + " |",
                 "|---|" + "---|" * len(names)]
        for role in roles:
            cells = ["—" if f.get("missing") else self._show(role, self._value(f, role)) for _, f in figs]
            lines.append(f"| {self._cmp_name(page, role)} | " + " | ".join(cells) + " |")
        missing = [d.display for d, f in figs if f.get("missing")]
        if missing:
            lines.append(f"{', '.join(missing)} {'does' if len(missing) == 1 else 'do'} not appear on this page.")
        if len(ok) >= 2:
            for role in ask.roles:
                vals = [(d, self._value(f, role)) for d, f in ok]
                if any(v is None for _, v in vals):
                    continue
                lines.append(self._gap_line(self._cmp_name(page, role), role, vals))
        return "\n".join(lines)

    def _cmp_name(self, page: str, role: str) -> str:
        return {"pcs_pending": "Pending pcs", "pending": "Pending pcs", "completion": "Completion % (by pcs)",
                "d_completion": "Completion % (by designs)", "total": "Total pcs", "completed": "Completed pcs"}.get(
            role) or self._role_name(page, role)

    def _gap_line(self, name: str, role: str, vals: list) -> str:
        pct = role in ("completion", "pending_pct", "d_completion", "d_pending_pct")
        unit = "designs" if role in DESIGN_ROLES else "pcs"
        hi = max(vals, key=lambda x: x[1])
        lo = min(vals, key=lambda x: x[1])
        hv, lv = hi[1], lo[1]
        if hv == lv:
            return f"{name}: all the same ({self._show(role, hv)})."
        if len(vals) == 2:
            if pct:
                return f"{name}: **{hi[0].display}** is higher by **{hv - lv:.2f} percentage points** ({hv:.2f}% − {lv:.2f}%)."
            more = f", {(hv - lv) / lv * 100:.2f}% more" if lv else ""
            return f"{name}: **{hi[0].display}** is higher by **{hv - lv:,.0f} {unit}** ({hv:,.0f} − {lv:,.0f}{more})."
        if pct:
            return (f"{name}: highest **{hi[0].display}** ({hv:.2f}%), lowest **{lo[0].display}** ({lv:.2f}%), "
                    f"a spread of **{hv - lv:.2f} percentage points**.")
        return (f"{name}: highest **{hi[0].display}** ({hv:,.0f}), lowest **{lo[0].display}** ({lv:,.0f}), "
                f"a spread of **{hv - lv:,.0f} {unit}**.")
