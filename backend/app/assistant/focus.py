"""The three most used tabs - Daily Delegation, Designers and Production - for the question shapes the general matcher
gets wrong: a person or a task by name, who has done nothing, a designer's categories, filters like "less than 6000
pcs", overdue designs, status and month breakdowns.

``answer`` returns (text, page, context) or None, so everything else goes on as before. Every figure comes from that
page's own endpoint.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from . import fmt

PRONOUN = re.compile(r"\b(uska|uske|uski|usne|usko|iska|iske|iski|his|her|their)\b", re.I)
NOT_DELEGATION = re.compile(r"\b(designers?|production|fabric\w*|samples?|po|pos|stock|vendors?|clients?|revenue|orders?|"
                            r"promis\w*|flo future|pcs|designs?|sale)\b")
TASK = re.compile(r"\b(tasks?|kaam|delegation)\b")
_TITLE_STOP = set("""the a an of for to and with on in from by is are was ko ka ke ki se me mein hai hain hua kya kab kaun
kisko kisne kiska status task tasks work kaam wala wali wale about who responsible given diya open pending completed done
kitne kitna din days since how long list dikhao batao all show what which today aaj hua ho gaya check tell hotel""".split())


def _rows(body: dict, name: str) -> tuple[list[str], list[list]]:
    t = (body.get("tables") or {}).get(name) or {}
    cols = [c["label"] for c in t.get("columns") or []]
    return cols, [r for r in t.get("rows") or [] if str(r[0]).upper() != "TOTAL"]


def _n(v) -> str:
    return fmt.fmt_int(v or 0)


def _table(head: list[str], rows: list[list]) -> list[str]:
    return ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + \
        ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]


def _first(name: str) -> str:
    return name.lower().split()[0]


def _named(text: str, names: list[str]) -> list[str]:
    low = text.lower()
    hit = [(m.start(), n) for n in names
           if (m := re.search(rf"\b(?:{re.escape(n.lower())}|{re.escape(_first(n))})\b", low))]
    return [n for _, n in sorted(hit)]


# ------------------------------------------------------------------------------------------------ Daily Delegation
def _dd_ctx(extra: dict | None = None) -> dict:
    return {"page": "daily-delegation", "metric": "Tasks", "intent": "value", "entities": [], "months": [], "dim": None,
            "deleg": {"person": [], "status": [], "date": [], **(extra or {})}}


def _task_lookup(low: str, body: dict, known: set[str], need: int = 2) -> list[list]:
    """Tasks whose title the question quotes: two words of the title, or one that nothing else on the dashboard uses."""
    cols, rows = _rows(body, "tasks")
    i = cols.index("Task")
    said = {w for w in re.findall(r"[a-z0-9]+", low) if len(w) > 2 and w not in _TITLE_STOP}
    scored = []
    for r in rows:
        title = {w for w in re.findall(r"[a-z0-9]+", str(r[i]).lower()) if len(w) > 2}
        hit = said & title
        rare = {w for w in hit if w not in known and w not in _TITLE_STOP}
        if len(hit) >= need or (need == 2 and rare):
            scored.append((len(hit), r))
    if not scored:
        return []
    best = max(s for s, _ in scored)
    return [r for s, r in scored if s == best]


def delegation(text: str, ctx: dict, history: list, fetch, pa, known: set[str], other_names: set[str]):
    low = text.lower().strip()
    in_dd = ctx.get("page") == "daily-delegation"
    base = fetch("daily-delegation", {})
    if base.get("empty") or "kpis" not in base:
        return None
    people = (base.get("options") or {}).get("person") or []
    named = _named(low, people)
    only_here = [p for p in named if _first(p) not in other_names]      # "Deepika" is also a designer
    # a title may use another page's words ("sample", "fabric"): then three of its words must be quoted
    elsewhere = bool(NOT_DELEGATION.search(low))
    if elsewhere and not (re.search(r"\b(status|responsible|kisko|task|kitne din)\b", low) and
                          _task_lookup(low, base, known, need=3)):
        return None
    about_tasks = bool(TASK.search(low)) or in_dd or bool(only_here)
    pcols, prows = _rows(base, "persons")
    at = {c: i for i, c in enumerate(pcols)}
    dctx = (ctx.get("deleg") or {}) if in_dd else {}
    short = len(low.split()) <= 8

    def run(question: str, remember: dict | None = None, any_status: bool = False):
        earlier = {**ctx, "deleg": {**dctx, "status": []}} if any_status and in_dd else ctx
        out = pa.daily_delegation(question, [], [], ["daily-delegation"], earlier if in_dd else None)
        if not out:
            return None
        answer, c = out
        if remember:
            c = {**c, "deleg": {**(c.get("deleg") or {}), **remember}}
        return answer, "daily-delegation", c

    # "kisne ek bhi task complete nahi kiya" / "who has not completed anything"
    if about_tasks and re.search(r"\b(kisne|kiska|kis ne|who|which person)\b", low) and \
            re.search(r"\b(nahi|nahin|nhi|not|no|zero|nothing|ek bhi)\b", low) and \
            re.search(r"\b(complete\w*|done|finish\w*|kiya|khatam)\b", low):
        none = [r for r in prows if not r[at["Completed"]]]
        if not none:
            return "Everyone has completed at least one task.", "daily-delegation", _dd_ctx()
        lines = [f"**{len(none)} {'person has' if len(none) == 1 else 'people have'} completed no task yet**:"]
        lines += [f"• **{r[0]}**: {_n(r[at['Tasks']])} tasks, {_n(r[at['Open']])} open" for r in none]
        return "\n".join(lines), "daily-delegation", _dd_ctx()

    # how many / which people are involved
    if re.search(r"\b(kitne log|how many people|people involved|log involved|who all|kaun kaun)\b", low) and \
            (about_tasks or "involved" in low):
        lines = [f"**{len(prows)} people** have tasks in Daily Delegation:"]
        lines += [f"• **{r[0]}**: {_n(r[at['Tasks']])} tasks, {_n(r[at['Open']])} open" for r in prows]
        return "\n".join(lines), "daily-delegation", _dd_ctx()

    # by date
    if about_tasks and not named and re.search(r"\b(date[- ]?wise|day[- ]?wise|which (?:day|date)|kis (?:din|date))\b", low):
        dcols, drows = _rows(base, "dates")
        d = {c: i for i, c in enumerate(dcols)}
        lines = ["**Daily Delegation** · by task date"]
        if re.search(r"\b(which|kis)\b", low):
            top = (min if re.search(r"\b(least|fewest|lowest|kam)\b", low) else max)(drows, key=lambda r: r[d["Tasks"]])
            lines.append(f"**{top[d['Date']]}** has the {'fewest' if re.search(r'least|fewest|lowest|kam', low) else 'most'} "
                         f"tasks: **{_n(top[d['Tasks']])}**.")
        lines += _table(["Date", "Tasks", "Completed", "Open"],
                        [[r[d["Date"]], _n(r[d["Tasks"]]), _n(r[d["Completed"]]), _n(r[d["Open"]])] for r in drows])
        return "\n".join(lines), "daily-delegation", _dd_ctx()

    # yesterday ("kal ke tasks")
    if about_tasks and re.search(r"\b(yesterday|beete kal|kal (?:ke|ka|ki|wale))\b", low):
        today = str(base.get("today") or "")
        try:
            day = (datetime.strptime(today, "%d %b %Y") - timedelta(days=1)).strftime("%d %b %Y")
        except ValueError:
            return None
        options = (base.get("options") or {}).get("date") or []
        if day not in options:
            return (f"No tasks are dated yesterday ({day}). The sheet's dates are {', '.join(options)}.",
                    "daily-delegation", _dd_ctx())
        return run(f"tasks of {day[:6]}")

    # a person who is not in the sheet: "Rahul ke tasks"
    m = re.match(r"^\s*([a-z]{3,})(?: sir| mam| ji)? (?:ke|ka|ki) (?:pending |open |completed )?(?:tasks?|kaam)\b", low)
    if m and not named and m.group(1) not in known | _TITLE_STOP and m.group(1) not in other_names:
        return (f"I don't find **{m.group(1).title()}** in Daily Delegation. People in the sheet: {', '.join(people)}.",
                "daily-delegation", _dd_ctx())

    # one task, by words of its title
    asks_task = re.search(r"\b(status|hua|ho gaya|responsible|kisko|kisko diya|kaun|who|task|kitne din|how long|kab|"
                          r"booking)\b", low)
    searching = re.search(r"\btasks?\s+(?:about|regarding|related to|containing|with|dated)\b", low)   # a search
    if not named and asks_task and not searching and not re.search(r"\b(most|least|sabse|top|compare|summary|how many|kitne tasks)\b", low):
        found = _task_lookup(low, base, known, need=3 if elsewhere else 2)
        if found and len(found) <= 6:
            cols, _ = _rows(base, "tasks")
            c = {n: i for i, n in enumerate(cols)}
            lines = ["**Daily Delegation** · matching task" + ("s" if len(found) > 1 else "")]
            for r in found:
                age = r[c["Open for (days)"]]
                extra = f", open for {_n(age)} days" if age and r[c["Status"]] != "Completed" else ""
                note = f" Remarks: {r[c['Remarks']]}" if r[c["Remarks"]] else ""
                lines.append(f"• **{r[c['Task']]}**: {r[c['Responsible']]}, **{r[c['Status']]}**, dated {r[c['Date']]}"
                             f"{extra}.{note}")
            return "\n".join(lines), "daily-delegation", _dd_ctx({"person": list({r[c["Responsible"]] for r in found})
                                                                  if len(found) == 1 else []})

    status = "pending" if re.search(r"\bpending\b", low) else "completed" if re.search(
        r"\b(complete\w*|done|finished)\b", low) else "open" if re.search(r"\b(open|baki|baaki|remaining)\b", low) else ""

    if in_dd and short:
        # "dono compare karo": the last two people talked about
        if re.search(r"\b(dono|compare both|compare them)\b", low):
            seen: list[str] = []
            for past in reversed([h for h in history if isinstance(h, dict)] or [ctx]):
                for p in (past.get("deleg") or {}).get("person") or []:
                    if p not in seen:
                        seen.append(p)
            if len(seen) >= 2:
                return run(f"compare {seen[1]} and {seen[0]} tasks")
        # "uske pending?": the person the last ranking put first
        if PRONOUN.search(low) and not named:
            who = (dctx.get("person") or [None])[0] or dctx.get("top")
            if not who and len(dctx.get("tied") or []) > 1:
                return (f"There is a tie: {', '.join(dctx['tied'])}. Which one do you mean?", "daily-delegation",
                        _dd_ctx({"tied": dctx["tied"]}))
            if who:
                rate = bool(re.search(r"\b(completion|rate|percent\w*)\b|%", low))     # of all their tasks
                what = "completion %" if rate else f"{status} tasks"
                return run(f"{who} {what}".strip(), {"person": [who]}, any_status=rate)
        # "kiske hain?": who holds what is in hand
        if re.search(r"^\s*(?:ye |yeh )?(kiske|kiska|kiski|whose)(?: hain| hai| tasks?| are (?:they|these))?\s*\??$", low):
            held = " ".join(dctx.get("status") or [])
            key = "completed" if held == "Completed" else "pending" if held == "Pending" else "open"
            return run(f"who has most {key} tasks")

    # a person only this sheet has, asked without the word "task". With that word, or inside a task conversation, the
    # page's own reading (see extras.daily_delegation) already handles status, comparison and follow-ups
    if only_here and not in_dd and not TASK.search(low):
        return run(low)

    if in_dd and short and re.search(r"\b(\d{1,2} ?(?:nov|dec|jan|feb|mar|apr|may|jun|jul|aug|sep|oct)[a-z]*)\b", low):
        return run(f"tasks of {low}")
    if in_dd and short and re.search(r"^\s*(?:poori |puri )?(list|details?)(?: dikhao| batao| do)?\s*\??$", low):
        return run("list tasks")
    # "kiske approval me atke hain" / "waiting for approval"
    if re.search(r"\bapproval\b", low) and re.search(r"\b(kiske|kiska|atk\w*|ruk\w*|waiting|stuck|whose)\b", low):
        return run("awaiting approval tasks")
    if about_tasks and re.search(r"\b(best|top) performer\b|\bworst performer\b", low):
        return run("which person has the " + ("lowest" if "worst" in low else "highest") + " completion percentage tasks")
    return None


# ------------------------------------------------------------------------------------------------ Designers
DESIGNER_OTHER = re.compile(r"\b(production|pending|received|overdue|revenue|target|samples?|po|pos|fabric|tasks?|kaam|"
                            r"flo future|promis\w*|sale|on.?time|rate|approv\w*|reject\w*|clients?|vendors?)\b")


def _designer_ctx(name: str | None = None, measure: str | None = None) -> dict:
    return {"page": "designer", "metric": "Total Volume (Pcs)", "intent": "value", "months": [], "dim": "designer",
            "entities": [{"type": "designer", "value": name}] if name else [], "designer": name, "measure": measure}


# a designer's own figures, and the short follow-ups that name one of them ("new?", "aur Charu?")
MEASURES = {"new": ("New Orders (Pcs)", "new pcs"), "repeat": ("Repeat Orders (Pcs)", "repeat pcs"),
            "designs": ("Design Count", "designs"), "total": ("Total Volume (Pcs)", "pcs in total"),
            "share": ("Share %", "% share")}
_FOLLOW_WORDS = {"aur", "and", "ka", "ke", "ki", "what", "about", "uska", "uske", "uski", "kitna", "kitne", "kitni", "hai",
                 "new", "repeat", "design", "designs", "count", "total", "quantity", "qty", "pcs", "share", "orders"}


def _measure(low: str) -> str | None:
    for key, pat in (("new", r"\bnew\b"), ("repeat", r"\brepeat\b"), ("share", r"\bshare\b"),
                     ("designs", r"\b(design count|designs)\b"), ("total", r"\b(total|quantity|qty|volume|pcs)\b")):
        if re.search(pat, low):
            return key
    return None


def designers(text: str, ctx: dict, fetch, entities, months: list[str], known: set[str]):
    low = text.lower().strip()
    named = [e.display.upper() for e in entities if e.type == "designer"]
    cats = [e for e in entities if e.type == "category"]
    if not named and ctx.get("page") == "designer" and PRONOUN.search(low) and ctx.get("designer"):
        named = [str(ctx["designer"]).upper()]
    if re.search(r"\bnot[- ]assigned\b|\bunassigned\b", low):
        named = ["(NOT ASSIGNED)"]
    elif DESIGNER_OTHER.search(low):
        return None
    params = {"month": months} if months else {}
    body = fetch("designer", params)
    dcols, drows = _rows(body, "designers")
    ccols, crows = _rows(body, "categories")
    if not drows:
        return None
    d = {c: i for i, c in enumerate(dcols)}
    by_name = {str(r[0]).upper(): r for r in drows}
    cat_names = [c for c in ccols[1:] if c.upper() != "TOTAL"]
    when = f" in {' and '.join(months)}" if months else ""
    real = [r for r in drows if not str(r[0]).startswith("(")]

    def summary_line(r) -> str:
        return (f"**{r[0]}**{when}: **{_n(r[d['Design Count']])} designs**, **{_n(r[d['Total Volume (Pcs)']])} pcs** "
                f"(new {_n(r[d['New Orders (Pcs)']])}, repeat {_n(r[d['Repeat Orders (Pcs)']])}), "
                f"{r[d['Share %']]:.1f}% share.")

    def cats_of(name: str) -> list[tuple[str, float]]:
        row = next((r for r in crows if str(r[0]).upper() == name), None)
        if row is None:
            return []
        return sorted(((c, row[ccols.index(c)] or 0) for c in cat_names), key=lambda x: -x[1])

    def figure(name: str, measure: str):
        column, words = MEASURES[measure]
        value = by_name[name][d[column]]
        shown = f"{value:.1f}" if measure == "share" else _n(value)
        return (f"**{name}**{when}: **{shown}{'' if measure == 'share' else ' '}{words}** (Designers page).", "designer",
                _designer_ctx(name, measure))

    # short follow-ups in a designer conversation, and "Ayushi total quantity"
    rest = [w for w in re.findall(r"[a-z]+", low) if w not in _FOLLOW_WORDS
            and not any(w in n.lower().split() for n in named)]
    short_follow = ctx.get("page") == "designer" and not rest and not months and not cats
    if short_follow:
        who = named[0] if len(named) == 1 else str(ctx.get("designer") or "").upper() if not named else ""
        measure = _measure(low) or (ctx.get("measure") if named else None)
        if who in by_name and measure:
            return figure(who, measure)
    if len(named) == 1 and named[0] in by_name and not cats and \
            re.search(r"\btotal (?:quantity|qty|pcs|volume)\b", low):
        return figure(named[0], "total")

    if named == ["(NOT ASSIGNED)"]:
        r = by_name.get("(NOT ASSIGNED)")
        return (summary_line(r), "designer", _designer_ctx()) if r else None

    # "designers with less than 6000 pcs"
    m = re.search(r"(?:(less|fewer|under|below|more|over|above) (?:than )?([\d,]+))|(?:([\d,]+) (?:pcs |pieces )?se "
                  r"(kam|neeche|zyada|jyada|upar))", low)
    if m and re.search(r"\bdesigners?\b", low) and not named:
        limit = float((m.group(2) or m.group(3)).replace(",", ""))
        under = (m.group(1) or m.group(4)) in ("less", "fewer", "under", "below", "kam", "neeche")
        count = bool(re.search(r"\bdesigns\b|\borders\b", low))
        key = "Design Count" if count else "Total Volume (Pcs)"
        unit = "designs" if count else "pcs"
        hit = sorted((r for r in real if (r[d[key]] < limit if under else r[d[key]] > limit)), key=lambda r: r[d[key]],
                     reverse=not under)
        words = f"{'under' if under else 'over'} {_n(limit)} {unit}{when}"
        if not hit:
            return f"No designer is {words}.", "designer", _designer_ctx()
        lines = [f"**{len(hit)} designer{'s' if len(hit) != 1 else ''}** {words}:"]
        lines += [f"• **{r[0]}**: {_n(r[d[key]])} {unit}" for r in hit]
        return "\n".join(lines), "designer", _designer_ctx()

    if re.search(r"\b(average|avg|ausat)\b", low) and re.search(r"\bper designer\b|\bdesigner[- ]?wise average\b|"
                                                                  r"\bdesigner (?:ka |ke )?average\b", low):
        n = len(real)
        designs = sum(r[d["Design Count"]] or 0 for r in real)
        pcs = sum(r[d["Total Volume (Pcs)"]] or 0 for r in real)
        return (f"Average per designer{when}: **{designs / n:,.1f} designs** and **{_n(pcs / n)} pcs** ({_n(designs)} designs "
                f"and {_n(pcs)} pcs across {n} designers; not-assigned rows left out).", "designer", _designer_ctx())

    # a category, by designer: "which designer makes most kurta"
    if cats and not named and re.search(r"\b(designer\w*|kisne|kis ne|who|kaun)\b", low):
        cat = next((c for c in cat_names if c.upper() == cats[0].display.upper()), None)
        if cat:
            low_first = bool(re.search(r"\b(least|fewest|lowest|sabse kam)\b", low))
            ranked = sorted(((r[0], r[ccols.index(cat)] or 0) for r in crows if not str(r[0]).startswith("(")),
                            key=lambda x: x[1], reverse=not low_first)
            lines = [f"**{ranked[0][0]}** has the {'fewest' if low_first else 'most'} **{cat}** pcs{when}: "
                     f"**{_n(ranked[0][1])}**."]
            lines += [f"{i}. {name}: {_n(v)} pcs" for i, (name, v) in enumerate(ranked[:5], 1)]
            return "\n".join(lines), "designer", _designer_ctx(str(ranked[0][0]).upper())

    if len(named) == 1 and named[0] in by_name:
        name, r = named[0], by_name[named[0]]
        mine = cats_of(name)
        if cats and mine:                                  # "Ayushi ke dress kitne"
            cat = next((c for c in cat_names if c.upper() == cats[0].display.upper()), None)
            if cat:
                value = dict(mine)[cat]
                return (f"**{name}** · {cat}{when}: **{_n(value)} pcs** of {_n(r[d['Total Volume (Pcs)']])} total "
                        f"(Designers page).", "designer", _designer_ctx(name))
        if re.search(r"\bcategor\w+\b", low) and mine:
            if re.search(r"\b(best|top|most|highest|sabse (?:zyada|jyada))\b", low):
                return (f"**{name}**'s biggest category{when} is **{mine[0][0]}**: **{_n(mine[0][1])} pcs**.", "designer",
                        _designer_ctx(name))
            lines = [f"**{name}** by category{when} (Designers page, pcs):"]
            lines += [f"• {c}: {_n(v)}" for c, v in mine]
            return "\n".join(lines), "designer", _designer_ctx(name)
        if re.search(r"\b(design count|kitne designs?|how many designs?)\b", low) and PRONOUN.search(low):
            return (f"**{name}** has **{_n(r[d['Design Count']])} designs**{when}.", "designer", _designer_ctx(name))
        if re.search(r"\b(pura|poora|puri|full|complete|everything|all)\b.*\b(data|details?|report|info\w*)\b|"
                     r"\b(details?|profile|report|summary)\b", low) and not re.search(r"\borders?\b", low):
            lines = [summary_line(r)]
            if mine:
                lines.append("Top categories: " + ", ".join(f"{c} {_n(v)}" for c, v in mine[:3]) + " pcs.")
            prod = fetch("production", {**params, "designer": [name]})
            k = {x["label"]: x for x in prod.get("kpis") or []}
            if "Pending" in k:
                lines.append(f"Production: in production {_n(k['In production']['value'])}, received "
                             f"{_n(k['Received']['value'])}, pending **{_n(k['Pending']['value'])} pcs**.")
            return "\n".join(lines), "designer", _designer_ctx(name)

    # "Ayushi September vs October"
    if len(named) == 1 and len(months) == 2 and re.fullmatch(
            r"\s*(?:compare )?[a-z]+ (?:in )?[a-z]+(?:-\d\d)? (?:vs|versus|aur|and) [a-z]+(?:-\d\d)?\s*\??", low):
        rows = []
        for month in months:
            mc, mr = _rows(fetch("designer", {"month": [month]}), "designers")
            row = next((x for x in mr if str(x[0]).upper() == named[0]), None)
            rows.append([month, _n(row[mc.index("Design Count")]) if row else "0",
                         _n(row[mc.index("Total Volume (Pcs)")]) if row else "0"])
        lines = [f"**{named[0]}** · {months[0]} vs {months[1]} (Designers page)"]
        return "\n".join(lines + _table(["Month", "Designs", "Pcs"], rows)), "designer", _designer_ctx(named[0])

    # "Priya ke orders": a name the dashboard does not have
    m = re.match(r"^\s*([a-z]{3,}) (?:ke|ka|ki) (?:total |new |repeat )?(?:orders?|designs?)\b", low)
    if m and not named and not cats and m.group(1) not in known | _TITLE_STOP:
        return (f"I don't find a designer called **{m.group(1).title()}**. Designers: "
                f"{', '.join(str(r[0]) for r in real)}.", "designer", _designer_ctx())
    return None


# ------------------------------------------------------------------------------------------------ Production
PRODUCTION_OTHER = re.compile(r"\b(clients?|po|pos|fabric|samples?|tasks?|kaam|flo future|promis\w*|vendors?|rates? list|"
                              r"sale|stock|revenue|deliveries|expected)\b")
STAGES = {"cutting": "CUTTING", "finishing": "FINISHING", "confirmed": "CONFIRMED",
          "partial received": "PARTIAL RECEIVED", "partial": "PARTIAL RECEIVED"}


def _prod_ctx(metric: str = "Pending") -> dict:
    return {"page": "production", "metric": metric, "intent": "value", "entities": [], "months": [], "dim": None}


def production(text: str, fetch, entities, months: list[str]):
    low = text.lower().strip()
    if PRODUCTION_OTHER.search(low):
        return None
    params: dict = {"month": months} if months else {}
    for e in entities:
        if e.type in ("fabricator", "designer", "category") and "production" in e.raw:
            params.setdefault(e.type, []).append(e.raw["production"])
    scope = " · ".join([*(v for k, vs in params.items() if k != "month" for v in vs), *months])
    scope = f" ({scope})" if scope else ""

    def kpis(extra: dict | None = None) -> tuple[dict, dict]:
        body = fetch("production", {**params, **(extra or {})})
        return {x["label"]: x for x in body.get("kpis") or []}, body

    if re.search(r"\boverdue designs?\b|\bdesigns? (?:are |is )?overdue\b|\bkitne designs? (?:late|overdue)\b|"
                 r"\blate designs?\b", low):
        _, body = kpis()
        count = (body.get("summary") or {}).get("overdue_designs")
        if count is None:
            return None
        return f"**{_n(count)} designs** are overdue in production{scope}.", "production", _prod_ctx("Overdue pcs")
    if re.search(r"^(?:production )?(?:pending (?:percentage|percent|%|share)|(?:percentage|percent|%) (?:of )?pending|"
                 r"kitna (?:percent|%) pending)(?: (?:in )?production)?(?: hai)?\s*\??$", low):
        _, body = kpis()
        pct = (body.get("summary") or {}).get("pending_pct")
        if pct is None:
            return None
        return f"**{pct:.1f}%** of the pcs in production are still pending{scope}.", "production", _prod_ctx()
    if re.search(r"\bmonth[- ]?wise production\b|\bproduction month[- ]?wise\b|\bmonthly production\b", low):
        _, body = kpis()
        cols, rows = _rows(body, "monthly")
        at = {c: i for i, c in enumerate(cols)}
        names = ["Orders", "In Production", "Received", "Pending"]
        lines = [f"**Production month by month**{scope} (pcs)"]
        lines += _table(["Month", *names], [[r[0], *(_n(r[at[n]]) for n in names)] for r in rows if r[at["In Production"]]])
        return "\n".join(lines), "production", _prod_ctx()

    stage = next((v for k, v in STAGES.items() if re.search(rf"\b{k}\b", low)), None)
    wise = re.search(r"\bstatus[- ]?wise\b", low)
    if wise or (stage and re.search(r"\b(stage|status|me|mein|in|kitna|kitne|pcs|how)\b", low)):
        _, body = kpis()
        options = (body.get("options") or {}).get("status") or []
        wanted = options if wise else [s for s in options if s == stage]
        if not wanted:
            return None
        rows = []
        for status in wanted:
            k, _ = kpis({"status": [status]})
            rows.append([status, _n(k.get("Designs in production", {}).get("value")),
                         _n(k.get("In production", {}).get("value")), _n(k.get("Pending", {}).get("value"))])
        lines = [f"**Production by status**{scope}"]
        return "\n".join(lines + _table(["Status", "Designs", "In production (pcs)", "Pending (pcs)"], rows)), \
            "production", _prod_ctx()

    if re.search(r"\bfabricators?\b", low) and re.search(r"\bon.?time\b", low) and \
            re.search(r"\b(ranking|rank|wise|list|all)\b", low):
        _, body = kpis()
        found = []
        for name in (body.get("options") or {}).get("fabricator") or []:
            if name.startswith("("):
                continue
            k, _ = kpis({"fabricator": [name]})
            value = k.get("On-time delivery", {}).get("value")
            if value is not None:
                found.append((name, value))
        if not found:
            return None
        found.sort(key=lambda x: -x[1])
        lines = [f"**Fabricators by on-time delivery**{scope} (Production page)"]
        lines += [f"{i}. {name}: {v:.1f}%" for i, (name, v) in enumerate(found, 1)]
        return "\n".join(lines), "production", _prod_ctx("On-time delivery")
    return None
