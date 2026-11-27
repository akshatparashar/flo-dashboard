"""Questions that are not about one figure: what is urgent, where a page is, what FLO World is, and a rate asked for a
fabric the rate list may not group. Each returns (answer, page key, intent) or None.

All figures come from the dashboard's own endpoints (``fetch``).
"""
from __future__ import annotations

import re

from . import fmt
from ..dashboards.vendor_rate import category_in_text

WHERE = re.compile(r"\b(where|kahan|kaha|kidhar|which page|kis page|kaunse page|konse page)\b", re.I)
URGENT = re.compile(r"\b(urgent\w*|needs? (?:my |our )?attention|attention (?:needed|required)|what needs|priorit(?:y|ies)|"
                    r"dhyan (?:dena|do|de|chahiye)|zaroori|zaruri|red flags?|action (?:needed|items?))\b", re.I)
NOT_OVERVIEW = re.compile(r"\b(tasks?|delegation|kaam|sir|mam|flo future|promis\w*|samples?|po|pos|stock|vendors?|"
                          r"fabricators?|designers?|clients?)\b", re.I)

TEAM_STATUS = re.compile(r"^\s*(?:flo future )?team(?:[- ]?wise| ka| ki)? (?:status|progress|report|completion|summary)"
                         r"(?: (?:batao|dikhao|kya hai))?\s*[?.!]*$", re.I)

# (words people use, page label, sidebar group); first match wins
PAGES_WHERE = [
    (r"vendor rates?|fabric rates?|rate (?:list|card|sheet)|price list|rates?", "Vendor Rate", "Operations", "vendor-rate"),
    (r"daily delegation|delegation|daily schedule|daily tasks?|tasks?|task list", "Daily Delegation", "Management",
     "daily-delegation"),
    (r"fabric po|purchase orders?|pos?", "Fabric PO", "Operations", "fabric-po"),
    (r"fabricators?(?: stock)?|karigars?", "Fabricators", "Operations", "fabricator"),
    (r"in ?/? ?out ?/? ?sale|net sale|sale pcs|incoming(?: pcs)?|sales?", "In/Out Sale", "Operations", "in-out-sale"),
    (r"production", "Production", "Operations", "production"),
    (r"designer order target|order target|target|revenue", "Designer Order Target", "Design and sales", "target"),
    (r"flo future|future|promises?|promised samples|meetings?|visits?", "FLO Future", "Design and sales", "flo-future"),
    (r"samples?", "Samples", "Design and sales", "samples"),
    (r"clients?(?: order status)?|fw orders?|expected deliver(?:y|ies)", "Clients Order Status", "Design and sales",
     "client"),
    (r"designers?", "Designers", "Design and sales", "designer"),
    (r"overview|home|summary|alerts?", "Overview", "Operations", "overview"),
]
_FILLER = set("where is are the a page tab section screen dashboard can i we see find view check open get show me my our "
              "kaha kahan kidhar pe par hai hain he dikhega dikhegi dikhenge dikhta dikhti milega milegi milta milti "
              "dekhu dekhe dekhein dekh sakte sakta ka ki ke ko mein which kis kaunse konse on in of do does to "
              "batao bataiye wala wali report data".split())

LABELS = ("community basic classic premium exclusive vibe men curve uncut drape roots whatsapp deal connect label online "
          "care outlet mumbai gratitude").split()
WORLD = re.compile(rf"\bflo[- ]?(world|{'|'.join(LABELS)}|play,? learn|people (?:&|and) culture)\b", re.I)

# "georgette ka rate", "rate of chiffon", "banarasi ka sabse sasta vendor"
ASKS_RATE = [
    re.compile(r"^\s*([a-z][a-z ]{2,30}?) (?:fabric |kapde? )?(?:ka|ke|ki) (?:sabse )?(?:rates?|price|sasta|sasti|"
               r"mehenga|mehnga)\b", re.I),
    re.compile(r"\b(?:rates?|price) (?:of|for) ([a-z][a-z ]{2,30}?)(?: fabric)?\s*[?.!]*$", re.I),
    re.compile(r"\b(?:cheapest|most expensive|best) (?:vendor|rate) (?:of|for) ([a-z][a-z ]{2,30}?)(?: fabric)?\s*[?.!]*$",
               re.I),
]


