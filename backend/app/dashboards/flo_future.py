"""FLO Future dashboard (sheet "FLO_Future <Mon YYYY>").

Ported from the FLO Future tab of the Streamlit dashboard (github.com/design355/sample-production-dashboard, kept as
legacy/streamlit_app.py; tests/test_parity_flo_future.py runs both on the same grids and compares every number).

A) Tab "Samples" -> row 1 = header, one row per promised sample (filled by hand). Columns by header name, with the
   old app's fallback positions (A=0 ...): Designer | Team | Collection / Sample | Vendor | Season | Qty Promised |
   Completed | Pending | Status | Due Date | Overdue | Promised To | Contact | Remark | Key (auto).
   Pending / Overdue / Days Left are re-calculated with the same rule as the sheet formulas:
     Pending  = Qty Promised − Completed (never below 0; 0 when Qty Promised is blank)
     Complete = Status 'Complete', or Completed ≥ Qty Promised (qty filled in and > 0)
     Overdue  = not complete and the Due Date is before today (IST).
B) Tab "Visits & Meetings" -> 'Causative Milestone' blocks; each block's numbered rows are the planned activities
   (empty rows = nothing planned). Done = 'X' or STATUS 'Done'. Each activity type has a required count per month.
C) Tab "Outsource Projects" (not in the old dashboard) -> the same rules, shown in its own section only; it never
   changes the Samples numbers.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from ..core import clean_text, norm_key, num, parse_dates, safe_div_pct, today_ist
from ..tables import kpi, notice, table, with_total

# field -> (accepted normalised header names, fallback column position A=0 ...)   [old app: FF_COLS]
FF_COLS = {
    "designer": (("DESIGNER",), 0), "team": (("TEAM",), 1), "item": (("COLLECTIONSAMPLE", "COLLECTION"), 2),
    "vendor": (("VENDOR", "CLIENT"), 3), "season": (("SEASON",), 4), "qty": (("QTYPROMISED", "QTY"), 5),
    "done": (("COMPLETED",), 6), "pending_sheet": (("PENDING",), 7), "status": (("STATUS",), 8),
    "due": (("DUEDATE",), 9), "overdue_sheet": (("OVERDUE",), 10), "to": (("PROMISEDTO",), 11),
    "contact": (("CONTACT",), 12), "remark": (("REMARK",), 13),
}
# Outsource Projects tab: Designer | Project / Collection | Outsource Vendor | Season | Qty Promised | Completed |
# Pending | Status | Due Date | Overdue | Promised To | Remark (no Team column: taken from the designer's samples)
OUT_COLS = {
    "designer": (("DESIGNER",), 0), "team": (("TEAM",), 99),
    "item": (("PROJECTCOLLECTION", "PROJECT", "COLLECTION"), 1),
    "vendor": (("OUTSOURCEVENDOR", "VENDOR"), 2), "season": (("SEASON",), 3), "qty": (("QTYPROMISED", "QTY"), 4),
    "done": (("COMPLETED",), 5), "pending_sheet": (("PENDING",), 6), "status": (("STATUS",), 7),
    "due": (("DUEDATE",), 8), "overdue_sheet": (("OVERDUE",), 9), "to": (("PROMISEDTO",), 10),
    "contact": (("CONTACT",), 99), "remark": (("REMARK",), 11),
}
FF_DUE_BUCKETS = ["Overdue", "Due Today", "Due in 1-3 Days", "Due in 4-7 Days", "Due Later (> 7 Days)",
                  "No Due Date", "Completed"]
FF_OPEN_BUCKETS = FF_DUE_BUCKETS[:-1]
URGENT = ["Overdue", "Due Today", "Due in 1-3 Days"]
FF_STATUS_ORDER = ["Complete", "In Progress", "In-House Process", "Sampling Ordered", "Corrections", "CAD In Queue",
                   "CAD In Process", "Not Started", "Not Updated"]
# Visits & Meetings: block title -> (activity type, required per month; 0 = as many as planned rows)
FF_VISIT_TYPES = [(r"MARKET", "Market Visit (Accessories)", 1),
                  (r"STORE\s*/?\s*EXHIBITION|EXHIBI", "Store / Exhibition Visit", 1),
                  (r"SURAT", "Surat Sampling Visit", 1), (r"FACTORY", "Factory / Store Visit", 2),
                  (r"MEETING", "Meetings", 0)]
FF_VISIT_STATES = ["Done", "Missed / Not Marked", "Today", "Upcoming", "Rescheduled", "Cancelled", "No Date"]
RATE_FF = {"good": 80, "mid": 40}       # Done %: green >= 80 %, amber 40-79 %, red < 40 %   [old: ff_rate_class]

SAMPLE_TAB_NAMES = ["Samples"]
SAMPLE_TAB_REGEX = r"^\s*samples?\s*$"
VISIT_TAB_NAMES = ["Visits & Meetings"]
VISIT_TAB_REGEX = r"visit|meeting"
OUTSOURCE_TAB_NAMES = ["Outsource Projects", "Outsource"]


# ------------------------------------------------------------------------------------------------ A) samples
def ff_header_row(grid):
    for r in range(min(6, len(grid))):
        keys = {norm_key(c) for c in grid[r]}
        if "DESIGNER" in keys and ({"QTYPROMISED", "STATUS", "DUEDATE"} & keys):
            return r
    return None


def ff_col_map(header, cols=FF_COLS):
    keys = [norm_key(h) for h in header]
    out = {}
    for field, (names, pos) in cols.items():
        idx = next((keys.index(n) for n in names if n in keys), None)
        if idx is None:
            idx = next((i for i, k in enumerate(keys) for n in names if k.startswith(n)), None)
        out[field] = idx if idx is not None else pos
    return out


def ff_canon_status(s):
    """Status text -> one spelling (case / extra spaces ignored). Blank -> 'Not Updated'."""
    lookup = {norm_key(v): v for v in FF_STATUS_ORDER}
    return clean_text(s).map(lambda v: "Not Updated" if v == "" else lookup.get(norm_key(v), v.strip().title()))


def build_ff_samples(values, today, cols=FF_COLS):
    """Raw 'Samples' grid (unformatted values) -> one clean row per promised sample. Returns (df, header_found)."""
    if not values:
        return pd.DataFrame(), False
    hr = ff_header_row(values)
    header_ok = hr is not None
    hr = hr if header_ok else 0
    cmap = ff_col_map(values[hr], cols)
    rows = values[hr + 1:]
    if not rows:
        return pd.DataFrame(), header_ok
    width = max(max(len(r) for r in rows), max(cmap.values()) + 1)
    # index = real sheet row number (header on sheet row hr+1 -> first data row hr+2)
    grid = pd.DataFrame([list(r) + [""] * (width - len(r)) for r in rows], index=range(hr + 2, hr + 2 + len(rows)))

    def col(field):
        return grid[cmap[field]]

    designer, item, qty_txt = clean_text(col("designer")), clean_text(col("item")), clean_text(col("qty"))
    qty, done = num(col("qty")), num(col("done"))
    keep = (designer != "") & ((item != "") | (qty != 0) | (done != 0))

    d = pd.DataFrame(index=grid.index)
    d.index.name = "sheet_row"
    d["designer"] = designer.str.title()
    team = clean_text(col("team")).str.title()
    d["team"] = team.where(team != "", "(No Team)")
    d["item"] = item.where(item != "", "(No Name)")
    for f in ("vendor", "season", "to", "contact", "remark"):
        d[f] = clean_text(col(f))
    d["qty_blank"] = qty_txt == ""
    d["qty"], d["done"] = qty, done
    d["status"] = ff_canon_status(col("status"))
    d["due"] = parse_dates(col("due")).dt.normalize()
    d["pending_sheet"] = num(col("pending_sheet"))
    d["overdue_sheet"] = clean_text(col("overdue_sheet")).str.upper().eq("OVERDUE")
    d = d[keep]
    if d.empty:
        return d, header_ok

    d["pending"] = np.where(d["qty_blank"], 0.0, (d["qty"] - d["done"]).clip(lower=0))
    d["is_complete"] = (d["status"] == "Complete") | (~d["qty_blank"] & (d["qty"] > 0) & (d["done"] >= d["qty"]))
    d["days_left"] = (d["due"] - today).dt.days            # NaN when no due date
    dl = d["days_left"]
    d["due_bucket"] = np.select(
        [d["is_complete"], dl.isna(), dl < 0, dl == 0, dl <= 3, dl <= 7],
        ["Completed", "No Due Date", "Overdue", "Due Today", "Due in 1-3 Days", "Due in 4-7 Days"],
        default="Due Later (> 7 Days)")
    d["is_overdue"] = d["due_bucket"] == "Overdue"
    d["days_overdue"] = np.where(d["is_overdue"], -dl, 0).astype(float)
    return d, header_ok


def days_text(row) -> str:
    if row["is_complete"]:
        return "Done"
    dl = row["days_left"]
    if pd.isna(dl):
        return "No date"
    dl = int(dl)
    if dl < 0:
        return f"{-dl} day{'s' if dl != -1 else ''} late"
    return "Due today" if dl == 0 else f"{dl} day{'s' if dl != 1 else ''} left"


def ff_stats(g):
    """One summary row for any slice of promised samples (totals recomputed, % never summed)."""
    tgt, done, pen = float(g["qty"].sum()), float(g["done"].sum()), float(g["pending"].sum())
    od = g[g["is_overdue"]]
    soon = g[g["due_bucket"].isin(["Due Today", "Due in 1-3 Days"])]
    return {"Items": int(len(g)), "Target Qty": tgt, "Completed": done, "Pending": pen,
            "Done %": safe_div_pct(done, tgt), "Items Done": int(g["is_complete"].sum()),
            "Overdue Items": int(len(od)), "Overdue Pcs": float(od["pending"].sum()),
            "Due ≤ 3 Days": int(len(soon)), "No Due Date": int((g["due_bucket"] == "No Due Date").sum())}


def nearest_due(g) -> str:
    open_ = g[~g["is_complete"] & g["due"].notna()]
    if open_.empty:
        return "—"
    r = open_.loc[open_["due"].idxmin()]
    return f"{r['due'].strftime('%d-%b')} ({days_text(r)})"


def ff_group(x, col, label, order=None):
    keys = order if order is not None else list(dict.fromkeys(x[col]))
    rows = [{label: k, **ff_stats(x[x[col] == k]), "Nearest Open Due": nearest_due(x[x[col] == k])}
            for k in keys if (x[col] == k).any()]
    return pd.DataFrame(rows)


# ------------------------------------------------------------------------------------------------ B) visits
def visit_type(title):
    t = str(title).upper()
    for pat, name, req in FF_VISIT_TYPES:
        if re.search(pat, t):
            return name, req
    return (str(title).strip().title() or "Other"), 0


def build_ff_visits(values, today):
    """'Visits & Meetings' block grid -> (activities df, blocks df). Empty numbered rows = nothing planned."""
    acts, blocks = [], []
    n = len(values)
    r = 0
    while r < n:
        row = values[r]
        ci = next((c for c, v in enumerate(row) if norm_key(v).startswith("CAUSATIVEMILESTONE")), None)
        if ci is None:
            r += 1
            continue
        title = next((str(v).strip() for v in row[ci + 1:] if str(v).strip()), "")
        vtype, req = visit_type(title)
        # header row = first row below with 'Sr' in it
        h = next((k for k in range(r + 1, min(r + 4, n)) if any(norm_key(v) == "SR" for v in values[k])), None)
        if h is None:
            r += 1
            continue
        keys = [norm_key(v) for v in values[h]]

        def find(*names, default=None):
            return next((i for i, k in enumerate(keys) for nm in names if k.startswith(nm)), default)

        c_sr = find("SR", default=0)
        c_act = find("PROMISEDACTION", default=c_sr + 1)
        c_freq = c_act + 1
        c_by = find("PROMISEDBYWHOM", default=c_act + 4)
        c_to = find("PROMISEDTOWHOM", "PROMISEDTO", default=c_act + 5)
        c_when = find("PROMISEDBYWHEN", default=c_act + 6)
        c_x = find("COMPLETE", default=c_act + 7)
        c_st = find("STATUS", default=c_act + 8)
        c_rm = find("REMARK", default=c_act + 9)
        freq_hdr = str(values[h][c_freq]).strip() if c_freq < len(values[h]) else ""
        planned = 0
        k = h + 1
        while k < n and not any(norm_key(v).startswith("CAUSATIVEMILESTONE") for v in values[k]):
            cells = list(values[k]) + [""] * 20

            def cell(i):
                return cells[i] if i is not None and i < len(cells) else ""

            act = str(cell(c_act)).strip()
            if act:
                planned += 1
                due = parse_dates(pd.Series([cell(c_when)])).iloc[0]
                due = due.normalize() if pd.notna(due) else pd.NaT
                st_txt = str(cell(c_st)).strip()
                stn = norm_key(st_txt)
                x_mark = norm_key(cell(c_x)) in ("X", "YES", "DONE", "TRUE", "Y")
                if x_mark or stn in ("DONE", "COMPLETE", "COMPLETED"):
                    state = "Done"
                elif stn.startswith("CANCEL"):
                    state = "Cancelled"
                elif stn.startswith("RESCHED"):
                    state = "Rescheduled"
                elif pd.isna(due):
                    state = "No Date"
                elif due < today:
                    state = "Missed / Not Marked"
                elif due == today:
                    state = "Today"
                else:
                    state = "Upcoming"
                acts.append({"sheet_row": k + 1, "type": vtype, "milestone": title, "action": act.title(),
                             "freq": (str(cell(c_freq)).strip() or freq_hdr).title(),
                             "by": str(cell(c_by)).strip().title(), "to": str(cell(c_to)).strip(),
                             "date": due, "x": "X" if x_mark else "", "sheet_status": st_txt,
                             "remark": str(cell(c_rm)).strip(), "state": state})
            k += 1
        blocks.append({"type": vtype, "milestone": title, "freq": freq_hdr.title(), "required": req,
                       "planned": planned, "sheet_row": r + 1})
        r = k
    a = pd.DataFrame(acts)
    if not a.empty:
        a["days_left"] = (a["date"] - today).dt.days
    return a, pd.DataFrame(blocks)


def ff_visit_summary(a, b):
    """One row per activity type: required this month vs planned vs done / missed / upcoming."""
    rows = []
    for vtype in dict.fromkeys(b["type"]) if not b.empty else []:
        g = a[a["type"] == vtype] if not a.empty else pd.DataFrame(columns=["state"])
        planned = int(b.loc[b["type"] == vtype, "planned"].sum())
        req = int(b.loc[b["type"] == vtype, "required"].max())
        req = max(req, planned) if req else planned
        done = int((g["state"] == "Done").sum())
        rows.append({"Activity": vtype, "Required (Month)": req, "Planned": planned, "Done": done,
                     "Missed / Not Marked": int((g["state"] == "Missed / Not Marked").sum()),
                     "Upcoming": int(g["state"].isin(["Upcoming", "Today"]).sum()),
                     "Not Planned Yet": max(req - planned, 0), "Done %": safe_div_pct(done, req)})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------------------------------------ parse
def parse_flo_future(grids: dict, today: pd.Timestamp | None = None) -> dict:
    """grids: {"samples": values, "visits": values, "outsource": values} (a missing tab -> [])."""
    today = pd.Timestamp(today if today is not None else today_ist()).normalize()
    d, header_ok = build_ff_samples(grids.get("samples") or [], today)
    va, vb = build_ff_visits(grids.get("visits") or [], today)
    o, _ = build_ff_samples(grids.get("outsource") or [], today, OUT_COLS)
    if not o.empty:
        team_of = d.groupby("designer")["team"].agg(lambda v: v.mode().iloc[0]) if not d.empty else {}
        o["team"] = o["designer"].map(team_of).fillna("(No Team)")
    return {"samples": d, "header_ok": header_ok, "visits": va, "blocks": vb, "outsource": o, "today": today,
            "has": {k: bool(grids.get(k)) for k in ("samples", "visits", "outsource")}}


# ------------------------------------------------------------------------------------------------ dashboard
def orders(d):
    """Team / designer / status orders exactly as the old filters list them."""
    team_order = sorted(d["team"].unique(), key=lambda t: (t.startswith("("), t))
    des_order = list(dict.fromkeys(d.sort_values("team", key=lambda s: s.map(team_order.index), kind="mergesort")
                                   ["designer"]))
    statuses = [s for s in FF_STATUS_ORDER if s in set(d["status"])] + \
        sorted(s for s in d["status"].unique() if s not in FF_STATUS_ORDER)
    return team_order, des_order, statuses


def ff_filter(d, f, skip=()):
    y = d
    for name, colname in (("designer", "designer"), ("team", "team"), ("status", "status"), ("due", "due_bucket")):
        if f.get(name) and name not in skip:
            y = y[y[colname].isin(f[name])]
    return y


def urgent_sort(x):
    rank = x["due_bucket"].map({b: i for i, b in enumerate(FF_DUE_BUCKETS)})
    return x.assign(_r=rank).sort_values(["_r", "days_left", "designer"], na_position="last").drop(columns="_r")


def designer_scorecard(d, x_nd, des_order):
    dsc = ff_group(x_nd, "designer", "Designer", [n for n in des_order if n in set(x_nd["designer"])])
    if dsc.empty:
        return dsc
    team_of = d.groupby("designer")["team"].agg(lambda v: v.mode().iloc[0])
    dsc.insert(1, "Team", dsc["Designer"].map(team_of))
    return dsc


def item_rows(x, first="Collection / Sample", vendor_label="Vendor"):
    """Item-level table (the old 'Sample Detail'), most urgent first, with a TOTAL row."""
    if x is None or x.empty:
        return pd.DataFrame()
    x = urgent_sort(x)
    t = pd.DataFrame({
        first: x["item"].values,
        "Designer": x["designer"].values,
        "Team": x["team"].values,
        vendor_label: x["vendor"].values,
        "Season": x["season"].values,
        "Qty": np.where(x["qty_blank"], np.nan, x["qty"]),
        "Completed": x["done"].values,
        "Pending": x["pending"].values,
        "Status": x["status"].values,
        "Due Date": x["due"].values,
        "Days Left": [days_text(r) for _, r in x.iterrows()],
        "Due Status": x["due_bucket"].values,
        "Promised To": x["to"].values,
        "Remark": x["remark"].values,
        "Sheet Row": [str(i) for i in x.index],
    })
    s = ff_stats(x)
    tot = {first: "TOTAL", "Qty": s["Target Qty"], "Completed": s["Completed"], "Pending": s["Pending"],
           "Status": f"{s['Done %']:.0f}% done · {s['Items Done']}/{s['Items']} items",
           "Days Left": f"{s['Overdue Items']} overdue"}
    return pd.concat([t, pd.DataFrame([tot])], ignore_index=True)


def designer_chart(dsc, x_nd):
    """Stacked column per designer: Completed + Pending overdue + Pending due in 0-3 days + other pending."""
    if dsc.empty:
        return {"categories": [], "series": [], "labels": []}
    o = dsc.sort_values(["Target Qty", "Designer"], ascending=[False, True]).reset_index(drop=True)
    od = o["Designer"].map(x_nd[x_nd["due_bucket"] == "Overdue"].groupby("designer")["pending"].sum()).fillna(0.0)
    soon = o["Designer"].map(x_nd[x_nd["due_bucket"].isin(["Due Today", "Due in 1-3 Days"])]
                             .groupby("designer")["pending"].sum()).fillna(0.0)
    rest = (o["Pending"] - od - soon).clip(lower=0)
    return {"categories": list(o["Designer"]),
            "series": [{"name": "Completed", "values": [float(v) for v in o["Completed"]]},
                       {"name": "Pending · Overdue", "values": [float(v) for v in od]},
                       {"name": "Pending · Due in 0-3 Days", "values": [float(v) for v in soon]},
                       {"name": "Pending · Due later / No date", "values": [float(v) for v in rest]}],
            "labels": [{"designer": r["Designer"], "team": r["Team"], "done_pct": float(r["Done %"]),
                        "completed": float(r["Completed"]), "target": float(r["Target Qty"]),
                        "items": int(r["Items"]), "overdue_items": int(r["Overdue Items"]),
                        "nearest": r["Nearest Open Due"]} for _, r in o.iterrows()]}


def visits_payload(va, vb):
    vs = ff_visit_summary(va, vb) if not vb.empty else pd.DataFrame()
    detail = pd.DataFrame()
    if not va.empty:
        order = {t: i for i, t in enumerate(dict.fromkeys(vb["type"]))}
        v = va.assign(_t=va["type"].map(order)).sort_values(["_t", "date", "sheet_row"], na_position="last")
        detail = pd.DataFrame({"Activity": v["action"].values, "Type": v["type"].values, "Frequency": v["freq"].values,
                               "By Whom": v["by"].values, "To Whom": v["to"].values, "Date": v["date"].values,
                               "State": v["state"].values, "Remark": v["remark"].values})
    chart = {"categories": list(vs["Activity"]) if len(vs) else [],
             "series": [{"name": n, "values": [float(v) for v in vs[c]] if len(vs) else []}
                        for n, c in (("Required", "Required (Month)"), ("Done", "Done"),
                                     ("Missed / Not Marked", "Missed / Not Marked"), ("Upcoming", "Upcoming"))],
             "flags": [("Not planned" if r["Planned"] == 0 else
                        (f"{int(r['Missed / Not Marked'])} not marked" if r["Missed / Not Marked"] else ""))
                       for _, r in vs.iterrows()] if len(vs) else []}
    totals = {"done": int(vs["Done"].sum()) if len(vs) else 0,
              "required": int(vs["Required (Month)"].sum()) if len(vs) else 0,
              "missed": int(vs["Missed / Not Marked"].sum()) if len(vs) else 0,
              "not_planned": int(vs["Not Planned Yet"].sum()) if len(vs) else 0}
    return vs, detail, chart, totals


def checks(d):
    """Things in the sheet that look wrong or are missing (fix them in the sheet). Never changes a number."""
    out = []
    if d.empty:
        return out
    blank = d[d["qty_blank"]]
    if len(blank):
        out.append(notice(f"Qty Promised is blank for {len(blank)} item(s): "
                          + ", ".join(f"{r['item']} ({r['designer']}, sheet row {i})" for i, r in blank.iterrows())
                          + ". They count as 0 promised and 0 pending.", "warning"))
    k = d["item"].map(norm_key)
    dup = d.assign(k=k).groupby("k")["designer"].nunique()
    for key in dup[(dup > 1) & (dup.index != norm_key("(No Name)"))].index:
        rows = d[k == key]
        out.append(notice(f"“{rows['item'].iloc[0]}” is listed under {', '.join(rows['designer'].unique())}, so its "
                          f"qty ({rows['qty'].sum():,.0f} pcs) is counted for each of them.", "warning"))
    sheet_pen = d[~d["qty_blank"] & (d["pending_sheet"].round(6) != d["pending"].round(6))]
    if len(sheet_pen):
        out.append(notice(f"The sheet's own Pending column differs from Qty − Completed on {len(sheet_pen)} row(s) "
                          "(sheet rows " + ", ".join(str(i) for i in sheet_pen.index) + "). The dashboard uses "
                          "Qty − Completed.", "info"))
    od_diff = d[d["overdue_sheet"] != d["is_overdue"]]
    if len(od_diff):
        out.append(notice(f"The sheet's Overdue column disagrees with today's date on {len(od_diff)} row(s) (sheet "
                          "rows " + ", ".join(str(i) for i in od_diff.index) + "); it may not have recalculated yet.",
                          "info"))
    nd = d[~d["is_complete"] & d["due"].isna()]
    if len(nd):
        out.append(notice(f"{len(nd)} open item(s) have no due date, so they can never show as overdue: "
                          + ", ".join(sorted(nd["designer"].unique())) + ".", "info"))
    nu = d[~d["is_complete"] & (d["status"] == "Not Updated")]
    if len(nu):
        out.append(notice(f"{len(nu)} open item(s) still have status “Not Updated”: "
                          + ", ".join(sorted(nu["designer"].unique())) + ".", "info"))
    return out


def follow_up(x):
    """Overdue, due today and due in 1-3 days: the top of the old 'most urgent first' list."""
    u = urgent_sort(x[x["due_bucket"].isin(URGENT)])
    return [{"level": "error" if r["due_bucket"] == "Overdue" else "warning", "bucket": r["due_bucket"],
             "reason": days_text(r), "item": r["item"], "designer": r["designer"], "team": r["team"],
             "vendor": r["vendor"], "status": r["status"], "pending": float(r["pending"]), "qty": float(r["qty"]),
             "due": r["due"].strftime("%d/%m/%Y") if pd.notna(r["due"]) else None,
             "days_left": None if pd.isna(r["days_left"]) else int(r["days_left"])} for _, r in u.iterrows()]


def period_label(d) -> str:
    due = d["due"].dropna() if not d.empty else pd.Series(dtype="datetime64[ns]")
    if due.empty:
        return ""
    return due.dt.to_period("M").mode().iloc[0].strftime("%b %Y")


FMT = {"Done %": "pct"}
RATES = {"Done %": RATE_FF}
ITEM_FMT = {"Due Date": "date"}


def flo_future_dashboard(parsed, f):
    d, today = parsed["samples"], parsed["today"]
    va, vb, o = parsed["visits"], parsed["blocks"], parsed["outsource"]
    notices = []
    if not parsed["header_ok"] and not d.empty:
        notices.append(notice("Header row (Designer / Qty Promised / Status / Due Date) not found in the 'Samples' "
                              "tab - default columns (A..N) were used, please verify the numbers.", "warning"))
    vs, vdetail, vchart, vt = visits_payload(va, vb)
    if vb.empty:
        notices.append(notice("'Visits & Meetings' tab not found, or it has no 'Causative Milestone' blocks.",
                              "warning"))
    base = {"period": period_label(d), "today": today.strftime("%d/%m/%Y"), "notices": notices,
            "visits": {"totals": vt, "summary": table(vs, FMT, key_col=None, sort=False, rates=RATES),
                       "detail": table(vdetail, {"Date": "date"}, key_col=None, sort=False), "chart": vchart}}
    if d.empty:
        notices.append(notice("No data found in the 'Samples' tab. Expected: row 1 = header (Designer, Team, "
                              "Collection / Sample, Vendor, Season, Qty Promised, Completed, Pending, Status, "
                              "Due Date ...), data from row 2.", "warning"))
        return {**base, "empty": True, "options": {"designer": [], "team": [], "status": [], "due": FF_DUE_BUCKETS},
                "kpis": []}

    team_order, des_order, statuses = orders(d)
    x = ff_filter(d, f)
    x_nd = ff_filter(d, f, skip=("designer",))          # designer comparison: all designers
    s = ff_stats(x)
    dg = ff_group(x, "designer", "Designer", [n for n in des_order if n in set(x["designer"])])
    most_pen = dg.loc[dg["Pending"].idxmax()] if len(dg) and dg["Pending"].max() > 0 else None
    worst = x.loc[x["days_overdue"].idxmax()] if len(x) and x["days_overdue"].max() > 0 else None
    soon_pcs = float(x.loc[x["due_bucket"].isin(["Due Today", "Due in 1-3 Days"]), "pending"].sum())

    kpis = [
        kpi("Target Qty (Promised)", s["Target Qty"], "pcs", id="target", hint=f"{s['Items']} items promised"),
        kpi("Completed", s["Completed"], "pcs", id="completed", tone="good",
            hint=f"{s['Items Done']} of {s['Items']} items done"),
        kpi("Pending", s["Pending"], "pcs", id="pending"),
        kpi("Completion %", s["Done %"], "", "pct", id="done_pct", hint="Completed ÷ Target Qty"),
        kpi("Overdue (Date Passed)", s["Overdue Items"], "items", id="overdue", tone="alert",
            hint=f"{s['Overdue Pcs']:,.0f} pcs pending"),
        kpi("Due in Next 3 Days", s["Due ≤ 3 Days"], "items", id="due_soon", hint=f"{soon_pcs:,.0f} pcs pending"),
        kpi("Most Pending", most_pen["Designer"] if most_pen is not None else "None", "", "text", id="most_pending",
            hint=f"{most_pen['Pending']:,.0f} pcs pending" if most_pen is not None else None),
        kpi("Longest Overdue", f"{int(worst['days_overdue'])} days" if worst is not None else "None", "", "text",
            id="longest_overdue", hint=f"{worst['designer']} · {worst['item']}" if worst is not None else None),
    ]
    if vt["required"]:
        kpis.append(kpi("Visits & Meetings Done", f"{vt['done']} / {vt['required']}", "", "text", id="visits_done",
                        hint="Done ÷ required this month"))

    dsc = designer_scorecard(d, x_nd, des_order)
    cols = ["Designer", "Team", "Items", "Target Qty", "Completed", "Pending", "Done %", "Overdue Items",
            "Due ≤ 3 Days", "Nearest Open Due"]
    des_tbl = with_total(dsc[cols], "Designer", pct=("Done %", "Completed", "Target Qty")) if len(dsc) else dsc
    if len(des_tbl):
        des_tbl.loc[des_tbl["Designer"] == "TOTAL", ["Team", "Nearest Open Due"]] = ["", nearest_due(x_nd)]

    x_nt = ff_filter(d, f, skip=("team",))              # team comparison: all teams
    teams = ff_group(x_nt, "team", "Team", [t for t in team_order if t in set(x_nt["team"])])
    if len(teams):
        teams.insert(1, "Designers", teams["Team"].map(x_nt.groupby("team")["designer"].nunique()))
        teams = with_total(teams[["Team", "Designers", "Items", "Target Qty", "Completed", "Pending", "Done %",
                                  "Overdue Items", "Due ≤ 3 Days"]], "Team", pct=("Done %", "Completed", "Target Qty"))
    by_bucket = [{"label": b, "items": int((x["due_bucket"] == b).sum()),
                  "value": float(x.loc[x["due_bucket"] == b, "pending"].sum())} for b in FF_OPEN_BUCKETS]
    st_rows = [{"label": st, "items": int((x["status"] == st).sum()),
                "value": float(x.loc[x["status"] == st, "pending"].sum())} for st in statuses]

    return {
        **base,
        "options": {"designer": des_order, "team": team_order, "status": statuses, "due": FF_DUE_BUCKETS},
        "no_match": bool(x.empty),
        "kpis": kpis,
        "summary": {"items": s["Items"], "target": s["Target Qty"], "completed": s["Completed"],
                    "pending": s["Pending"], "done_pct": s["Done %"], "items_done": s["Items Done"],
                    "overdue_items": s["Overdue Items"], "overdue_pcs": s["Overdue Pcs"],
                    "due_soon": s["Due ≤ 3 Days"], "due_soon_pcs": soon_pcs, "no_due_date": s["No Due Date"],
                    "most_pending": {"designer": most_pen["Designer"], "pending": float(most_pen["Pending"])}
                    if most_pen is not None else None,
                    "longest_overdue": {"designer": worst["designer"], "item": worst["item"],
                                        "days": int(worst["days_overdue"])} if worst is not None else None,
                    "visits": vt},
        "follow_up": follow_up(x),
        "checks": checks(d),
        "tables": {
            "designers": table(des_tbl, FMT, key_col="Target Qty", rates=RATES,
                               note="The Designer filter is not applied here so all designers can be compared; the "
                                    "other filters apply."),
            "items": table(item_rows(x), ITEM_FMT, key_col=None, sort=False),
            "teams": table(teams, FMT, key_col="Target Qty", sort=False, rates=RATES,
                           note="The Team filter is not applied here so all teams can be compared."),
            "outsource": table(item_rows(ff_filter(o, f) if not o.empty else o, "Project / Collection",
                                         "Outsource Vendor"), ITEM_FMT, key_col=None, sort=False),
        },
        "charts": {
            "designers": designer_chart(dsc, x_nd),
            "due_status": [b for b in by_bucket if b["items"]],
            "status": [r for r in st_rows if r["items"] and r["label"] != "Complete"],
        },
    }


def overview_highlights(parsed) -> dict | None:
    """FLO Future block for the Overview page: the same numbers as the FLO Future page with no filters."""
    if not parsed or parsed["samples"].empty:
        return None
    d = parsed["samples"]
    s = ff_stats(d)
    _, des_order, _ = orders(d)
    dsc = designer_scorecard(d, d, des_order)
    soon_pcs = float(d.loc[d["due_bucket"].isin(["Due Today", "Due in 1-3 Days"]), "pending"].sum())
    _, _, _, vt = visits_payload(parsed["visits"], parsed["blocks"])
    worst = d.loc[d["days_overdue"].idxmax()] if d["days_overdue"].max() > 0 else None
    period = period_label(d)
    if s["Overdue Items"]:
        alert = {"kind": "error" if s["Overdue Items"] >= 3 else "warning", "area": "promises",
                 "title": f"{s['Overdue Items']} promised sample{'s' if s['Overdue Items'] != 1 else ''} overdue",
                 "text": f"{s['Done %']:.1f}% of {s['Target Qty']:,.0f} promised pcs completed"
                         f"{' for ' + period if period else ''}. {s['Overdue Pcs']:,.0f} pcs are past their due "
                         f"date; longest: {worst['item']} ({worst['designer']}, {int(worst['days_overdue'])} days). "
                         f"{s['Due ≤ 3 Days']} more due in the next 3 days."}
    else:
        alert = {"kind": "success", "area": "promises", "title": f"{s['Done %']:.1f}% of promises done",
                 "text": f"No promised sample is overdue. {s['Due ≤ 3 Days']} item(s) due in the next 3 days."}
    kpis = [
        kpi("Target Qty (Promised)", s["Target Qty"], "pcs", id="target", hint=f"{s['Items']} items"),
        kpi("Completion %", s["Done %"], "", "pct", id="done_pct",
            hint=f"{s['Completed']:,.0f} of {s['Target Qty']:,.0f} pcs"),
        kpi("Overdue (Date Passed)", s["Overdue Items"], "items", id="overdue", tone="alert",
            hint=f"{s['Overdue Pcs']:,.0f} pcs pending"),
        kpi("Due in Next 3 Days", s["Due ≤ 3 Days"], "items", id="due_soon", hint=f"{soon_pcs:,.0f} pcs pending"),
    ]
    if vt["required"]:
        kpis.append(kpi("Visits & Meetings Done", f"{vt['done']} / {vt['required']}", "", "text", id="visits_done",
                        hint=f"{vt['missed']} missed / not marked" if vt["missed"] else "Done ÷ required"))
    return {"alert": alert, "period": period, "kpis": kpis,
            "designers": [{"label": r["Designer"], "value": float(r["Done %"]), "pending": float(r["Pending"]),
                           "target": float(r["Target Qty"])} for _, r in dsc.iterrows()],
            "urgent": follow_up(d)[:5]}
