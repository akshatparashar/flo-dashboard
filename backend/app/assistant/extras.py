"""Page-level answers that need more than one KPI: the dashboard summary, samples waiting for approval, pending
purchase orders, the vendor rate list and the revenue target.

Each answer reads the page's own API (same filters as the page) and only arranges what the page already shows. Labels
are matched by the start of the KPI / column label, so a renamed figure fails safe (the answer is skipped and the
general matcher takes over) instead of inventing a number.
"""
from __future__ import annotations

import re
from typing import Callable

from . import fmt, planner
from .text import norm

SPECIAL = re.compile(r"^\(.*\)$|^(total|grand total)$", re.I)


def _kpis(body: dict) -> list[dict]:
    return [k for k in body.get("kpis") or [] if isinstance(k, dict)]


def _kpi(body: dict, start: str):
    return next((k for k in _kpis(body) if str(k.get("label", "")).lower().startswith(start.lower())), None)


def _show(k: dict | None) -> str:
    if not k:
        return "—"
    unit = k.get("unit") or ""
    return fmt.value(k.get("value"), k.get("format"), unit if unit not in ("₹",) else "")


def _table(body: dict, name: str) -> tuple[list[str], list[list]]:
    t = (body.get("tables") or {}).get(name) or {}
    return [c["label"] if isinstance(c, dict) else str(c) for c in t.get("columns") or []], list(t.get("rows") or [])


def _col(cols: list[str], start: str) -> int | None:
    return next((i for i, c in enumerate(cols) if c.lower().startswith(start.lower())), None)


def _filters(page: str, entities, months: list[str], allowed: dict) -> dict | None:
    """Page filters for the named things; None when a named thing isn't on that page."""
    f: dict = {}
    for e in entities:
        if e.type == "month":
            continue
        key = next((k for k, v in allowed.items() if v == e.type), None)
        raw = e.raw.get(page)
        if key is None or raw is None:
            return None
        f.setdefault(key, []).append(raw)
    if months and "month" in allowed:
        f["month"] = list(months)
    return f