def _urgent(text: str, fetch) -> tuple[str, str, str] | None:
    if not URGENT.search(text) or NOT_OVERVIEW.search(text):
        return None
    body = fetch("overview", {})
    alerts = [a for a in body.get("alerts") or [] if isinstance(a, dict) and (a.get("text") or a.get("title"))]
    if not alerts:
        return "The Overview page has no alerts right now.", "overview", "summary"
    lines = [f"**Needs attention** (Overview alerts): {len(alerts)}"]
    lines += [f"• {a.get('text') or a.get('title')}" for a in alerts[:8]]
    lines.append("For tasks, ask \"oldest open task\"; for promises, ask \"overdue items\".")
    return "\n".join(lines), "overview", "summary"


def _where(text: str) -> tuple[str, str, str] | None:
    if not WHERE.search(text) or re.search(r"\b(stock|unsold)\b", text, re.I):    # stock.py answers its own
        return None
    low = re.sub(r"[?.!,]", " ", text.lower())
    for words, label, group, key in PAGES_WHERE:
        m = re.search(rf"\b(?:{words})\b", low)
        if not m:
            continue
        rest = (low[:m.start()] + " " + low[m.end():]).split()
        if any(w not in _FILLER for w in rest):          # a figure is asked about, not the page itself
            return None
        return f"**{label}** is in the sidebar under {group} → {label}.", key, "where"
    return None


def _world(text: str) -> tuple[str, None, str] | None:
    m = WORLD.search(text)
    if not m:
        return None
    name = m.group(1).lower()
    if name == "world":
        return ("**FLO World** is the home of the FLO labels: the planet button in the top bar opens it. The Dashboard "
                "is live; the other 22 labels are marked coming soon, so there are no figures for them yet.", None, "page")
    return (f"**FLO {m.group(1).title()}** is one of the labels in FLO World (planet button in the top bar). It is not "
            "built yet (coming soon), so there are no figures for it.", None, "page")


def _fabric_rate(text: str, fetch, known: set[str]) -> tuple[str, str, str] | None:
    """A rate asked for a fabric the list has no category for: find it by name, or say it isn't there (rather than
    answering with some other "rate")."""
    name = next((m.group(1).strip().lower() for p in ASKS_RATE if (m := p.search(text))), None)
    if not name or category_in_text(name) or category_in_text(text.lower()):
        return None
    if any(w in known for w in name.split()):            # a figure, a person or a vendor: not a fabric
        return None
    body = fetch("vendor-rate", {})
    table = (body.get("tables") or {}).get("master") or {}
    cols = [c["label"] for c in table.get("columns") or []]
    if not {"Fabric", "Vendor"} <= set(cols):
        return None
    at = {c: i for i, c in enumerate(cols)}
    hits = [r for r in table.get("rows") or [] if name in str(r[at["Fabric"]]).lower()]
    if not hits:
        cats = ", ".join((body.get("options") or {}).get("fabric") or [])
        return (f"The rate list has no fabric called **{name}**. Fabric groups in the list: {cats}.", "vendor-rate",
                "rates")
    widths = [(c, c if c == "Per Pc" else f"{c}") for c in ('44"', '60"', '36"', "Per Pc") if c in at]
    lines = [f"Rates for fabrics named **{name}** (₹ per mtr unless marked per pc):"]
    for r in hits[:15]:
        parts = [f"{label} {fmt.inr(r[at[c]]) if isinstance(r[at[c]], (int, float)) else r[at[c]]}"
                 for c, label in widths if r[at[c]] not in (None, "")]
        lines.append(f"• **{r[at['Fabric']]}** ({r[at['Vendor']]}): {', '.join(parts) or 'no rate'}")
    return "\n".join(lines), "vendor-rate", "rates"


def _teams(text: str, fetch) -> tuple[str, str, str] | None:
    """"team wise status": FLO Future's team table, the only place the dashboard has teams."""
    if not TEAM_STATUS.search(text):
        return None
    table = (fetch("flo-future", {}).get("tables") or {}).get("teams") or {}
    columns, rows = table.get("columns") or [], table.get("rows") or []
    if not columns or not rows:
        return None
    cell = lambda v, c: "—" if v is None else fmt.value(v, c.get("format"), "") if isinstance(v, (int, float)) else str(v)
    lines = ["**FLO Future by team** (this month's promises)",
             "| " + " | ".join(c["label"] for c in columns) + " |", "|" + "---|" * len(columns)]
    lines += ["| " + " | ".join(cell(v, c) for v, c in zip(r, columns)) + " |" for r in rows]
    return "\n".join(lines), "flo-future", "summary"


def answer(text: str, fetch, known: set[str]) -> tuple[str, str | None, str] | None:
    """``known``: words that name a figure, person or vendor on the dashboard."""
    return (_world(text) or _where(text) or _urgent(text, fetch) or _teams(text, fetch)
            or _fabric_rate(text, fetch, known))
