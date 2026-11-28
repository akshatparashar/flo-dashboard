"""Daily Delegation dashboard (sheet "Sir_Daily_Delegation_Tracker", tab "Daily Schedule" only).

The tab is Sir's day as a list: one row per task / meeting / follow-up with the date, Task, Responsible Person,
Status and Remarks. There is no deadline column, so "how long has this been open" is measured from the row's date.
Columns are found by their header text. The date column is headed "Date", or "Day" since 28 Nov 2026; a "Day" column
beside a "Date" column is ignored (the weekday is worked out from the date instead).
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from ..core import norm_key, parse_dates, today_ist
from ..tables import kpi, notice, table

TAB = "Daily Schedule"
STATUSES = ["Completed", "In Progress", "Awaiting Approval", "Pending", "On Hold", "Status Not Set"]
OPEN_STATUSES = [s for s in STATUSES if s != "Completed"]
STATUS_ALIASES = {
    "COMPLETED": "Completed", "COMPLETE": "Completed", "DONE": "Completed",
    "INPROGRESS": "In Progress", "WIP": "In Progress", "ONGOING": "In Progress",
    "AWAITINGAPPROVAL": "Awaiting Approval", "AWAITINGSIRSAPPROVAL": "Awaiting Approval", "APPROVAL": "Awaiting Approval",
    "PENDING": "Pending", "NOTSTARTED": "Pending", "OPEN": "Pending",
    "ONHOLD": "On Hold", "HOLD": "On Hold",
}
AGE_BUCKETS = [("Today", 0, 0), ("1-2 days", 1, 2), ("3-5 days", 3, 5), ("6+ days", 6, 10**6)]
HEADERS = {"date": "DATE", "day": "DAY", "task": "TASK", "person": "RESPONSIBLE", "status": "STATUS", "remarks": "REMARKS"}


def _clean(v) -> str:
    return re.sub(r"\s+", " ", str(v if v is not None else "")).strip()


def clean_person(v) -> str:
    """'arihant sir' / 'Arihant Sir ' -> 'Arihant Sir'."""
    s = _clean(v)
    return " ".join(w[:1].upper() + w[1:].lower() for w in s.split(" ")) if s else ""


def clean_status(v) -> str:
    s = _clean(v)
    if not s:
        return "Status Not Set"
    return STATUS_ALIASES.get(norm_key(s), s.title())


def _date_column(grid, hr, cols):
    """The column holding each row's date: the one headed "Date", else the "Day" column when it holds dates (the tab
    has been laid out both ways). A "Day" column of weekday names is not a date column."""
    if cols["date"] is not None:
        return cols["date"]
    day, task = cols["day"], cols["task"]
    if day is None:
        return None
    values = [str(row[day]) for row in grid[hr + 1:] if day < len(row) and task < len(row) and _clean(row[task])]
    return day if any(re.search(r"\d", v) for v in values) else None


def parse_daily_schedule(grid):
    """Raw grid -> {"rows": DataFrame, "problems": [...]} (one row per task)."""
    hr, cols = None, {}
    for r, row in enumerate(grid or []):
        keys = [norm_key(v) for v in row]
        found = {name: next((i for i, k in enumerate(keys) if k.startswith(want)), None) for name, want in HEADERS.items()}
        if found["task"] is not None and found["status"] is not None and (found["date"] is not None or found["day"] is not None):
            hr, cols = r, found
            break
    if hr is None:
        return {"rows": pd.DataFrame(), "problems": ["header"]}
    cols["date"] = _date_column(grid, hr, cols)
    recs = []
    for r in range(hr + 1, len(grid)):
        row = grid[r]
        get = lambda n: row[cols[n]] if cols.get(n) is not None and cols[n] < len(row) else ""
        task = _clean(get("task"))
        if not task:
            continue                                  # empty template row
        recs.append({"sheet_row": r + 1, "date_raw": get("date"), "task": task, "person": clean_person(get("person")),
                     "status": clean_status(get("status")), "remarks": _clean(get("remarks"))})
    df = pd.DataFrame(recs, columns=["sheet_row", "date_raw", "task", "person", "status", "remarks"])
    df["date"] = parse_dates(df["date_raw"]) if len(df) else pd.NaT
    return {"rows": df, "problems": []}


def _lab(d) -> str:
    return d.strftime("%d %b %Y") if pd.notna(d) else "(No date)"


def delegation_options(parsed):
    d = parsed["rows"]
    if d.empty:
        return {"date": [], "person": [], "status": []}
    dates = sorted(d["date"].dropna().unique())
    return {"date": [_lab(pd.Timestamp(x)) for x in dates] + (["(No date)"] if d["date"].isna().any() else []),
            "person": sorted(p for p in d["person"].unique() if p) + (["(Not assigned)"] if (d["person"] == "").any() else []),
            "status": [s for s in STATUSES if s in set(d["status"])] + sorted(set(d["status"]) - set(STATUSES))}


def _pct(a, b) -> float:
    return round(a / b * 100, 1) if b else 0.0


def _counts(x):
    return {s: int((x["status"] == s).sum()) for s in STATUSES}


def daily_delegation_dashboard(parsed, f, today=None):
    d = parsed["rows"]
    if "header" in parsed.get("problems", []):
        return {"empty": True, "notices": [notice("The Daily Schedule tab's header row was not found, so its layout may "
                                                  "have changed. It needs the columns Task, Status and Date (or Day "
                                                  "holding the dates).", "warning")]}
    if d.empty:
        return {"empty": True, "notices": [notice("The Daily Schedule tab has no tasks yet (a header row with Date, "
                                                  "Task and Status, then one row per task).", "warning")]}
    today = pd.Timestamp(today if today is not None else today_ist()).normalize()
    d = d.copy()
    d["date_label"] = [_lab(x) for x in d["date"]]
    d["person_label"] = d["person"].replace("", "(Not assigned)")
    d["day"] = [x.strftime("%a") if pd.notna(x) else "" for x in d["date"]]
    d["age"] = np.where((d["status"] != "Completed") & d["date"].notna(), (today - d["date"]).dt.days.clip(lower=0), np.nan)
    opts = delegation_options(parsed)

    x = d
    for col, key in (("date_label", "date"), ("person_label", "person"), ("status", "status")):
        if f.get(key):
            x = x[x[col].isin(f[key])]
    q = (f.get("q") or [""])[0].strip().lower()
    if q:
        x = x[x["task"].str.lower().str.contains(q, regex=False) | x["person_label"].str.lower().str.contains(q, regex=False)
              | x["remarks"].str.lower().str.contains(q, regex=False)]
    base = {"options": opts, "today": today.strftime("%d %b %Y"), "checks": _checks(d)}
    if x.empty:
        return {**base, "no_match": True}

    n = len(x)
    c = _counts(x)
    done, open_n = c["Completed"], n - c["Completed"]
    open_x = x[x["status"] != "Completed"]
    oldest = open_x.loc[open_x["age"].idxmax()] if open_x["age"].notna().any() else None
    people = x[x["person"] != ""]["person"].nunique()
    today_n = int((x["date"] == today).sum())

    kpis = [
        kpi("Tasks", n, "", id="total", hint=f"{open_n} still open · {today_n} scheduled today"),
        kpi("Completed", done, "", id="completed", hint=f"{_pct(done, n):.0f}% of all tasks"),
        kpi("In progress", c["In Progress"], "", id="in_progress"),
        kpi("Pending", c["Pending"], "", id="pending", tone="alert" if c["Pending"] else None),
        kpi("Awaiting approval", c["Awaiting Approval"], "", id="awaiting", hint="Waiting for Sir's sign-off"),
        kpi("Oldest open task", float(oldest["age"]) if oldest is not None else 0, "days", id="oldest",
            hint=(oldest["task"][:56] if oldest is not None else "Nothing open")),
        kpi("People involved", people, "", id="people"),
    ]

    # per person
    pr = []
    for p, g in x.groupby("person_label"):
        cc = _counts(g)
        o = g[g["status"] != "Completed"]
        pr.append({"Person": p, "Tasks": len(g), "Completed": cc["Completed"], "In progress": cc["In Progress"],
                   "Pending": cc["Pending"], "Awaiting approval": cc["Awaiting Approval"],
                   "Open": len(o), "Done %": _pct(cc["Completed"], len(g)),
                   "Oldest open (days)": float(o["age"].max()) if o["age"].notna().any() else np.nan})
    pdf = pd.DataFrame(pr).sort_values(["Tasks", "Person"], ascending=[False, True]).reset_index(drop=True)
    ptot = {"Person": "TOTAL", **{k: float(pdf[k].sum()) for k in ("Tasks", "Completed", "In progress", "Pending", "Awaiting approval", "Open")},
            "Done %": _pct(done, n), "Oldest open (days)": float(pdf["Oldest open (days)"].max()) if pdf["Oldest open (days)"].notna().any() else np.nan}
    # per date
    dr = []
    for lab, g in x.groupby("date_label", sort=False):
        cc = _counts(g)
        dr.append({"Date": lab, "Day": g["day"].iloc[0], "Tasks": len(g), "Completed": cc["Completed"],
                   "Open": len(g) - cc["Completed"], "Done %": _pct(cc["Completed"], len(g)), "_k": g["date"].iloc[0]})
    ddf = pd.DataFrame(dr).sort_values("_k", na_position="last").drop(columns="_k").reset_index(drop=True)
    dtot = {"Date": "TOTAL", "Day": "", "Tasks": float(ddf["Tasks"].sum()), "Completed": float(ddf["Completed"].sum()),
            "Open": float(ddf["Open"].sum()), "Done %": _pct(done, n)}

    stat_present = [s for s in STATUSES if c[s]] + sorted(set(x["status"]) - set(STATUSES))
    by_person = {"categories": list(pdf["Person"]),
                 "series": [{"name": s, "values": [float((x[(x["person_label"] == p) & (x["status"] == s)]).shape[0]) for p in pdf["Person"]]}
                            for s in stat_present]}
    by_date = {"categories": list(ddf["Date"]),
               "series": [{"name": s, "values": [float(((x["date_label"] == dl) & (x["status"] == s)).sum()) for dl in ddf["Date"]]}
                          for s in stat_present]}
    ageing = []
    for label, lo, hi in AGE_BUCKETS:
        ageing.append({"label": label, "value": float(((open_x["age"] >= lo) & (open_x["age"] <= hi)).sum())})
    if open_x["date"].isna().any():
        ageing.append({"label": "No date", "value": float(open_x["date"].isna().sum())})

    tasks = x.assign(_o=(x["status"] == "Completed").astype(int), _a=-x["age"].fillna(-1)).sort_values(
        ["_o", "_a", "date", "sheet_row"], na_position="last")
    ttab = pd.DataFrame({"Date": tasks["date_label"], "Day": tasks["day"], "Task": tasks["task"],
                         "Responsible": tasks["person_label"], "Status": tasks["status"],
                         "Open for (days)": tasks["age"], "Remarks": tasks["remarks"]})
    att = open_x[(open_x["age"].fillna(0) >= 1) | (open_x["status"] == "Awaiting Approval")].sort_values(
        ["age", "sheet_row"], ascending=[False, True])
    atab = pd.DataFrame({"Task": att["task"], "Responsible": att["person_label"], "Status": att["status"],
                         "Date": att["date_label"], "Open for (days)": att["age"]})

    return {
        **base,
        "kpis": kpis,
        "summary": {"tasks": n, "completed": done, "open": open_n, "done_pct": _pct(done, n), "people": int(people),
                    "days": int(x["date"].nunique()), "awaiting": c["Awaiting Approval"], "today": today_n},
        "today_pending": _today_block(d, f, today),
        "insights": _insights(x, pdf, ddf, open_x, c, n, done),
        "charts": {"status": [{"label": s, "value": float(c[s])} for s in STATUSES if c[s]]
                   + [{"label": s, "value": float((x["status"] == s).sum())} for s in sorted(set(x["status"]) - set(STATUSES))],
                   "by_person": by_person, "by_date": by_date, "ageing": ageing},
        "tables": {"tasks": table(ttab, fmt={"Open for (days)": "int"}, sort=False),
                   "persons": table(pd.concat([pdf, pd.DataFrame([ptot])], ignore_index=True), fmt={"Done %": "pct"}, sort=False),
                   "dates": table(pd.concat([ddf, pd.DataFrame([dtot])], ignore_index=True), fmt={"Done %": "pct", "Day": "text"}, sort=False),
                   "attention": table(atab, fmt={"Open for (days)": "int"}, sort=False) if len(atab) else table(None)},
    }


def _today_block(d, f, today):
    """Open work for today, with who is responsible. Only the person and search filters apply: the date and status
    filters would hide exactly what this block is for. Tasks dated today come first, then open tasks carried over."""
    b = d
    if f.get("person"):
        b = b[b["person_label"].isin(f["person"])]
    q = (f.get("q") or [""])[0].strip().lower()
    if q:
        b = b[b["task"].str.lower().str.contains(q, regex=False) | b["person_label"].str.lower().str.contains(q, regex=False)]
    o = b[b["status"] != "Completed"]
    order = {s: i for i, s in enumerate(["Pending", "In Progress", "Awaiting Approval", "On Hold", "Status Not Set"])}

    def rows(g, aged):
        g = g.assign(_s=g["status"].map(order).fillna(9)).sort_values(["_s", "sheet_row"] if not aged else ["age", "_s", "sheet_row"],
                                                                      ascending=[True, True] if not aged else [False, True, True])
        return [{"task": r.task, "person": r.person_label, "status": r.status, "date": r.date_label,
                 "age": None if pd.isna(r.age) else int(r.age)} for r in g.itertuples()]

    t = o[o["date"] == today]
    c = o[o["date"] != today]
    return {"date": today.strftime("%d %b %Y"), "today": rows(t, False), "carried": rows(c, True),
            "today_total": int((b["date"] == today).sum())}


def _insights(x, pdf, ddf, open_x, c, n, done):
    out = []
    out.append(f"{done} of {n} tasks are completed ({_pct(done, n):.0f}%); {n - done} are still open.")
    top = pdf.iloc[0]
    out.append(f"{top['Person']} carries the most work: {int(top['Tasks'])} of {n} tasks ({_pct(top['Tasks'], n):.0f}%), "
               f"{int(top['Open'])} of them open.")
    most_open = pdf.sort_values(["Open", "Tasks"], ascending=False).iloc[0]
    if most_open["Open"] and most_open["Person"] != top["Person"]:
        out.append(f"{most_open['Person']} has the most open tasks ({int(most_open['Open'])}).")
    if c["Awaiting Approval"]:
        who = ", ".join(sorted(open_x[open_x["status"] == "Awaiting Approval"]["person_label"].unique()))
        out.append(f"{c['Awaiting Approval']} task{'s' if c['Awaiting Approval'] != 1 else ''} wait for Sir's approval (from {who}).")
    if open_x["age"].notna().any():
        old = open_x[open_x["age"] >= 1]
        if len(old):
            r = open_x.loc[open_x["age"].idxmax()]
            out.append(f"{len(old)} open task{'s' if len(old) != 1 else ''} carried over from earlier days; the oldest has been open "
                       f"{int(r['age'])} days ({r['task'][:60]}).")
    if len(ddf) >= 2:
        best = ddf.sort_values("Done %", ascending=False).iloc[0]
        worst = ddf.sort_values("Done %").iloc[0]
        if best["Date"] != worst["Date"]:
            out.append(f"{best['Date']} has the best completion rate ({best['Done %']:.0f}%), {worst['Date']} the lowest "
                       f"({worst['Done %']:.0f}%).")
    return out


def _checks(d):
    out = []
    nodate = d[d["date"].isna()]
    if len(nodate):
        out.append(notice(f"{len(nodate)} task(s) have no valid date (row {', '.join(str(r) for r in nodate['sheet_row'][:6])}"
                          f"{'…' if len(nodate) > 6 else ''}); they are shown as '(No date)'.", "warning"))
    unset = d[d["status"] == "Status Not Set"]
    if len(unset):
        out.append(notice(f"{len(unset)} task(s) have no status (row {', '.join(str(r) for r in unset['sheet_row'][:6])}"
                          f"{'…' if len(unset) > 6 else ''}).", "warning"))
    odd = sorted(set(d["status"]) - set(STATUSES))
    if odd:
        out.append(notice(f"Unknown status value(s): {', '.join(odd)}. Use Pending, In Progress, Awaiting Approval, "
                          "On Hold or Completed.", "warning"))
    nop = d[d["person"] == ""]
    if len(nop):
        out.append(notice(f"{len(nop)} task(s) have no Responsible Person (row {', '.join(str(r) for r in nop['sheet_row'][:6])}"
                          f"{'…' if len(nop) > 6 else ''}).", "warning"))
    dup = d[d.duplicated(["date_raw", "task", "person"], keep=False)]
    if len(dup):
        out.append(notice(f"{len(dup)} rows repeat the same date, task and person (row {', '.join(str(r) for r in dup['sheet_row'][:6])}"
                          f"{'…' if len(dup) > 6 else ''}).", "info"))
    return out
