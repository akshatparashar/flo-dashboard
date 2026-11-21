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
              "pending_pct": "Pending %"}
ROLE_NAMES_PAGE = {"production": {"total": "Total in production", "completed": "Received (completed)",
                                  "completion": "Received % (completion)"}}

_TOTAL = re.compile(r"\b(total|target|kul|overall|promised)\b")
_DONE = re.compile(r"\b(completed|complete|done|received|ready|finished|pura|poora|mila|aaya|aaye)\b")
_PEND = re.compile(r"\b(pending|baki|baaki|bacha|bache|bachi)\b")
_PCT = re.compile(r"(%|\bpercent\w*|\bpct\b|\bprati?shat\b)")
_COMPLETION = re.compile(r"\bcompletion\b|\b(complete|completed|done)\s*(%|percent\w*|rate)|(%|percent\w*)\s+(complete|"
                         r"completed|done)")
_PENDPCT = re.compile(r"\bpending\s*(%|percent\w*|rate)|(%|percent\w*)\s+(of\s+)?pending")
_BOTH_PAGES = re.compile(r"\b(both pages|both the pages|dono page\w*|separately|alag alag|alag-alag|each page|"
                         r"both sections)\b")
# words that name another figure: leave those questions to the other answers
_OTHER = re.compile(r"\b(po|pos|fpo|fabric|mtr|meters?|revenue|sales|sale|vendors?|rates?|overdue|delay\w*|late|"
                    r"approved|rejected|samples page|stock|fabricators?|clients?|orders?|designs?|items?|due|"
                    r"visits?|meetings?|outsource)\b")
_RANK = re.compile(r"\b(which|who|whose|highest|lowest|most|least|top|bottom|kaun|kiska|kiske|sabse|rank\w*|"
                   r"each|every|har|all designers|sab designers)\b")
_COMPARE_M = re.compile(r"\b(vs|versus)\b")
_FOLLOW_ONLY = re.compile(r"^\s*(what about|how about|and|aur|or|for|same for|uska|unka)?\s*[\w\s]*\??\s*$")


