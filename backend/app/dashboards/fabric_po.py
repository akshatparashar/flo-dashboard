"""Fabric PO dashboard (source: "INDEX" tab of the FABRIC PO sheet).

Row 1 = header, data below. Columns (A..T):
S.NO | VENDOR NAME | PO NO. | ORDER DATE | DELIVERY DATE | RCVD DATE | DELAY DAYS | ORDER TYPE | CLIENT NAME |
DESIGNER NAME | COLLECTION NAME | STATUS | ACTUAL ORDER QTY. | TOTAL MTR OF FABRIC ORDERED | TOTAL MTR OF FABRIC RCVD |
PENDING | EXCESS | REMARK | TOTAL PC | ITEM

Delivery rule: the vendor gets 15 days from ORDER DATE (DELIVERY DATE column). Fabric received after the delivery
date -> DELAYED. Not yet received and today is past the delivery date -> OVERDUE.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from ..core import clean_delay_days, clean_text, is_number_text, month_label, month_sort_key, norm_key, num, \
    parse_dates, safe_div_pct, today_ist
from ..tables import RATE_APPROVAL, kpi, notice, table

FABPO_LEAD_DAYS = 15     # used only when the DELIVERY DATE cell is blank
FABPO_COLS = {
    "sno": ("SNO", 0), "vendor": ("VENDORNAME", 1), "po": ("PONO", 2), "order_date": ("ORDERDATE", 3),
    "delivery_date": ("DELIVERYDATE", 4), "rcvd_date": ("RCVDDATE", 5), "delay_sheet": ("DELAYDAYS", 6),
    "order_type": ("ORDERTYPE", 7), "client": ("CLIENTNAME", 8), "designer": ("DESIGNERNAME", 9),
    "collection": ("COLLECTIONNAME", 10), "status": ("STATUS", 11), "qty": ("ACTUALORDERQTY", 12),
    "ordered": ("TOTALMTROFFABRICORDERED", 13), "rcvd": ("TOTALMTROFFABRICRCVD", 14),
    "pending": ("PENDING", 15), "total_pc": ("TOTALPC", 18), "item": ("ITEM", 19),
}
FABPO_TIMINGS = ["On Time", "Delayed", "Overdue (Pending)", "Open (Within Deadline)", "No Date", "Cancelled"]
_DATE_IN_TEXT = re.compile(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})")
FILTER_FIELDS = {"month": "month", "vendor": "vendor", "order_type": "order_type", "client": "client",
                 "designer": "designer", "item": "item", "status": "status"}


def parse_rcvd_cell(v):
    """RCVD DATE cell -> list of dates. Handles one date, serial numbers and part-lots like '24/04/2026+15/05/2026'."""
    if v is None:
        return []
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        if 20000 <= float(v) <= 80000:
            return [pd.Timestamp("1899-12-30") + pd.Timedelta(days=float(v))]
        return []
    text = re.sub(r"\s+", "", str(v))
    if not text:
        return []
    out = []
    for d, m, y in _DATE_IN_TEXT.findall(text):
        yr = int(y) + (2000 if int(y) < 100 else 0)
        try:
            out.append(pd.Timestamp(year=yr, month=int(m), day=int(d)))
        except ValueError:
            continue
    if not out:
        one = parse_dates(pd.Series([v])).iloc[0]
        if pd.notna(one):
            out = [one]
    return [d.normalize() for d in out]


def _fabpo_header_row(grid):
    for r in range(min(8, len(grid))):
        keys = {norm_key(c) for c in grid[r]}
        if "VENDORNAME" in keys or ("PONO" in keys and "ORDERDATE" in keys):
            return r
    return 0


def _fabpo_col_map(header):
    keys = [norm_key(h) for h in header]
    out = {}
    for field, (name, pos) in FABPO_COLS.items():
        idx = keys.index(name) if name in keys else next((i for i, k in enumerate(keys) if k.startswith(name)), None)
        out[field] = idx if idx is not None else pos
    return out


def build_fabric_po(values, today=None):
    """Raw INDEX grid (unformatted) -> clean one-row-per-PO DataFrame. Returns (df, header_row_cells)."""
    if not values:
        return pd.DataFrame(), []
    hr = _fabpo_header_row(values)
    header = values[hr]
    cmap = _fabpo_col_map(header)
    rows = values[hr + 1:]
    if not rows:
        return pd.DataFrame(), header
    width = max(max(len(r) for r in rows), max(cmap.values()) + 1)
    grid = pd.DataFrame([list(r) + [""] * (width - len(r)) for r in rows])

    def col(field):
        return grid[cmap[field]].reset_index(drop=True)

    vendor_raw = col("vendor")
    vendor_txt = clean_text(vendor_raw)
    po_txt = clean_text(col("po"))
    sno_ok = num(col("sno")) > 0
    bad_vendor = (vendor_txt == "") | vendor_txt.map(is_number_text) | \
        vendor_txt.str.match(r"^\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}$") | vendor_txt.str.upper().str.startswith("TOTAL")
    keep = (~bad_vendor) & (sno_ok | (po_txt != ""))     # drops the helper date row, blanks and TOTAL rows

    d = pd.DataFrame({"vendor": vendor_txt.str.upper(), "po": po_txt})
    for f in ("order_type", "client", "designer", "collection", "status", "item"):
        t = clean_text(col(f)).str.upper()
        d[f] = t.where(t != "", "(BLANK)")
    d["order_date"] = parse_dates(col("order_date"))
    d["delivery_date"] = parse_dates(col("delivery_date"))
    for f in ("qty", "ordered", "rcvd", "pending", "total_pc"):
        d[f] = num(col(f))
    d["sheet_delay"] = clean_delay_days(col("delay_sheet")).clip(lower=0)
    rcvd_lists = col("rcvd_date").map(parse_rcvd_cell)
    d["last_rcvd"] = pd.to_datetime(rcvd_lists.map(lambda L: max(L) if L else pd.NaT))
    d["rcvd_text"] = rcvd_lists.map(lambda L: " + ".join(x.strftime("%d/%m/%Y") for x in sorted(L)))
    d = d[keep.values].reset_index(drop=True)
    if d.empty:
        return d, header

    # --- delivery due date: sheet DELIVERY DATE, else ORDER DATE + 15 days
    due = d["delivery_date"].copy()
    fill = due.isna() & d["order_date"].notna()
    due[fill] = d.loc[fill, "order_date"] + pd.Timedelta(days=FABPO_LEAD_DAYS)
    d["due"] = due

    # --- fulfilment class from STATUS (falls back to pending / received meters when status is blank)
    sn = d["status"].map(norm_key)
    blank_recv = (d["status"] == "(BLANK)") & (d["pending"] <= 0) & (d["rcvd"] > 0)
    d["fulfil"] = np.select(
        [sn.str.contains("CANCEL"), sn.str.contains("PART"),
         sn.str.contains("PEND|NOTR|WAIT|TRANSIT|PROCESS"),
         sn.str.contains("RCVD|RECEIVED|RECD|COMPLETE|DELIVERED") | blank_recv],
        ["Cancelled", "Partial", "Pending", "Received"], default="Pending")
    recv = d["fulfil"] == "Received"
    openpo = d["fulfil"].isin(["Pending", "Partial"])

    # --- delay days
    today = today if today is not None else today_ist()
    has_dates = d["last_rcvd"].notna() & d["due"].notna()
    delay = pd.Series(0.0, index=d.index)
    m1 = recv & has_dates
    delay[m1] = (d.loc[m1, "last_rcvd"] - d.loc[m1, "due"]).dt.days
    m2 = openpo & d["due"].notna()
    delay[m2] = (today - d.loc[m2, "due"]).dt.days
    m3 = recv & ~has_dates
    delay[m3] = d.loc[m3, "sheet_delay"]
    d["delay_days"] = delay.clip(lower=0).fillna(0).astype(int)

    d["timing"] = np.select(
        [d["fulfil"] == "Cancelled", recv & (d["delay_days"] > 0), recv & ~has_dates & (d["sheet_delay"] <= 0),
         recv, openpo & (d["delay_days"] > 0)],
        ["Cancelled", "Delayed", "No Date", "On Time", "Overdue (Pending)"], default="Open (Within Deadline)")
    d["is_late"] = (d["delay_days"] > 0).astype(int)
    d["is_recv"] = recv.astype(int)
    d["is_ontime"] = (d["timing"] == "On Time").astype(int)
    d["month"] = month_label(d["order_date"])
    d["days_to_due"] = np.where(openpo & d["due"].notna(), (d["due"] - today).dt.days, np.nan)
    return d, header


def fabpo_stats(x):
    """One summary row for any slice of POs."""
    ordered, rcvd = float(x["ordered"].sum()), float(x["rcvd"].sum())
    late = int(x["is_late"].sum())
    recv_n = int(x["is_recv"].sum())
    return {
        "POs": int(len(x)),
        "Fabric Ordered (mtr)": ordered,
        "Fabric Rcvd (mtr)": rcvd,
        "Pending (mtr)": float(x["pending"].sum()),
        "RCVD %": safe_div_pct(rcvd, ordered),
        "Total Pcs": float(x["total_pc"].sum()),
        "Delayed POs": late,
        "Avg Delay (days)": (float(x["delay_days"].sum()) / late) if late else 0.0,
        "On-Time %": safe_div_pct(int(x["is_ontime"].sum()), recv_n),
    }


def fabpo_group(x, col, label, order_by="Fabric Ordered (mtr)", total=True):
    rows = [{label: k, **fabpo_stats(g)} for k, g in x.groupby(col, sort=False)]
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).sort_values(order_by, ascending=False).reset_index(drop=True)
    if total:
        df = pd.concat([df, pd.DataFrame([{label: "TOTAL", **fabpo_stats(x)}])], ignore_index=True)
    return df


FPO_FMT = {"Fabric Ordered (mtr)": "dec", "Fabric Rcvd (mtr)": "dec", "Pending (mtr)": "dec",
           "Avg Delay (days)": "dec", "RCVD %": "pct", "On-Time %": "pct"}


def fpo_date(s):
    return s.dt.strftime("%d/%m/%Y").fillna("")


def parse_fabric_po(values, today=None):
    d, header = build_fabric_po(values, today)
    return {"d": d, "header": header}


def filter_po(d, f):
    x = d
    for field, col in FILTER_FIELDS.items():
        sel = f.get(field) or []
        if sel:
            x = x[x[col].isin(sel)]
    return x


def overdue_list(x, limit=15):
    op = x[x["timing"] == "Overdue (Pending)"].sort_values("delay_days", ascending=False)
    head = op.head(limit)
    tbl = pd.DataFrame({"PO No.": head["po"].values, "Vendor": head["vendor"].values,
                        "Order Date": fpo_date(head["order_date"]).values, "Due Date": fpo_date(head["due"]).values,
                        "Days Overdue": head["delay_days"].astype(float).values,
                        "Pending (mtr)": head["pending"].values, "Status": head["status"].values})
    return op, tbl


def fabric_po_dashboard(parsed, f):
    d = parsed["d"]
    if d.empty:
        return {"empty": True, "options": {k: [] for k in FILTER_FIELDS},
                "notices": [notice("No Fabric PO data found. Expected an 'INDEX' tab with a header row (VENDOR NAME, "
                                   "PO NO., ORDER DATE, DELIVERY DATE, RCVD DATE ...) and PO rows below it.", "warning")]}

    def opts(c):
        return sorted(v for v in d[c].unique() if v)

    options = {"month": sorted(d["month"].unique(), key=month_sort_key), "vendor": opts("vendor"),
               "order_type": opts("order_type"), "client": opts("client"), "designer": opts("designer"),
               "item": opts("item"), "status": opts("status")}
    x = filter_po(d, f)
    rule = (f"Delivery rule: {FABPO_LEAD_DAYS} days from the order date (the sheet's DELIVERY DATE column). Fabric "
            "received after that date counts as delayed; not yet received and past the date counts as overdue. For "
            "part lots (e.g. 24/04/2026+15/05/2026) the last date counts.")
    if x.empty:
        return {"options": options, "rule": rule, "empty_filtered": True,
                "notices": [notice("No POs match the selected filters.")]}

    s = fabpo_stats(x)
    overdue_po, overdue_tbl = overdue_list(x)
    worst = x.loc[x["delay_days"].idxmax()]
    worst_txt = f"{int(worst['delay_days'])} days" if worst["delay_days"] > 0 else "None"

    mon = x.groupby("month").agg(ordered=("ordered", "sum"), rcvd=("rcvd", "sum"), pending=("pending", "sum"),
                                 pcs=("total_pc", "sum")).reindex(sorted(x["month"].unique(), key=month_sort_key))
    mrows = [{"Month": m, **fabpo_stats(x[x["month"] == m])} for m in mon.index]
    mtbl = pd.DataFrame(mrows)[["Month", "POs", "Fabric Ordered (mtr)", "Fabric Rcvd (mtr)", "Pending (mtr)",
                                "RCVD %", "Total Pcs"]]
    mtbl = pd.concat([mtbl, pd.DataFrame([{"Month": "TOTAL", **{k: s[k] for k in mtbl.columns[1:]}}])],
                     ignore_index=True)

    vend = fabpo_group(x, "vendor", "Vendor")
    vv = vend[vend["Vendor"] != "TOTAL"]
    o = vv.sort_values("Fabric Ordered (mtr)", ascending=False)
    share = vv[vv["Fabric Ordered (mtr)"] > 0].sort_values("Fabric Ordered (mtr)", ascending=False)
    stbl = None
    if not share.empty:
        stbl = share[["Vendor", "Fabric Ordered (mtr)"]].copy()
        stbl["Share %"] = stbl["Fabric Ordered (mtr)"] / stbl["Fabric Ordered (mtr)"].sum() * 100
        from ..tables import with_total
        stbl = with_total(stbl, "Vendor", pct=("Share %", "Fabric Ordered (mtr)", "Fabric Ordered (mtr)"))
    ot = x["order_type"].value_counts()
    tm = x["timing"].value_counts()

    po_rows = x.sort_values(["delay_days"], ascending=False)
    po_list = pd.DataFrame({"PO No.": po_rows["po"].values, "Vendor": po_rows["vendor"].values,
                            "Item": po_rows["item"].values, "Order Date": fpo_date(po_rows["order_date"]).values,
                            "Due Date": fpo_date(po_rows["due"]).values, "Received On": po_rows["rcvd_text"].values,
                            "Timing": po_rows["timing"].values, "Days Late": po_rows["delay_days"].astype(float).values,
                            "Ordered (mtr)": po_rows["ordered"].values, "Pending (mtr)": po_rows["pending"].values})
    return {
        "options": options,
        "rule": rule,
        "notices": [],
        "kpis": [
            kpi("Total POs", s["POs"], "POs", id="pos"),
            kpi("Fabric ordered", s["Fabric Ordered (mtr)"], "mtr", id="ordered"),
            kpi("Fabric received", s["Fabric Rcvd (mtr)"], "mtr", id="received", tone="good"),
            kpi("Pending fabric", s["Pending (mtr)"], "mtr", id="pending", tone="alert"),
            kpi("Received rate", s["RCVD %"], "", "pct", id="received_pct"),
            kpi("Total pcs", s["Total Pcs"], "pcs", id="pcs"),
            kpi("Delayed POs", s["Delayed POs"], "POs", id="delayed"),
            kpi("Overdue, not received", len(overdue_po), "POs", id="overdue", tone="alert"),
            kpi("On-time delivery", s["On-Time %"], "", "pct", id="ontime_pct"),
            kpi("Avg delay", s["Avg Delay (days)"], "days", "dec1", id="avg_delay"),
            kpi("Longest delay", worst_txt, "", "text", id="longest",
                hint=f"PO {worst['po']} · {worst['vendor']}" if worst["delay_days"] > 0 else None),
        ],
        "tables": {
            "monthly": table(mtbl, FPO_FMT, key_col="Fabric Ordered (mtr)", sort=False),
            "vendors": table(vend, FPO_FMT, key_col="Fabric Ordered (mtr)",
                             rates={"RCVD %": RATE_APPROVAL, "On-Time %": RATE_APPROVAL}),
            "vendor_share": table(stbl, {"Share %": "pct", "Fabric Ordered (mtr)": "dec"},
                                  key_col="Fabric Ordered (mtr)") if stbl is not None else table(None),
            "overdue": table(overdue_tbl, {"Pending (mtr)": "dec"}, key_col="Days Overdue"),
            "pos": table(po_list, {"Ordered (mtr)": "dec", "Pending (mtr)": "dec"}, key_col="Days Late"),
        },
        "overdue_total": int(len(overdue_po)),
        "charts": {
            "monthly": {"categories": list(mon.index), "series": [
                {"name": "Ordered", "values": [float(v) for v in mon["ordered"]]},
                {"name": "Received", "values": [float(v) for v in mon["rcvd"]]},
                {"name": "Pending", "values": [float(v) for v in mon["pending"]]}]},
            "order_type": [{"label": str(k), "value": float(v)} for k, v in ot.items()],
            "vendors": {"categories": list(o["Vendor"]), "series": [
                {"name": "Received", "values": [float(v) for v in o["Fabric Rcvd (mtr)"]]},
                {"name": "Pending", "values": [float(v) for v in o["Pending (mtr)"]]}]},
            "vendor_share": [{"label": r["Vendor"], "value": float(r["Fabric Ordered (mtr)"])}
                             for _, r in share.iterrows()],
            "timing": [{"label": str(k), "value": float(v)} for k, v in tm.items()],
        },
    }
