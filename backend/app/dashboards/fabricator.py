"""Fabricator stock dashboard (mirrors the "FABRICATOR DASHBOARD" Apps Script).

Source tab: MONTHWISE SUMMARY -> blocks titled "Position Of Stock <NAME>". Each block: a "Month" header row,
then 12 rows April..March with 5 value columns to the right of Month:
Fabric Issue (mtr) | Pcs Under Production | RCVD | Remaining | Monthly Incoming
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from ..core import FY_MONTH_LABELS, FY_MONTH_SHORT, safe_div_pct, to_num
from ..tables import RATE_APPROVAL, kpi, notice, table, with_total

FAB_METRICS = ["Fabric Issue (mtr)", "Pcs Under Production", "RCVD (Pcs)", "Remaining (Pcs)", "Monthly Incoming (Pcs)"]
DEFAULT_METRIC = "Fabric Issue (mtr)"


def detect_fab_blocks(disp):
    blocks, used = [], {}
    for r, row in enumerate(disp):
        for c, cell in enumerate(row):
            m = re.match(r"^position\s+of\s+stock\s*(.*)$", str(cell).strip(), re.I)
            if not m:
                continue
            hdr = -1
            for rr in range(r, min(r + 7, len(disp))):
                if c < len(disp[rr]) and re.fullmatch(r"month", str(disp[rr][c]).strip(), re.I):
                    hdr = rr
                    break
            if hdr < 0:
                continue
            first = -1
            for rr in range(hdr + 1, min(hdr + 7, len(disp))):
                if c < len(disp[rr]) and re.match(r"apr", str(disp[rr][c]).strip(), re.I):
                    first = rr
                    break
            if first < 0:
                continue
            raw = re.sub(r"[()]", "", m.group(1)).strip().upper()
            raw = re.sub(r"^[\s:\-–]+", "", raw).strip()
            is_all = bool(re.search(r"ALL\s*OVER", raw))
            name = "ALL OVER" if is_all else (raw or "BLOCK")
            if name in used:
                used[name] += 1
                name = f"{name} ({used[name]})"
            else:
                used[name] = 1
            blocks.append({"name": name, "is_all": is_all, "title_row": r, "first_row": first, "col": c,
                           "title": str(cell).strip()})
    return blocks


def _cell(grid, r, c):
    if r < len(grid) and c < len(grid[r]):
        return grid[r][c]
    return ""


def build_fab_data(disp, raw):
    blocks = detect_fab_blocks(disp)
    recs = []
    for b in blocks:
        for k in range(12):
            vals = [to_num(_cell(raw, b["first_row"] + k, b["col"] + f)) for f in range(1, 6)]
            rec = {"Fabricator": b["name"], "is_all": b["is_all"], "Month": FY_MONTH_LABELS[k]}
            rec.update(dict(zip(FAB_METRICS, vals)))
            recs.append(rec)
    return blocks, pd.DataFrame(recs)


def parse_fabricator(disp, raw):
    blocks, df = build_fab_data(disp, raw)
    return {"blocks": blocks, "df": df}


def split_base(df):
    """(fabricator rows, ALL OVER rows, fabricator names). Falls back to ALL OVER when no fabricator blocks."""
    all_over = df[df["is_all"]]
    fabs_df = df[~df["is_all"]]
    base = fabs_df if not fabs_df.empty else all_over
    return base, all_over, list(dict.fromkeys(base["Fabricator"]))


def _rcvd_pct(frame):
    frame["RCVD %"] = np.where(frame["Pcs Under Production"] > 0,
                               frame["RCVD (Pcs)"] / frame["Pcs Under Production"].replace(0, np.nan) * 100, 0.0)
    return frame


FMT = {"RCVD %": "pct", "Fabric Issue (mtr)": "dec"}
RATES = {"RCVD %": RATE_APPROVAL}


def fabricator_dashboard(parsed, f):
    df = parsed["df"]
    if df.empty:
        return {"empty": True, "options": {"fabricator": [], "month": FY_MONTH_LABELS, "metric": FAB_METRICS},
                "notices": [notice("No 'Position Of Stock ...' tables found (each needs a 'Month' header under the "
                                   "title and 12 rows starting with April).", "error")]}
    metric = f.get("metric") or DEFAULT_METRIC
    if metric not in FAB_METRICS:
        metric = DEFAULT_METRIC
    base, all_over, fab_names = split_base(df)
    sel_fab, sel_month = f.get("fabricator") or [], f.get("month") or []

    def flt(frame, fabs=True, months=True):
        y = frame
        if fabs and sel_fab:
            y = y[y["Fabricator"].isin(sel_fab)]
        if months and sel_month:
            y = y[y["Month"].isin(sel_month)]
        return y

    x = flt(base)                                  # KPIs, matrix
    x_by_month = flt(base, months=False)           # monthly table/charts ignore the month filter
    x_by_fab = flt(base, fabs=False)               # scorecard compares all fabricators
    ao_f = flt(all_over, fabs=False)

    tot = x[FAB_METRICS].sum()
    recv_pct = safe_div_pct(tot["RCVD (Pcs)"], tot["Pcs Under Production"])
    g = x.groupby("Fabricator")[FAB_METRICS].sum()

    def top_of(col):
        if len(g) and g[col].max() > 0:
            return str(g[col].idxmax()), float(g[col].max())
        return None, 0.0

    top_rcv, top_rem = top_of("RCVD (Pcs)"), top_of("Remaining (Pcs)")
    notices = []
    if tot[FAB_METRICS].abs().sum() == 0:
        notices.append(notice("No data for the selected filters."))

    mm = x_by_month.groupby("Month")[FAB_METRICS].sum().reindex(FY_MONTH_LABELS, fill_value=0).astype(float)
    mm = _rcvd_pct(mm)
    mm.index.name = "Month"
    monthly = mm.reset_index()

    sc = _rcvd_pct(x_by_fab.groupby("Fabricator", sort=False)[FAB_METRICS].sum().astype(float))
    sc.index.name = "Fabricator"
    score = sc.reset_index()

    shown = with_total(score, "Fabricator", pct=("RCVD %", "RCVD (Pcs)", "Pcs Under Production"))
    if not ao_f.empty:
        ao_sum = ao_f[FAB_METRICS].sum()
        ao_row = {"Fabricator": "ALL OVER (SHEET)", **{k: float(ao_sum[k]) for k in FAB_METRICS},
                  "RCVD %": safe_div_pct(ao_sum["RCVD (Pcs)"], ao_sum["Pcs Under Production"])}
        shown = pd.concat([shown, pd.DataFrame([ao_row])], ignore_index=True)
        diff = float((score[FAB_METRICS].sum() - ao_f[FAB_METRICS].sum()).abs().sum())
        check = notice("Fabricator totals match the sheet's ALL OVER table.", "success") if diff < 1 else \
            notice(f"Fabricator totals differ from the ALL OVER table by {diff:,.0f}. A fabricator table may be "
                   "missing from the summary.", "warning")
    else:
        check = notice("No ALL OVER table found on the sheet, so the totals could not be cross-checked.")

    xm = flt(base, months=False)
    matrix = None
    if not xm.empty:
        mat = (xm.groupby(["Fabricator", "Month"])[metric].sum().unstack(fill_value=0)
               .reindex(index=[n for n in fab_names if n in set(xm["Fabricator"])], columns=FY_MONTH_LABELS,
                        fill_value=0))
        mat.columns = FY_MONTH_SHORT
        tbl = mat.copy()
        tbl["TOTAL"] = tbl.sum(axis=1)
        tbl.index.name = "Fabricator"
        tbl = with_total(tbl.reset_index(), "Fabricator", label="ALL FABRICATORS")
        dec = {c: "dec" for c in ("TOTAL", *FY_MONTH_SHORT)} if metric.startswith("Fabric") else {}
        matrix = {
            "table": table(tbl, dec, key_col="TOTAL"),
            "heatmap": {"rows": list(mat.index), "columns": FY_MONTH_SHORT,
                        "values": [[float(v) for v in row] for row in mat.to_numpy()]},
        }

    by_rcvd = score.sort_values("RCVD (Pcs)")
    by_pct = score.sort_values("RCVD %")
    return {
        "options": {"fabricator": fab_names, "month": FY_MONTH_LABELS, "metric": FAB_METRICS},
        "metric": metric,
        "notices": notices,
        "kpis": [
            kpi("Fabric issued", tot["Fabric Issue (mtr)"], "mtr", id="fabric"),
            kpi("Pcs under production", tot["Pcs Under Production"], "pcs", id="production"),
            kpi("Received", tot["RCVD (Pcs)"], "pcs", id="received", tone="good"),
            kpi("Remaining", tot["Remaining (Pcs)"], "pcs", id="remaining", tone="alert"),
            kpi("Monthly incoming", tot["Monthly Incoming (Pcs)"], "pcs", id="incoming"),
            kpi("Received rate", recv_pct, "", "pct", id="received_pct"),
            kpi("Top receiver", top_rcv[0] or "—", "", "text", id="top_receiver",
                hint=f"{top_rcv[1]:,.0f} pcs" if top_rcv[0] else None),
            kpi("Most pending", top_rem[0] or "—", "", "text", id="most_pending", tone="alert",
                hint=f"{top_rem[1]:,.0f} pcs" if top_rem[0] else None),
        ],
        "tables": {
            "monthly": table(with_total(monthly, "Month", pct=("RCVD %", "RCVD (Pcs)", "Pcs Under Production")), FMT,
                             key_col="Pcs Under Production", sort=False, rates=RATES,
                             note="The month filter is not applied here; the full year is shown."),
            "scorecard": table(shown, FMT, key_col="Pcs Under Production", rates=RATES,
                               note="The fabricator filter is not applied here so all fabricators can be compared."),
        },
        "check": check,
        "matrix": matrix,
        "charts": {
            "monthly": {"categories": FY_MONTH_LABELS, "series": [
                {"name": "Under production", "values": [float(v) for v in mm["Pcs Under Production"]]},
                {"name": "Received", "values": [float(v) for v in mm["RCVD (Pcs)"]]},
                {"name": "Remaining", "values": [float(v) for v in mm["Remaining (Pcs)"]]}]},
            "issue_incoming": {"categories": FY_MONTH_LABELS, "series": [
                {"name": "Fabric issue (mtr)", "values": [float(v) for v in mm["Fabric Issue (mtr)"]], "axis": "left"},
                {"name": "Monthly incoming (pcs)", "values": [float(v) for v in mm["Monthly Incoming (Pcs)"]],
                 "axis": "right"}]},
            "rcvd_vs_remaining": {"categories": list(by_rcvd["Fabricator"]), "series": [
                {"name": "Received", "values": [float(v) for v in by_rcvd["RCVD (Pcs)"]]},
                {"name": "Remaining", "values": [float(v) for v in by_rcvd["Remaining (Pcs)"]]}]},
            "received_pct": [{"label": r["Fabricator"], "value": float(r["RCVD %"])} for _, r in by_pct.iterrows()],
        },
    }