@dataclass
class Ask:
    roles: list[str]
    pages: list[str]
    designers: list = field(default_factory=list)       # Entity objects (type designer)
    months: list[str] = field(default_factory=list)
    compare: bool = False


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

    # ------------------------------------------------------------------------------------------------ understanding
    def parse(self, q, ctx: dict | None, history: list[dict], vocab) -> Ask | None:
        t = norm(q.text)
        sctx = (ctx or {}).get("status") if isinstance(ctx, dict) else None
        designers = [e for e in q.entities if e.type == "designer"]
        if any(e.type not in ("designer", "month") for e in q.entities):
            return None
        roles = roles_in(t)
        named = [p for p in q.explicit if p in SOURCES]
        if _BOTH_PAGES.search(t) or ("production" in t and re.search(r"\bflo future\b|\bfuture\b", t)):
            named = list(SOURCES)
        both = bool(re.search(r"\b(compare|vs|versus|mukabla|both|dono)\b", t))

        if not roles:
            if not sctx:
                return None
            # follow-up: "What about Ayushi?", "Compare both designers", "aur November?"
            if _OTHER.search(t) or (q.metric_toks - {"compare", "both", "designer", "dono", "karo", "show", "about",
                                                       "same", "wise"}):
                return None
            roles = list(sctx.get("roles") or [])
            if not designers and both:
                designers = self._last_two(history or [ctx], vocab)
            if not designers and not q.months and not named:
                return None
            designers = designers or self._names(sctx.get("designers"), vocab)
            pages = named or list(sctx.get("pages") or [])
            months = q.months or list(sctx.get("months") or [])
            return Ask(roles, pages, designers, months, compare=len(designers) > 1)

        if _OTHER.search(t) and not re.search(r"\b(qty|quantity|pcs|pieces)\b", t):
            return None
        # rankings, shares of another figure and "remaining target" belong to the other answers
        if _RANK.search(t) or re.search(r"\b(percent\w*|%)\s+of\b|\bof\b.*\b(is|are)\s+pending\b|\bme\s*$", t) or \
                (re.search(r"\btarget\b", t) and not designers and len(named) < 2):
            return None
        if not designers and len(named) < 2 and not (named and len(roles) >= 2 and not _COMPARE_M.search(t)):
            return None                              # page-wide single figures: the normal answers handle them
        if not designers and sctx and len(q.toks) <= 6 and not re.search(r"\b(total|overall|all|sab|sabhi)\b", t) \
                and not named:
            designers = self._names(sctx.get("designers"), vocab)
        if both and len(designers) < 2 and sctx and not designers:
            designers = self._last_two(history or [ctx], vocab)
        pages = named or self._pages_for(roles, t)
        return Ask(roles, pages, designers, list(q.months), compare=len(designers) > 1)

    @staticmethod
    def _pages_for(roles: list[str], t: str) -> list[str]:
        """No page named: the words decide when they belong to one page only, otherwise both pages are shown."""
        if re.search(r"\b(promis\w*|target|this month'?s? samples|vaada|vada|wada|commit\w*)\b", t) or \
                re.search(r"\b(completed|complete|done|completion)\b", t):
            return ["flo-future"]
        if re.search(r"\b(received|in production|fabricator|production)\b", t):
            return ["production"]
        return list(SOURCES)

    @staticmethod
    def _names(names, vocab) -> list:
        out = []
        for nm in names or []:
            e = vocab.entities.get(("designer", name_key(str(nm))))
            if e:
                out.append(e)
        return out

    def _last_two(self, history: list[dict], vocab) -> list:
        seen = []
        for c in reversed([h for h in history if isinstance(h, dict)]):
            names = ((c.get("status") or {}).get("designers")) or [e.get("value") for e in c.get("entities") or []
                                                                      if e.get("type") == "designer"]
            for nm in names:
                if nm not in seen:
                    seen.append(nm)
            if len(seen) >= 2:
                break
        return self._names(list(reversed(seen[:2])), vocab)

    # ------------------------------------------------------------------------------------------------ figures
    def figures(self, page: str, designer, months: list[str]) -> dict:
        """total / completed / pending for one page and one designer (None = everyone), from the page's KPIs."""
        f: dict = {}
        if designer is not None:
            raw = designer.raw.get(page)
            if raw is None:
                return {"missing": True}
            f["designer"] = [raw]
        if months and page == "production":
            f["month"] = list(months)
        body = self.fetch(page, f)
        kpis = body.get("kpis") or []
        out = {}
        for role, start in SOURCES[page][1].items():
            k = next((k for k in kpis if str(k.get("label", "")).startswith(start)), None)
            out[role] = float(k["value"]) if k and isinstance(k.get("value"), (int, float)) else None
        out["period"] = (body.get("period") if page == "flo-future" else
                         (" and ".join(months) if months else "all months so far"))
        return out

    # ------------------------------------------------------------------------------------------------ answering
    def answer(self, ask: Ask) -> tuple[str, dict]:
        blocks = []
        for page in ask.pages:
            if ask.compare:
                blocks.append(self._compare_block(page, ask))
            else:
                blocks.append(self._card(page, ask, ask.designers[0] if ask.designers else None))
        if len(ask.pages) > 1:
            blocks.append("These are two different measures: Production counts pcs of orders still with fabricators; "
                          "FLO Future counts this month's promised samples. They are shown separately and never added.")
        ctx = {"page": ask.pages[0], "metric": ROLE_NAMES[ask.roles[0]], "intent": "status",
               "entities": [{"type": "designer", "value": d.display} for d in ask.designers],
               "months": ask.months, "dim": None,
               "status": {"roles": ask.roles, "pages": ask.pages, "designers": [d.display for d in ask.designers],
                          "months": ask.months}}
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
        return fig.get(role)

    @staticmethod
    def _show(role: str, v) -> str:
        if v is None:
            return "not available"
        if role in ("completion", "pending_pct"):
            return f"{v:.2f}%"
        return f"{v:,.0f} pcs"

    def _card(self, page: str, ask: Ask, designer) -> str:
        label = SOURCES[page][0]
        fig = self.figures(page, designer, ask.months)
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
            if role in ("completion", "pending_pct") and v is None:
                line += " (total is 0, so a percentage can't be worked out)"
            lines.append(line)
        lines.append(self._check(fig))
        if ask.months and page == "flo-future":
            lines.append(f"Note: FLO Future only holds {fig['period']}; the month you asked for doesn't apply to it.")
        return "\n".join(x for x in lines if x)

    def _check(self, fig: dict) -> str:
        tot, done, pend = fig.get("total"), fig.get("completed"), fig.get("pending")
        if None in (tot, done, pend):
            return ""
        if abs(done + pend - tot) < 0.5:
            return f"Check: completed {done:,.0f} + pending {pend:,.0f} = total {tot:,.0f} ✓"
        return (f"Check: completed {done:,.0f} + pending {pend:,.0f} = {done + pend:,.0f}, not the total {tot:,.0f} - "
                f"the page counts {abs(tot - done - pend):,.0f} pcs in neither (for example cancelled or extra "
                f"received pcs), so the figures are shown as the dashboard has them.")

    def _compare_block(self, page: str, ask: Ask) -> str:
        label = SOURCES[page][0]
        figs = [(d, self.figures(page, d, ask.months)) for d in ask.designers]
        names = [d.display for d, _ in figs]
        period = next((f["period"] for _, f in figs if not f.get("missing")), "")
        roles = list(dict.fromkeys(ask.roles + [r for r in ("total", "completed", "pending", "completion")
                                                if r not in ask.roles]))
        lines = [f"**{label}** · Period: {period}", "| Metric | " + " | ".join(names) + " |",
                 "|---|" + "---|" * len(names)]
        for role in roles:
            cells = ["—" if f.get("missing") else self._show(role, self._value(f, role)) for _, f in figs]
            lines.append(f"| {self._role_name(page, role)} | " + " | ".join(cells) + " |")
        missing = [d.display for d, f in figs if f.get("missing")]
        if missing:
            lines.append(f"{', '.join(missing)} {'does' if len(missing) == 1 else 'do'} not appear on this page.")
        ok = [(d, f) for d, f in figs if not f.get("missing")]
        if len(ok) == 2:
            for role in ask.roles:
                a, b = self._value(ok[0][1], role), self._value(ok[1][1], role)
                if a is None or b is None:
                    continue
                if a == b:
                    lines.append(f"{self._role_name(page, role)}: both are the same ({self._show(role, a)}).")
                    continue
                hi, lo = (ok[0], ok[1]) if a > b else (ok[1], ok[0])
                hv, lv = max(a, b), min(a, b)
                if role in ("completion", "pending_pct"):
                    lines.append(f"{self._role_name(page, role)}: **{hi[0].display}** is higher by "
                                 f"**{hv - lv:.2f} points** ({hv:.2f}% vs {lv:.2f}%).")
                else:
                    more = f", {(hv - lv) / lv * 100:.2f}% more" if lv else ""
                    lines.append(f"{self._role_name(page, role)}: **{hi[0].display}** is higher by "
                                 f"**{hv - lv:,.0f} pcs** ({hv:,.0f} − {lv:,.0f}{more}).")
        return "\n".join(lines)
