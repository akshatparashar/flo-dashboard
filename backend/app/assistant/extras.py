"""Page-level answers that need more than one KPI: the dashboard summary, samples waiting for approval, pending
purchase orders, the vendor rate list and the revenue target.

Each answer reads the page's own API (same filters as the page) and only arranges what the page already shows. Labels
are matched by the start of the KPI / column label, so a renamed figure fails safe (the answer is skipped and the
general matcher takes over) instead of inventing a number.
"""
from __future__ import annotations

import re
from typing import Callable

from . import fmt
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
        if not (self.PO.search(t) and self.PO_OPEN.search(t) and self.PO_ASK.search(t)):
            return None
        if re.search(r"\b(mtr|meters?|fabric pending|pending fabric|quantity|qty|kitna)\b", t) and \
                not re.search(r"\b(which|list|how many|kitne|count)\b", t):
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
        lines = [f"**{len(open_rows):,} POs are still pending** (fabric not fully received) out of "
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