class PageAnswers:
    def __init__(self, fetch: Callable[[str, dict], dict], page_filters: dict[str, dict], labels: dict[str, str]):
        self.fetch = fetch
        self.page_filters = page_filters
        self.labels = labels

    # ------------------------------------------------------------------------------------------------ summary
    SUMMARY = re.compile(r"\b(summary|summarise|summarize|overview|saar|saransh|snapshot|highlights|report|"
                         r"performance)\b")
    SUMMARY_SCOPE = re.compile(r"\b(dashboard|complete|overall|whole|full|entire|everything|sab|sabka|company|flo|"
                               r"this month|is mahine|month|performance|business|aaj tak)\b")

    def summary(self, text: str, months: list[str]) -> tuple[str, dict] | None:
        t = norm(text)
        if not (self.SUMMARY.search(t) and self.SUMMARY_SCOPE.search(t)):
            return None
        body = self.fetch("overview", {"month": months} if months else {})
        sections = body.get("sections") or {}
        names = {"orders": "Orders & production", "stock": "Fabricator stock", "po": "Fabric POs",
                 "samples": "Samples", "flo_future": "FLO Future (this month's promises)"}
        when = " and ".join(months) if months else "all months so far"
        lines = [f"**Dashboard summary** · Period: {when}"]
        for key, sec in sections.items():
            ks = _kpis(sec) if isinstance(sec, dict) else []
            if not ks:
                continue
            lines.append(f"\n**{names.get(key, key.replace('_', ' ').title())}**")
            lines += [f"• {k.get('label')}: **{_show(k)}**" for k in ks]
        if len(lines) == 1:
            return None
        alerts = [a for a in body.get("alerts") or [] if isinstance(a, dict)]
        if alerts:
            lines.append("\n**Needs attention**")
            lines += [f"• {a.get('title') or a.get('text') or a.get('message')}" for a in alerts[:6]
                      if a.get('title') or a.get('text') or a.get('message')]
        if months:
            lines.append("FLO Future always shows the current month's promises, whatever month is picked.")
        ctx = {"page": "overview", "metric": None, "intent": "summary", "entities": [], "months": months, "dim": None}
        return "\n".join(lines), ctx

    # ------------------------------------------------------------------------------------------------ samples
    SAMPLES = re.compile(r"\bsamples?\b")
    OPEN = re.compile(r"\b(pending|waiting|wait|baki|baaki|open|pipeline|not approved|awaiting|in process|"
                      r"on hold|hold|abhi tak)\b")
    NOT_SAMPLES_PAGE = re.compile(r"\b(promis\w*|flo future|future|target|vaada|commit\w*)\b")

    def samples_open(self, text: str, entities, months: list[str]) -> tuple[str, dict] | None:
        t = norm(text)
        if not (self.SAMPLES.search(t) and self.OPEN.search(t)) or self.NOT_SAMPLES_PAGE.search(t):
            return None
        if re.search(r"\b(approval|approved|rejection|rejected)\s*(%|rate|percent\w*)", t):
            return None
        f = _filters("samples", entities, months, self.page_filters["samples"])
        if f is None:
            return None
        body = self.fetch("samples", f)
        pipe, hold, proc = _kpi(body, "Open pipeline"), _kpi(body, "On hold"), _kpi(body, "In process")
        if not (pipe and hold and proc):
            return None
        who = " and ".join(e.display for e in entities if e.type != "month") or "All designers"
        when = " and ".join(months) if months else "all months so far"
        lines = [f"**Samples waiting for a decision** ({who} · {when})",
                 f"• Open pipeline: **{_show(pipe)}** = On hold {_show(hold)} + In process {_show(proc)}",
                 f"• Approved so far: {_show(_kpi(body, 'Approved'))}, rejected: {_show(_kpi(body, 'Rejected'))}"]
        cols, rows = _table(body, "designers")
        ih, ip = _col(cols, "On Hold"), _col(cols, "In Process")
        if ih is not None and ip is not None and not any(e.type == "designer" for e in entities):
            open_rows = [(r[0], (r[ih] or 0) + (r[ip] or 0), r[ih] or 0, r[ip] or 0) for r in rows
                         if not SPECIAL.match(str(r[0])) and ((r[ih] or 0) + (r[ip] or 0)) > 0]
            open_rows.sort(key=lambda x: -x[1])
            if open_rows:
                lines.append("By designer (on hold + in process):")
                lines += [f"• {n}: {fmt.fmt_int(o)} pcs (on hold {fmt.fmt_int(h)}, in process {fmt.fmt_int(p)})"
                          for n, o, h, p in open_rows[:10]]
        lines.append("The Samples page counts samples by status; it has no list of individual samples. "
                     "FLO Future's promised samples are a separate figure (ask \"FLO Future pending\").")
        ctx = {"page": "samples", "metric": "Open pipeline", "intent": "value",
               "entities": [{"type": e.type, "value": e.display} for e in entities if e.type != "month"],
               "months": months, "dim": None}
        return "\n".join(lines), ctx

    # ------------------------------------------------------------------------------------------------ fabric POs
    PO = re.compile(r"\b(pos?|purchase orders?|fabric po)\b")
    PO_OPEN = re.compile(r"\b(pending|open|baki|baaki|not received|outstanding|abhi tak)\b")
    PO_ASK = re.compile(r"\b(how many|kitne|kitni|count|number|which|list|show|batao|dikhao|kaun|kon)\b")

    def po_pending(self, text: str, entities, months: list[str]) -> tuple[str, dict] | None:
        t = norm(text)
        pcs_asked = re.search(r"\b(pcs|pc|pieces?)\b", t)
        if not (self.PO.search(t) and self.PO_OPEN.search(t) and (self.PO_ASK.search(t) or pcs_asked)):
            return None
        if re.search(r"\b(mtr|meters?|fabric pending|pending fabric|quantity|qty|kitna)\b", t) and \
                not re.search(r"\b(which|list|how many|kitne|count)\b", t) and not pcs_asked:
            return None
        f = _filters("fabric-po", entities, months, self.page_filters["fabric-po"])
        if f is None:
            return None
        body = self.fetch("fabric-po", f)
        cols, rows = _table(body, "pos")
        ipend, ipo, iv, idue = _col(cols, "Pending"), _col(cols, "PO No"), _col(cols, "Vendor"), _col(cols, "Due Date")
        iitem = _col(cols, "Item")
        if ipend is None or ipo is None:
            return None
        open_rows = [r for r in rows if isinstance(r[ipend], (int, float)) and r[ipend] > 0]
        total_pos = _kpi(body, "Total POs")
        pend_mtr = sum(r[ipend] for r in open_rows)
        who = " and ".join(e.display for e in entities if e.type != "month") or "all vendors"
        when = " and ".join(months) if months else "all months so far"
        lines = []
        if re.search(r"\b(pcs|pc|pieces?|qty in pcs)\b", t):
            tp = _kpi(body, "Total pcs")
            lines.append(f"Fabric PO does not record **pending pcs** - pending is tracked in **metres** of fabric (shown "
                         f"below). The only pcs figure on the page is the pcs ordered on the POs: {_show(tp)}.")
        lines += [f"**{len(open_rows):,} POs are still pending** (fabric not fully received) out of "
                 f"{_show(total_pos)} · {who} · {when}.",
                 f"Pending fabric on these POs: **{fmt.value(pend_mtr, 'dec', 'mtr')}** (the page's Pending fabric "
                 f"KPI: {_show(_kpi(body, 'Pending fabric'))}).",
                 f"Overdue and not received: {_show(_kpi(body, 'Overdue, not received'))}."]
        open_rows.sort(key=lambda r: -r[ipend])
        if open_rows:
            lines.append(f"Largest pending POs{' (top 15)' if len(open_rows) > 15 else ''}:")
            for r in open_rows[:15]:
                bits = [str(r[iv])] if iv is not None else []
                if iitem is not None and r[iitem]:
                    bits.append(str(r[iitem]))
                if idue is not None and r[idue]:
                    bits.append(f"due {r[idue]}")
                lines.append(f"• **{r[ipo]}** — {fmt.value(r[ipend], 'dec', 'mtr')} pending ({', '.join(bits)})")
        if abs(pend_mtr - ((_kpi(body, "Pending fabric") or {}).get("value") or pend_mtr)) > 1:
            lines.append("The PO list and the KPI are summed differently on the page (the KPI may count short "
                         "deliveries differently), so both are shown.")
        ctx = {"page": "fabric-po", "metric": "Pending (mtr)", "intent": "value",
               "entities": [{"type": e.type, "value": e.display} for e in entities if e.type != "month"],
               "months": months, "dim": None}
        return "\n".join(lines), ctx

    # ------------------------------------------------------------------------------------------------ vendor rates
    def rate_list(self, text: str, entities) -> tuple[str, dict] | None:
        t = norm(text)
        if not re.search(r"\b(vendor rates?|rate list|rate card|all rates|price list|vendors? ke rates?)|^(show |list |give )?(me )?(all )?(the )?rates? of (all )?(the )?vendors\b", t):
            return None
        if entities or re.search(r"\b(cheapest|lowest|highest|best|compare|average|avg|time|delay\w*|\d{2})\b", t):
            return None
        body = self.fetch("vendor-rate", {})
        cols, rows = _table(body, "benchmark")
        if not rows:
            return None
        keep = [i for i, c in enumerate(cols) if i == 0 or c.lower().startswith(("total items", "avg", "min", "max",
                                                                               "per pc", "pending"))]
        lines = ["**Vendor rate list** (₹ per mtr; 0 and blank rates left out of averages)",
                 "| " + " | ".join(cols[i] for i in keep) + " |", "|" + "---|" * len(keep)]
        for r in rows:
            if SPECIAL.match(str(r[0])):
                continue
            cells = []
            for i in keep:
                v = r[i]
                cells.append(str(v) if i == 0 or not isinstance(v, (int, float)) else
                             (fmt.inr(v) if re.search(r"rate", cols[i], re.I) else fmt.fmt_int(v)))
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("Ask for one vendor (\"RV rates\") or one fabric (\"crepe rates\") to see every item.")
        return "\n".join(lines), {"page": "vendor-rate", "metric": None, "intent": "list", "entities": [],
                                  "months": [], "dim": "vendor"}

    # ------------------------------------------------------------------------------------------------ revenue target
    def target_achieved(self, text: str, months: list[str]) -> tuple[str, dict] | None:
        t = norm(text)
        monthly = re.search(r"\b(monthly|month wise|month-wise|every month|har mahine|each month|by month)\b", t) and \
            re.search(r"\btargets?\b", t) and re.search(r"\b(revenue|achiev\w*|actual|vs|versus|compare|against)\b", t)
        achieved = re.search(r"\b(achiev\w*|hasil|achieve)\b", t)
        money = re.search(r"\b(revenue|target|sales)\b", t) or (months and not re.search(
            r"\b(pos?|fabric|samples?|production|promis\w*|future|stock|fabricators?|orders?|designs?|pcs|qty)\b", t))
        if not monthly and not (achieved and money):
            return None
        if re.search(r"\b(remaining|bacha|baki|left)\b", t):
            return None
        body = self.fetch("target", {})
        if re.search(r"\b(designers?|who|which|kis|kaun|kiska|kiske|sabse)\b", t) and \
                re.search(r"\b(achiev\w*|target)\b", t):
            return self._designer_target(body, t)
        if re.search(r"\b(monthly|month wise|month-wise|every month|har mahine|each month|by month)\b", t) or \
                (re.search(r"\b(compare|vs|versus)\b", t) and re.search(r"\btargets?\b", t)):
            return self._target_table(body.get("tracker") or {}, months)
        tracker = body.get("tracker") or {}
        tgt, ach = _kpi(tracker, "Yearly target"), _kpi(tracker, "Achieved (new)")
        pct, rep, tot = _kpi(tracker, "Achieved"), _kpi(tracker, "Repeat revenue"), _kpi(tracker, "Total revenue")
        pct = next((k for k in _kpis(tracker) if k.get("label") == "Achieved"), pct)
        if not (tgt and ach):
            return None
        want_pct = bool(re.search(r"(%|\bpercent\w*|\bpct\b|\bprati?shat\b)", t))
        a, g = ach.get("value"), tgt.get("value")
        p = a / g * 100 if g else None
        lines = []
        if months:
            cols, rows = _table(tracker, "table") if isinstance(tracker.get("table"), dict) else ([], [])
            if not cols:
                tab = tracker.get("table") or {}
                cols = [c["label"] if isinstance(c, dict) else c for c in tab.get("columns") or []]
                rows = tab.get("rows") or []
            it, ia, ip = _col(cols, "Target"), _col(cols, "Achieved (New)"), _col(cols, "Achieved %")
            for m in months:
                r = next((x for x in rows if str(x[0]) == m), None)
                if r and None not in (it, ia):
                    pm = r[ia] / r[it] * 100 if r[it] else None
                    lines.append(f"**{m}**: achieved (new) **{fmt.inr_short(r[ia])}** against a target of "
                                 f"{fmt.inr_short(r[it])}" + (f" = **{pm:.2f}%**" if pm is not None else "") + ".")
            if lines:
                lines.append("Formula: Achieved (new) ÷ Target × 100.")
                return "\n".join(lines), {"page": "target", "metric": "Achieved (New)", "intent": "value",
                                          "entities": [], "months": months, "dim": None}
        lead = (f"Target achievement is **{p:.2f}%**: achieved (new orders) **{fmt.inr_short(a)}** of the yearly target "
                f"**{fmt.inr_short(g)}**." if want_pct and p is not None else
                f"Revenue achieved against the target (new orders): **{fmt.inr_short(a)}** of **{fmt.inr_short(g)}**"
                + (f" ({p:.2f}%)." if p is not None else "."))
        lines = [lead]
        if p is not None:
            lines.append(f"Formula: {fmt.inr_short(a)} ÷ {fmt.inr_short(g)} × 100 = {p:.2f}%.")
        if rep and tot:
            lines.append(f"Repeat revenue is not counted toward the target: {_show(rep)}; total revenue (new + repeat) "
                         f"is {_show(tot)}.")
        return "\n".join(lines), {"page": "target", "metric": "Achieved (new)", "intent": "value", "entities": [],
                                  "months": [], "dim": None}

    # ------------------------------------------------------------------------------------------------ fabricators
    WORK = re.compile(r"\b(pending|remaining|baki|baaki|bacha|work|kaam|stock|under production|received|rcvd|status|"
                      r"show|details?|compare)\b")

    def fabricator_work(self, text: str, entities, months: list[str], production_names: list[str]):
        """A fabricator's pending work: the Fabricators page (stock: pcs under production, received, remaining) and,
        when the same fabricator is on the Production page, its pending pcs there. Several fabricators -> a table."""
        t = norm(text)
        fabs = [e for e in entities if e.type == "fabricator"]
        if not fabs or len(fabs) != len([e for e in entities if e.type != "month"]) or not self.WORK.search(t):
            return None
        if re.search(r"\b(overdue|delay\w*|late|on time|on-time|issued|mtr)\b", t):
            return None
        rows_out = []
        for e in fabs:
            row = {"name": e.display}
            raw = e.raw.get("fabricator")
            if raw is not None:
                f = {"fabricator": [raw], **({"month": months} if months else {})}
                body = self.fetch("fabricator", f)
                for key, start in (("under", "Pcs under production"), ("rcvd", "Received"), ("remaining", "Remaining"),
                                   ("rate", "Received rate")):
                    k = _kpi(body, start)
                    row[key] = k.get("value") if k else None
            praw = e.raw.get("production")
            if praw is None:
                cands = [n for n in production_names if n.upper().startswith(e.display.upper() + " ")]
                praw = cands[0] if len(cands) == 1 else None
                row["alias"] = praw
            if praw is not None:
                body = self.fetch("production", {"fabricator": [praw], **({"month": months} if months else {})})
                k, d = _kpi(body, "Pending"), _kpi(body, "In production")
                row["p_pending"], row["p_total"] = (k or {}).get("value"), (d or {}).get("value")
            rows_out.append(row)
        if all(r.get("remaining") is None and r.get("p_pending") is None for r in rows_out):
            return None
        when = " and ".join(months) if months else "all months so far"
        num = lambda v: "—" if v is None else fmt.fmt_int(v)
        if len(rows_out) == 1:
            r = rows_out[0]
            lines = [f"**{r['name']}** · {when}"]
            if r.get("remaining") is not None:
                lines += ["Fabricators page (stock):",
                          f"• Pcs under production: **{num(r.get('under'))} pcs**",
                          f"• Received: **{num(r.get('rcvd'))} pcs**",
                          f"• Remaining (pending work): **{num(r.get('remaining'))} pcs**"]
                if r.get("rate") is not None:
                    lines.append(f"• Received rate: {r['rate']:.1f}%")
            if r.get("p_pending") is not None:
                alias = f" (listed there as {r['alias']})" if r.get("alias") else ""
                lines += [f"Production page{alias}:", f"• In production: {num(r.get('p_total'))} pcs",
                          f"• Pending: **{num(r.get('p_pending'))} pcs**"]
            if r.get("remaining") is not None and r.get("p_pending") is not None:
                lines.append("The two pages count differently (stock sheet vs order tracker), so they are shown apart.")
        else:
            lines = [f"**Fabricator pending work** · {when}", "| Metric | " + " | ".join(r["name"] for r in rows_out) + " |",
                     "|---|" + "---|" * len(rows_out),
                     "| Remaining pcs (Fabricators page) | " + " | ".join(num(r.get("remaining")) for r in rows_out) + " |",
                     "| Pcs under production (Fabricators page) | " + " | ".join(num(r.get("under")) for r in rows_out) + " |",
                     "| Pending pcs (Production page) | " + " | ".join(num(r.get("p_pending")) for r in rows_out) + " |"]
            vals = [(r["name"], r.get("remaining")) for r in rows_out if r.get("remaining") is not None]
            if len(vals) >= 2:
                hi, lo = max(vals, key=lambda x: x[1]), min(vals, key=lambda x: x[1])
                if hi[1] != lo[1]:
                    lines.append(f"**{hi[0]}** has **{fmt.fmt_int(hi[1] - lo[1])} more** remaining pcs than {lo[0]} "
                                 f"({fmt.fmt_int(hi[1])} − {fmt.fmt_int(lo[1])}).")
        ctx = {"page": "fabricator", "metric": "Remaining (Pcs)", "intent": "value",
               "entities": [{"type": "fabricator", "value": e.display} for e in fabs], "months": months, "dim": None}
        return "\n".join(lines), ctx

    @staticmethod
    def _tracker_table(tracker: dict):
        tab = tracker.get("table") or {}
        return [c["label"] if isinstance(c, dict) else str(c) for c in tab.get("columns") or []], list(tab.get("rows") or [])

    def _target_table(self, tracker: dict, months: list[str]):
        cols, rows = self._tracker_table(tracker)
        it, ia, ir, inr_ = _col(cols, "Target"), _col(cols, "Achieved (New)"), _col(cols, "Repeat Revenue"), \
            _col(cols, "New + Repeat")
        if it is None or ia is None:
            return None
        rows = [r for r in rows if not SPECIAL.match(str(r[0])) and (not months or r[0] in months)]
        lines = ["**Monthly target vs revenue** (target is for NEW orders; Achieved % = Achieved (new) ÷ Target × 100)",
                 "| Month | Target | Achieved (new) | Achieved % | Repeat revenue | New + repeat |", "|---|---|---|---|---|---|"]
        for r in rows:
            pct = f"{r[ia] / r[it] * 100:.2f}%" if r[it] else "—"
            cell = lambda i: fmt.inr_short(r[i]) if i is not None and isinstance(r[i], (int, float)) else "—"
            lines.append(f"| {r[0]} | {cell(it)} | {cell(ia)} | {pct} | {cell(ir)} | {cell(inr_)} |")
        done = [r for r in rows if isinstance(r[ia], (int, float)) and r[ia]]
        if done:
            best = max(done, key=lambda r: r[ia] / r[it] if r[it] else 0)
            lines.append(f"Best month against target: **{best[0]}** ({best[ia] / best[it] * 100:.2f}%)." if best[it] else "")
        return "\n".join(x for x in lines if x), {"page": "target", "metric": "Achieved (New)", "intent": "trend",
                                                  "entities": [], "months": months, "dim": "month"}

    # ------------------------------------------------------------------------------------------------ In/Out Sale
    IOS = re.compile(r"\b(in[\s/-]*out[\s/-]*sale|net sale|net per pc|sale (?:pcs|pieces|amount|qty|quantity|value)|"
                     r"sold (?:pcs|pieces)|incoming (?:pcs|pieces)|pcs incoming|in[\s-]?house|inhouse|deducted|"
                     r"sent to production|pieces under production|sale vs incoming)\b")
    IOS_METRICS = [("Net sale per pc", r"net sale per pc|net per pc|per pc net"), ("Net sale", r"net sale"),
                   ("Sale amount", r"sale (?:amount|value)"), ("Sale pcs", r"sale (?:pcs|pieces|qty|quantity)|sold"),
                   ("Incoming pcs", r"incoming"), ("Order pcs", r"order pcs|order pieces|orders? pcs"),
                   ("Sent to production", r"sent to production|under production|production pcs")]
    TYPE_W = re.compile(r"\b(in[\s-]?house|inhouse|outsource\w*|out source)\b")

    IOS_NOT_FOLLOW = re.compile(r"\b(po|pos|fabric|vendor|samples?|designer|client|production|revenue|target|promis\w*)\b")

    def _ios(self, months, fabs=(), typ=None):
        f: dict = {}
        if months:
            f["month"] = list(months)
        raws = [e.raw.get("in-out-sale") for e in fabs]
        if raws and all(raws):
            f["fabricator"] = raws
        if typ:
            f["type"] = [typ]
        return self.fetch("in-out-sale", f)

    def _type_totals(self, months, fabs=()):
        """Incoming pcs for In-house and Outsource, read with the page's own Type filter (a fabricator can have pcs of
        both kinds, so adding up the Type column of the unfiltered table is not the same)."""
        out = {}
        for typ in ("In-house", "Outsource"):
            cols, rows = _table(self._ios(months, fabs, typ), "fabricators")
            i = _col(cols, "Total")
            out[typ] = (sum(r[i] or 0 for r in rows if not SPECIAL.match(str(r[0]))) if i is not None else None,
                        [r[0] for r in rows if not SPECIAL.match(str(r[0]))])
        return out

    @staticmethod
    def _incoming_gap(body: dict, fab_total: float) -> str:
        """The page shows incoming pcs twice: the month table (the Incoming pcs KPI) and the fabricator-wise table.
        When the sheet's two tables disagree, say so with the page's own check instead of picking one silently."""
        kp = _kpi(body, "Incoming pcs")
        if not kp or not isinstance(kp.get("value"), (int, float)) or abs(kp["value"] - fab_total) < 0.5:
            return ""
        why = " ".join(c["text"] for c in body.get("checks") or [] if isinstance(c, dict) and "Incoming" in c.get("text", ""))
        return (f"Note: total incoming is **{fmt.fmt_int(kp['value'])} pcs** in the month table (the page's Incoming pcs "
                f"figure) but **{fmt.fmt_int(fab_total)} pcs** when the fabricator-wise table is added up - "
                f"{fmt.fmt_int(abs(fab_total - kp['value']))} pcs apart in the sheet itself. " + (f"The page flags it: {why} " if why else "") +
                "Fabricator shares use the fabricator-wise total so they add up to 100%.")

    @staticmethod
    def _inr(v):
        return fmt.inr_short(v) if isinstance(v, (int, float)) else "—"

    WHOLE_YEAR = planner.WHOLE_YEAR
    FOLLOW_IOS = re.compile(r"\b(last year|previous year|compare|comparison|highest|lowest|best|worst|which month|"
                            r"month wise|month by month|monthly|deducted|per pc|vs|growth|change|increase|decrease|"
                            r"difference|percent\w*|%)\b")

    def in_out_sale(self, text: str, entities, months: list[str], explicit: list[str], ctx_in: dict | None = None):
        raw = re.sub(r"[/]", " ", text.lower())
        t = norm(text)
        follow = isinstance(ctx_in, dict) and ctx_in.get("page") == "in-out-sale" and len(raw.split()) <= 9 and \
            bool(self.FOLLOW_IOS.search(raw)) and not self.IOS_NOT_FOLLOW.search(raw)
        whole_year = bool(self.WHOLE_YEAR.search(raw))
        names_metric = any(re.search(rx, raw) for _, rx in self.IOS_METRICS)
        if whole_year:
            months = []                         # "this year", "FY 2026-27", "year to date": every month, whatever was asked before
        elif follow and not months and not names_metric and not re.search(
                r"\b(highest|lowest|best|worst|which month|month wise|monthly|month by month)\b", raw):
            months = [m for m in ctx_in.get("months") or []]      # a bare follow-up ("compare with last year") keeps the period
        named = "in-out-sale" in explicit or bool(self.IOS.search(raw)) or follow
        promised = re.search(r"\bpromis\w*\b", raw) and re.search(r"\b(came|come|incoming|aaya|aaye|fabricators?|pcs|"
                                                                    r"pieces|achieved|pending)\b", raw) and \
            not re.search(r"\b(samples?|items?|designers?|teams?|overdue|visits?|meetings?|flo future|outsource)\b", raw)
        fab_ents = [e for e in entities if e.type == "fabricator" and e.raw.get("in-out-sale")]
        fab_follow = isinstance(ctx_in, dict) and ctx_in.get("page") == "in-out-sale" and \
            ctx_in.get("dim") == "fabricator" and bool(fab_ents) and len(raw.split()) <= 7
        if fab_follow and not months:
            months = list(ctx_in.get("months") or [])
        incoming_fab = fab_follow or (re.search(r"\bincoming\b", raw) and not re.search(r"\bmonthly incoming\b", raw) and (
            fab_ents or re.search(r"\b(fabricators?|by fabricator|fabricator wise|karigar)\b", raw)))
        if not (named or promised or incoming_fab):
            return None
        if any(e.type not in ("month", "fabricator") for e in entities):
            return None
        kinds = {("In-house" if re.search(r"house", m) else "Outsource") for m in
                 (x.group(1) for x in self.TYPE_W.finditer(raw))}
        typ = next(iter(kinds)) if len(kinds) == 1 else None
        if len(kinds) == 2 or (typ and re.search(r"\b(vs|versus|compare|comparison)\b", raw)):
            kinds = {"In-house", "Outsource"}
            typ = None
        when = " and ".join(months) if months else "all months so far"
        ctx = {"page": "in-out-sale", "metric": None, "intent": "value", "entities":
               [{"type": "fabricator", "value": e.display} for e in fab_ents], "months": months, "dim": None}
        sheet = "IN/OUT/SALE sheet, 2026-27 tab"

        # ---- promised vs incoming per fabricator and month
        if promised:
            body = self._ios(months, fab_ents)
            cols, rows = _table(body, "promises")
            if not rows:
                return None
            lines = [f"**Promised vs incoming pcs by fabricator** · {when} · {sheet}",
                     "| Month | Fabricator | Promised | Incoming | Pending | Achieved % |", "|---|---|---|---|---|---|"]
            tp = ti = 0
            for r in rows:
                if SPECIAL.match(str(r[0])):
                    continue
                tp, ti = tp + (r[2] or 0), ti + (r[3] or 0)
                lines.append(f"| {r[0]} | {r[1]} | {fmt.fmt_int(r[2])} | {fmt.fmt_int(r[3])} | {fmt.fmt_int(r[4])} | "
                             f"{r[5]:.1f}% |" if isinstance(r[5], (int, float)) else f"| {r[0]} | {r[1]} | {fmt.fmt_int(r[2])} | {fmt.fmt_int(r[3])} | {fmt.fmt_int(r[4])} | — |")
            lines.append(f"Total: promised **{fmt.fmt_int(tp)}** pcs, incoming **{fmt.fmt_int(ti)}** pcs, "
                         f"pending **{fmt.fmt_int(max(tp - ti, 0))}** pcs" +
                         (f" — achieved **{ti / tp * 100:.1f}%** ({fmt.fmt_int(ti)} ÷ {fmt.fmt_int(tp)} × 100)." if tp else "."))
            lines.append("The sheet tracks promised pcs for some fabricators and months only.")
            return "\n".join(lines), {**ctx, "metric": "Promised"}

        # ---- In-house / Outsource exists only for incoming pcs: never answer a sale question with incoming figures
        sale_words = re.search(r"\b(sale|sales|sold|net sale|sale amount|bikri|becha)\b", raw)
        if kinds and sale_words and not re.search(r"\bincoming\b", raw):
            all_b = self._ios(months)
            lines = [f"The In/Out Sale page does not split **sale pcs, sale amount or net sale** by In-house / Outsource - "
                     f"sale figures are kept for the whole company per month only ({sheet}).",
                     f"Company sale pcs · {when}: **{_show(_kpi(all_b, 'Sale pcs'))}**."]
            tt = self._type_totals(months)
            ih, ot = tt["In-house"][0], tt["Outsource"][0]
            if ih is not None and ot is not None:
                lines.append(f"The In-house / Outsource split exists for **incoming pcs** only: In-house {fmt.fmt_int(ih)} pcs, "
                             f"Outsource {fmt.fmt_int(ot)} pcs. Ask \"In-house vs outsource incoming\" for that comparison.")
            return "\n".join(lines), {**ctx, "metric": "Sale pcs"}

        # ---- fabricator-wise incoming (one fabricator, a type, or the ranking)
        if len(kinds) == 2 and not fab_ents:
            tt = self._type_totals(months)
            (ih, ih_n), (ot, ot_n) = tt["In-house"], tt["Outsource"]
            if ih is None or ot is None:
                return None
            tot = ih + ot
            lines = [f"**Incoming pcs: In-house vs Outsource** · {when} · {sheet}",
                     "| Type | Fabricators | Incoming pcs | Share % |", "|---|---|---|---|",
                     f"| In-house | {len(ih_n)} | {fmt.fmt_int(ih)} | {ih / tot * 100 if tot else 0:.1f}% |",
                     f"| Outsource | {len(ot_n)} | {fmt.fmt_int(ot)} | {ot / tot * 100 if tot else 0:.1f}% |"]
            both = sorted(set(ih_n) & set(ot_n))
            if both:
                lines.append(f"{', '.join(both)} send{'s' if len(both) == 1 else ''} pcs of both kinds (the sheet marks "
                             f"some months \"(OUT SOURCE)\"), so these figures follow the page's Type filter, month by month.")
                split = {x.get("label"): x.get("value") for x in (self._ios(months).get("charts") or {}).get("fab_split") or []}
                if split.get("In-house") is not None and abs(split["In-house"] - ih) > 0.5:
                    lines.append(f"The page's In-house / Outsource pie counts a fabricator as Outsource for every month once "
                                 f"any month is marked so: In-house {fmt.fmt_int(split['In-house'])}, Outsource "
                                 f"{fmt.fmt_int(split.get('Outsource') or 0)} pcs. Same total, split differently.")
            if ih != ot:
                hi, lo, a, b = ("In-house", "Outsource", ih, ot) if ih > ot else ("Outsource", "In-house", ot, ih)
                lines.append(f"**{hi}** is higher by **{fmt.fmt_int(a - b)} pcs** ({fmt.fmt_int(a)} − {fmt.fmt_int(b)}"
                             + (f", {(a - b) / b * 100:.1f}% more" if b else "") + ").")
            return "\n".join(lines), {**ctx, "metric": "Incoming pcs", "dim": "fabricator"}

        if fab_ents or typ or incoming_fab or re.search(r"\b(fabricators?|fabricator wise)\b", raw):
            body = self._ios(months, fab_ents, typ)
            cols, rows = _table(body, "fabricators")
            it, itot, ish = _col(cols, "Type"), _col(cols, "Total"), _col(cols, "Share")
            if itot is None:
                return None
            data = [r for r in rows if not SPECIAL.match(str(r[0]))]
            if not data:
                return None
            total = sum(r[itot] or 0 for r in data)
            all_b = self._ios(months) if (fab_ents or typ) else body          # shares are of ALL fabricators' incoming
            ac, ar = _table(all_b, "fabricators")
            ai = _col(ac, "Total")
            grand = sum(r[ai] or 0 for r in ar if not SPECIAL.match(str(r[0]))) if ai is not None else total
            lines = [f"**Incoming pcs by fabricator**{' (' + typ + ')' if typ else ''} · {when} · {sheet}"]
            if re.search(r"\b(highest|most|top|lowest|least|which|kaun|sabse)\b", raw) and not fab_ents:
                low = re.search(r"\b(lowest|least)\b", raw)
                pick = (min if low else max)(data, key=lambda r: r[itot] or 0)
                lines.append(f"**{pick[0]}** has the {'lowest' if low else 'highest'} incoming pcs: "
                             f"**{fmt.fmt_int(pick[itot])} pcs** ({pick[itot] / total * 100:.1f}% of {fmt.fmt_int(total)})."
                             if total else "")
            if fab_ents and len(data) <= 6:
                lines += [f"• **{r[0]}** ({r[it]}): **{fmt.fmt_int(r[itot])} pcs**"
                          + (f" — {r[itot] / grand * 100:.1f}% of all fabricators' incoming ({fmt.fmt_int(r[itot])} ÷ "
                             f"{fmt.fmt_int(grand)} × 100)" if grand else "")
                          for r in data]
                if len(data) == 2:
                    a, b = sorted(data, key=lambda r: -(r[itot] or 0))
                    lines.append(f"**{a[0]}** is higher by **{fmt.fmt_int(a[itot] - b[itot])} pcs** "
                                 f"({fmt.fmt_int(a[itot])} − {fmt.fmt_int(b[itot])}).")
            else:
                lines += ["| Fabricator | Type | Incoming pcs | Share % |", "|---|---|---|---|"]
                for r in sorted(data, key=lambda r: -(r[itot] or 0))[:15]:
                    share = (r[itot] / grand * 100) if grand else 0
                    lines.append(f"| {r[0]} | {r[it]} | {fmt.fmt_int(r[itot])} | {share:.1f}% |")
                if typ:
                    lines.append(f"{typ} total: **{fmt.fmt_int(total)} pcs** = {total / grand * 100:.1f}% of all "
                                 f"{fmt.fmt_int(grand)} incoming pcs (share = fabricator ÷ all fabricators × 100)." if grand else "")
                else:
                    lines.append(f"Total: **{fmt.fmt_int(total)} pcs** (share = fabricator ÷ total × 100).")
            if not typ and not fab_ents:
                tt = self._type_totals(months)
                ih, ot = tt["In-house"][0], tt["Outsource"][0]
                if ih is not None and ot is not None and total:
                    lines.append(f"In-house **{fmt.fmt_int(ih)} pcs** ({ih / total * 100:.1f}%), outsource "
                                 f"**{fmt.fmt_int(ot)} pcs** ({ot / total * 100:.1f}%) - the page's Type filter.")
            lines.append(self._incoming_gap(all_b, grand))
            lines.append("The Fabricators page's \"Monthly incoming\" comes from the stock sheet, so it can differ.")
            return "\n".join(x for x in lines if x), {**ctx, "metric": "Incoming pcs", "dim": "fabricator"}

        body = self._ios(months)
        k = lambda s: _kpi(body, s)
        cols_c, rows_c = _table(body, "compare")
        cols_f, rows_f = _table(body, "flow")
        wanted_early = [lab for lab, rx in self.IOS_METRICS if re.search(rx, raw)]
        if "Net sale" in wanted_early and "Net sale per pc" in wanted_early:
            wanted_early.remove("Net sale")
        yrs = body.get("years") or {}
        this_y, last_y = yrs.get("this", "this year"), yrs.get("last", "last year")

        # ---- this year against last year
        if re.search(r"\b(last year|previous year|prev year|pichhle saal|pichle saal|yoy|year on year|vs 20\d\d|"
                     r"compared? (?:to|with) 20\d\d|2025)\b", raw) or (
                re.search(r"\b(compare|comparison|vs|versus)\b", raw) and not months and re.search(r"\byear\b", raw)):
            if not rows_c:
                return None
            shown_rows = [r for r in rows_c if not SPECIAL.match(str(r[0])) and (not months or r[0] in months)]
            span = (f"{shown_rows[0][0]} to {shown_rows[-1][0]}" if len(shown_rows) > 1 else
                    (shown_rows[0][0] if shown_rows else "")) if shown_rows else ""
            period = (f"all available months of FY {this_y} ({span})" if not months else
                      " and ".join(months))
            lines = [f"**{this_y} vs {last_y}** · Period: {period} · same months in both years · {sheet}"]
            for lab in [w for w in wanted_early if w not in ("Sale pcs",)] if wanted_early else []:
                kp = k(lab)
                if kp is not None and kp.get("hint") and "vs" in str(kp["hint"]):
                    lines.append(f"{lab} {this_y}: **{_show(kp)}** ({kp['hint']})")
            lines += [f"| Month | Sale pcs {this_y} | Sale pcs {last_y} | Pcs change % | Net sale {this_y} | Net sale {last_y} | Net change % |",
                      "|---|---|---|---|---|---|---|"]
            tot = [0.0, 0.0, 0.0, 0.0]
            for r in rows_c:
                if SPECIAL.match(str(r[0])) or (months and r[0] not in months):
                    continue
                for i, j in enumerate((1, 2, 4, 5)):
                    tot[i] += r[j] or 0
                ch = lambda v: f"{v:+.1f}%" if isinstance(v, (int, float)) else "—"
                lines.append(f"| {r[0]} | {fmt.fmt_int(r[1])} | {fmt.fmt_int(r[2])} | {ch(r[3])} | {self._inr(r[4])} | "
                             f"{self._inr(r[5])} | {ch(r[6])} |")
            if tot[1]:
                lines.append(f"Total sale pcs: **{fmt.fmt_int(tot[0])}** vs {fmt.fmt_int(tot[1])} = "
                             f"**{(tot[0] - tot[1]) / tot[1] * 100:+.1f}%** "
                             f"(({fmt.fmt_int(tot[0])} − {fmt.fmt_int(tot[1])}) ÷ {fmt.fmt_int(tot[1])} × 100).")
            if tot[3]:
                lines.append(f"Total net sale: **{self._inr(tot[2])}** vs {self._inr(tot[3])} = "
                             f"**{(tot[2] - tot[3]) / tot[3] * 100:+.1f}%**.")
            return "\n".join(lines), {**ctx, "metric": "Sale pcs", "dim": "month"}

        wanted = [lab for lab, rx in self.IOS_METRICS if re.search(rx, raw)]
        if not wanted and follow and ctx_in.get("metric") in dict(self.IOS_METRICS):
            wanted = [ctx_in["metric"]]
        if not wanted and re.search(r"\bsales?\b", raw):
            wanted = ["Sale pcs", "Sale amount", "Net sale"]
        if "Net sale" in wanted and "Net sale per pc" in wanted:
            wanted.remove("Net sale")
        if "Sale amount" in wanted and "Net sale" in wanted:
            pass

        # ---- deducted share
        if re.search(r"\bdeduct\w*\b", raw) and rows_f:
            ci = {c: i for i, c in enumerate(cols_f)}
            rows = [r for r in rows_f if not SPECIAL.match(str(r[0])) and (not months or r[0] in months)]
            amt, net = sum(r[ci["Sale amount"]] or 0 for r in rows), sum(r[ci["Net sale"]] or 0 for r in rows)
            if amt:
                return (f"**Deducted from sale amount** · {when}: sale amount {self._inr(amt)} − net sale "
                        f"{self._inr(net)} = **{self._inr(amt - net)}**, which is **{(amt - net) / amt * 100:.2f}%** "
                        f"of the sale amount ({self._inr(amt - net)} ÷ {self._inr(amt)} × 100).", {**ctx, "metric": "Net sale"})

        # ---- month by month / best month / flow
        by_month = re.search(r"\b(month wise|month-wise|monthly|month by month|by month|each month|har mahine|"
                             r"which month|flow)\b", raw)
        extreme = re.search(r"\b(highest|lowest|best|worst|most|least|max|maximum|minimum|sabse)\b", raw)
        if rows_f and (by_month or (len(months) != 1 and (len(wanted) > 1 or extreme))) and not (len(months) == 1):
            ci = {c: i for i, c in enumerate(cols_f)}
            rows = [r for r in rows_f if not SPECIAL.match(str(r[0])) and (not months or r[0] in months)]
            lab = {"Sale pcs": "Sale pcs", "Net sale": "Net sale", "Sale amount": "Sale amount",
                   "Net sale per pc": "Net per pc", "Incoming pcs": "Incoming pcs", "Order pcs": "Order pcs",
                   "Sent to production": "Sent to production"}
            keyl = lab.get(wanted[0], "Sale pcs") if wanted else "Sale pcs"
            if extreme and keyl in ci:
                low = re.search(r"\b(lowest|worst|least|minimum)\b", raw)
                pick = (min if low else max)(rows, key=lambda r: r[ci[keyl]] or 0)
                v = pick[ci[keyl]]
                shown = self._inr(v) if keyl in ("Net sale", "Sale amount", "Net per pc") else f"{fmt.fmt_int(v)} pcs"
                return (f"**{pick[0]}** has the {'lowest' if low else 'highest'} {keyl.lower()}: **{shown}** "
                        f"({sheet}).", {**ctx, "metric": keyl, "dim": "month", "intent": "rank"})
            show = [c for c in ("Order pcs", "Sent to production", "Incoming pcs", "Sale pcs", "Sale amount", "Net sale",
                                "Net per pc") if c in ci]
            lines = [f"**Order → production → incoming → sale by month** · {sheet}",
                     "| Month | " + " | ".join(show) + " |", "|---|" + "---|" * len(show)]
            money = {"Sale amount", "Net sale", "Net per pc"}
            for r in rows:
                lines.append(f"| {r[0]} | " + " | ".join(self._inr(r[ci[c]]) if c in money else fmt.fmt_int(r[ci[c]])
                                                         for c in show) + " |")
            return "\n".join(lines), {**ctx, "metric": keyl, "dim": "month", "intent": "trend"}

        # ---- named figures (for the months asked) or the whole summary
        if wanted and not re.search(r"\b(summary|overview|saar|all figures|everything)\b", raw):
            lines = [f"**In/Out Sale** · {when} · {sheet}"]
            for lab in wanted:
                kp = k(lab)
                if kp is None:
                    continue
                hint = f" — {kp['hint']}" if kp.get("hint") and "vs" in str(kp.get("hint")) else ""
                lines.append(f"• {lab}: **{_show(kp)}**{hint}")
            if len(lines) == 1:
                return None
            if "Incoming pcs" in wanted:
                fc, fr = _table(body, "fabricators")
                fi = _col(fc, "Total")
                if fi is not None:
                    lines.append(self._incoming_gap(body, sum(r[fi] or 0 for r in fr if not SPECIAL.match(str(r[0])))))
            if "Net sale" in wanted and k("Net sale") and k("Sale amount") and "Sale amount" not in wanted:
                lines.append(f"(Net sale is the sale amount less deductions: {_show(k('Sale amount'))} sale amount.)")
            return "\n".join(lines), {**ctx, "metric": wanted[0]}
        lines = [f"**In/Out Sale summary** · {when} · {sheet}"]
        for kp in _kpis(body):
            hint = f" — {kp['hint']}" if kp.get("hint") else ""
            lines.append(f"• {kp['label']}: **{_show(kp)}**{hint}")
        for ch in body.get("checks") or []:
            if isinstance(ch, dict) and ch.get("text"):
                lines.append(f"Note from the page: {ch['text']}")
        return "\n".join(lines), {**ctx, "metric": "Sale pcs"}

    # ------------------------------------------------------------------------------------------------ Clients Order Status
    DELIVERY = re.compile(r"\b(expected deliver\w*|delivery (?:date|month|by month|due|schedule)|deliveries|"
                          r"due in (?:the )?next \d+ days?|due in \d+ days?|due (?:soon|later)|60 days? deliver\w*|"
                          r"delivery due|overdue deliver\w*|deliver\w* overdue|oldest delivery)\b")
    FW = re.compile(r"\bfw orders?\b|\bfw order s\b|\bfw dispatch\w*\b|\bdispatched pcs\b|\bdispatch(?:ed)? pending\b")

    @staticmethod
    def _month_name(v) -> str:
        from datetime import datetime, timedelta
        m = re.fullmatch(r"([A-Za-z]{3})[A-Za-z]*-(?:20)?(\d{2})", str(v).strip())
        if m:                                   # "Apr-2026" (FW ORDER'S) -> "April-26", the dashboard's month label
            try:
                return datetime.strptime(m.group(1).title() + m.group(2), "%b%y").strftime("%B-%y")
            except ValueError:
                return str(v)
        if isinstance(v, str) and re.fullmatch(r"\d{5}(\.0+)?", v.strip()):
            v = float(v)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and 20000 < v < 80000:
            d = datetime(1899, 12, 30) + timedelta(days=float(v))
            return d.strftime("%B-%y")
        return str(v)

    def fw_orders(self, text: str, entities, months: list[str], explicit: list[str]):
        raw = re.sub(r"['’]", " ", text.lower())
        if not self.FW.search(raw):
            return None
        body = self.fetch("client", {})
        fw = body.get("fw_orders")
        if not fw:
            err = body.get("fw_orders_error")
            return ("FW ORDER'S isn't available on the dashboard right now" + (f" ({err})" if err else "") + ".",
                    {"page": "client", "metric": None, "intent": "value", "entities": [], "months": months, "dim": None})
        cols, rows = _table(fw, "table") if False else ([c["label"] if isinstance(c, dict) else c for c in
                                                         fw["table"]["columns"]], fw["table"]["rows"])
        rows = [r for r in rows if str(r[0]).upper() != "TOTAL"]
        for r in rows:
            r[0] = self._month_name(r[0])
        pick = [r for r in rows if not months or r[0] in months]
        if months and not pick:
            return (f"FW ORDER'S has no row for {' and '.join(months)}.", {"page": "client", "metric": None,
                                                                         "intent": "value", "entities": [],
                                                                         "months": months, "dim": None})
        o, d, p = (sum(r[i] or 0 for r in pick) for i in (1, 2, 3))
        pct = f"{d / (d + p) * 100:.1f}%" if (d + p) else "—"
        lines = ["**FW ORDER'S** (Clients Order Status page · DASHBOARD tab of the master sheet) · " +
                 (" and ".join(months) if months else "all months from April"),
                 "| Month | Order pcs | Dispatched pcs | Pending pcs | Overall dispatched pcs |", "|---|---|---|---|---|"]
        lines += [f"| {r[0]} | {fmt.fmt_int(r[1])} | {fmt.fmt_int(r[2])} | {fmt.fmt_int(r[3])} | {fmt.fmt_int(r[4])} |"
                  for r in pick]
        if len(pick) > 1:
            lines.append(f"Total: order **{fmt.fmt_int(o)}**, dispatched **{fmt.fmt_int(d)}**, pending **{fmt.fmt_int(p)}** pcs.")
        lines.append(f"Dispatched share: {pct} (dispatched ÷ (dispatched + pending) × 100 = {fmt.fmt_int(d)} ÷ "
                     f"{fmt.fmt_int(d + p)}).")
        if o:
            lines.append(f"Compared with order pcs: dispatched is {d / o * 100:.1f}% of {fmt.fmt_int(o)} and pending is "
                         f"{p / o * 100:.1f}%" + (f" - dispatched + pending ({fmt.fmt_int(d + p)}) is "
                                                 f"{fmt.fmt_int(abs(d + p - o))} pcs {'more' if d + p > o else 'less'} "
                                                 f"than ordered, as the sheet has it." if abs(d + p - o) > 0.5 else "."))
        for ch in fw.get("checks") or []:
            if isinstance(ch, dict) and ch.get("text"):
                lines.append(f"Note from the page: {ch['text']}")
        opts = (body.get("options") or {}).get("client") or []
        fw_name = next((c for c in opts if str(c).strip().upper() == "FW"), None)
        if fw_name and not months:
            qty = _kpi(self.fetch("client", {"client": [fw_name]}), "Total quantity")
            if qty and isinstance(qty.get("value"), (int, float)):
                same = abs(qty["value"] - o) < 0.5
                lines.append(f"Cross-check: the client FW's total quantity on this page is {_show(qty)}"
                             + (" - the same as FW ORDER'S order pcs." if same else
                                f", {fmt.fmt_int(abs(qty['value'] - o))} pcs different from FW ORDER'S (different sheets)."))
        return "\n".join(lines), {"page": "client", "metric": "Order pcs", "intent": "value", "entities": [],
                                  "months": months, "dim": None}

    def deliveries(self, text: str, entities, months: list[str], explicit: list[str]):
        raw = text.lower()
        overdue_designs = re.search(r"\b(overdue|late)\b", raw) and re.search(r"\bdesigns?\b", raw) and not re.search(
            r"\b(production|fabricator|po|fabric)\b", raw)
        deliver_q = re.search(r"\bdeliver\w*\b", raw) and not re.search(r"\b(on[\s-]?time|ontime|delay\w*|late|vendor|po|pos|"
                                                                    r"fabric)\b", raw) and (
            months or re.search(r"\b(due|pending|kitne|kitna|kitni|how many|how much|hone|honi|baki|baaki|expected|"
                                r"next|upcoming|aane)\b", raw))
        if not (self.DELIVERY.search(raw) or deliver_q or overdue_designs or
                ("client" in explicit and re.search(r"\b(overdue|due)\b", raw))):
            return None
        clients = [e for e in entities if e.type == "client" and e.raw.get("client")]
        if any(e.type not in ("client", "month") for e in entities):
            return None
        f: dict = {}
        if clients:
            f["client"] = [e.raw["client"] for e in clients]
        body = self.fetch("client", f)
        d = body.get("delivery60")
        if not d:
            return None
        ks = {k["label"]: k for k in _kpis(d)}
        cols_m, rows_m = _table(d, "months")
        cols_c, rows_c = _table(d, "clients")
        who = " and ".join(e.display for e in clients) or "all clients"
        ctx = {"page": "client", "metric": "Pending", "intent": "value",
               "entities": [{"type": "client", "value": e.display} for e in clients], "months": [], "dim": None}
        lead = []
        want_over = re.search(r"\boverdue\b", raw)
        want_week = re.search(r"\b(next (?:7|seven) days?|in 7 days?|7 days?|this week)\b", raw)
        want_late = re.search(r"\b(due later|later)\b", raw)
        if re.search(r"\b(which|who|kaun|most|highest|sabse)\b", raw) and not clients and rows_c:
            key = "Overdue pcs" if want_over else "Pending pcs"
            i = _col(cols_c, key)
            data = [r for r in rows_c if not SPECIAL.match(str(r[0]))]
            if i is not None and data:
                top = max(data, key=lambda r: r[i] or 0)
                lines = [f"**{top[0]}** has the most {key.lower()} in expected deliveries: **{fmt.fmt_int(top[i])} pcs** "
                         f"({fmt.fmt_int(top[i])} of {fmt.fmt_int(sum(r[i] or 0 for r in data))})."]
                lines += [f"• {r[0]}: {fmt.fmt_int(r[i])} pcs" for r in sorted(data, key=lambda r: -(r[i] or 0))]
                return "\n".join(lines), ctx
        if want_week and "Due in 7 days" in ks:
            lead.append(f"Due in the next 7 days ({who}): **{_show(ks['Due in 7 days'])}** ({ks['Due in 7 days'].get('hint')}).")
        elif overdue_designs and "Overdue" in ks:
            lead.append(f"Overdue designs ({who}, 60-day delivery date passed): **{(ks['Overdue'].get('hint') or '').split(' ')[0]} designs** "
                        f"= {_show(ks['Overdue'])}. (The Production page's Overdue pcs counts a different date.)")
        elif want_over and "Overdue" in ks:
            lead.append(f"Overdue ({who}, delivery date passed): **{_show(ks['Overdue'])}** ({ks['Overdue'].get('hint')}) "
                        f"of {_show(ks['Pending'])} pending.")
        elif want_late and "Due later" in ks:
            lead.append(f"Due later ({who}): **{_show(ks['Due later'])}** ({ks['Due later'].get('hint')}).")
        lines = [f"**Expected deliveries** ({who}) · pending pcs by the 60-day delivery date"] + lead
        if not lead:
            lines += [f"• {k['label']}: **{_show(k)}**" + (f" ({k['hint']})" if k.get("hint") else "") for k in ks.values()]
        else:
            rows_c = []
        if months and rows_m:
            lines = [lines[0]]
            rows_m = [r for r in rows_m if r[0] in months]
            rows_c = []
            if not rows_m:
                return (f"There are no expected deliveries in {' and '.join(months)} (the delivery dates run "
                        f"{d.get('today')} onward).", ctx)
        if rows_m and not (lead and not months):
            lines += ["| Delivery month | Designs | Pending pcs | Overdue pcs |", "|---|---|---|---|"]
            for r in rows_m:
                lines.append(f"| {r[0]} | {fmt.fmt_int(r[1])} | {fmt.fmt_int(r[2])} | {fmt.fmt_int(r[3])} |")
        if rows_c and not clients:
            lines += ["| Client | Designs | Pending pcs | Overdue pcs | Oldest delivery date |", "|---|---|---|---|---|"]
            lines += [f"| {r[0]} | {fmt.fmt_int(r[1])} | {fmt.fmt_int(r[2])} | {fmt.fmt_int(r[3])} | {r[4] or '—'} |"
                      for r in rows_c]
        lines.append(f"As of {d.get('today')}: Overdue = delivery date before today. Pending pcs are the Clients "
                     "page's Pending (sheet column AU).")
        lines.append(self._pending_kinds(f, d))
        return "\n".join(x for x in lines if x), ctx

    def _pending_kinds(self, f: dict, d: dict) -> str:
        """Four "pending" figures people mix up, each with its own source."""
        ks = {k["label"]: k for k in _kpis(d)}
        try:
            prod = _kpi(self.fetch("production", {}), "Pending") if not f else None
        except Exception:
            prod = None
        bits = [f"expected delivery pcs = pending pcs grouped by their 60-day delivery date (this answer)",
                f"overdue pcs = the part whose delivery date has passed ({_show(ks.get('Overdue'))})",
                f"client pending = the same pending pcs split by client (Clients Order Status, {_show(ks.get('Pending'))})"]
        if prod:
            bits.append(f"production pending = Production page Pending, by order month ({_show(prod)}; the same sheet "
                        f"column, so the totals match)")
        return "What the pending figures mean: " + "; ".join(bits) + "."

    def _designer_target(self, body: dict, t: str):
        """The dashboard has one yearly NEW-order target for the company; there is no target per designer. The honest
        answer says so and ranks designers by what counts toward that target (NEW revenue)."""
        tracker = body.get("tracker") or {}
        tgt, ach = _kpi(tracker, "Yearly target"), _kpi(tracker, "Achieved (new)")
        cols, rows = _table(body.get("filtered") or {}, "designers")
        inew, itot = _col(cols, "New Revenue"), _col(cols, "Total Revenue")
        data = [r for r in rows if not SPECIAL.match(str(r[0])) and str(r[0]).upper() != "(NOT ASSIGNED)"]
        if inew is None or not data or not tgt or not ach:
            return None
        low = re.search(r"\b(lowest|least|minimum|worst|kam|sabse kam|bottom)\b", t)
        data.sort(key=lambda r: (r[inew] or 0), reverse=not low)
        a = ach["value"]
        pick = data[0]
        lines = [f"The Designer Order Target page has **no target per designer** - only the company's yearly NEW-order "
                 f"target of {_show(tgt)}, of which {_show(ach)} is achieved ({a / tgt['value'] * 100:.2f}%). "
                 f"So a designer's own achievement % can't be worked out.",
                 f"What can be measured is each designer's share of the achieved NEW revenue (the revenue that counts "
                 f"toward the target). {'Lowest' if low else 'Highest'}: **{pick[0]}** with "
                 f"**{fmt.inr_short(pick[inew] or 0)}** = {(pick[inew] or 0) / a * 100:.2f}% of {fmt.inr_short(a)} "
                 f"({fmt.inr_short(pick[inew] or 0)} ÷ {fmt.inr_short(a)} × 100).",
                 "| Designer | New revenue | Share of achieved (new) | Total revenue |", "|---|---|---|---|"]
        for r in data[:12]:
            lines.append(f"| {r[0]} | {fmt.inr_short(r[inew] or 0)} | {(r[inew] or 0) / a * 100:.2f}% | "
                         f"{fmt.inr_short(r[itot] or 0) if itot is not None else '—'} |")
        lines.append("FLO Future's Done % is a different measure (promised samples completed) and isn't used here.")
        return "\n".join(lines), {"page": "target", "metric": "New Revenue", "intent": "rank", "entities": [],
                                  "months": [], "dim": "designer"}
