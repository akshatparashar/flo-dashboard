"""Management overview: one page across Orders / Production (Master Sheet), Samples, Fabricator stock and Fabric
PO. Every number reuses the calculation of the individual dashboards, so they always match.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..core import FY_MONTH_LABELS, fmt, safe_div_pct
from ..tables import RATE_APPROVAL, kpi, notice, table, with_total
from . import fabric_po as fpo
from . import fabricator as fab
from . import flo_future as ffu
from . import master as mst
from . import samples as smp

ORDER_STAT_COLS = ["Designs", "Order Qty", "In Production", "Received", "Pending", "Overdue Pcs",
                   "Avg Overdue Days", "On-Time %"]
SHORT_COLS = ["Order Qty", "In Production", "Received", "Pending", "Overdue Pcs"]


def ovw_group(x, col, label, stats_fn, cols=None):
    """One row per group (+ TOTAL row computed on the whole slice, so averages / % are never summed)."""
    rows = [{label: k, **stats_fn(g)} for k, g in x.groupby(col, sort=False)]
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    num_cols = [c for c in df.columns if c != label]
    df = df[(df[num_cols].abs().sum(axis=1) > 0)]
    df = pd.concat([df, pd.DataFrame([{label: "TOTAL", **stats_fn(x)}])], ignore_index=True)
    return df[[label] + cols] if cols else df


def _top(df, label, col):
    """(name, value) of the biggest row (TOTAL ignored)."""
    if df is None or df.empty:
        return None, 0.0
    b = df[df[label] != "TOTAL"]
    if b.empty or b[col].max() <= 0:
        return None, 0.0
    r = b.loc[b[col].idxmax()]
    return r[label], float(r[col])


def _pcs(v):
    return f"{fmt(v)} pcs"


def po_stats(g):
    s = fpo.fabpo_stats(g)
    return {"POs": s["POs"], "Fabric Ordered (mtr)": s["Fabric Ordered (mtr)"],
            "Pending (mtr)": s["Pending (mtr)"], "RCVD %": s["RCVD %"],
            "Overdue POs": int((g["timing"] == "Overdue (Pending)").sum()), "Delayed POs": s["Delayed POs"],
            "Avg Delay (days)": s["Avg Delay (days)"], "On-Time %": s["On-Time %"]}


def overview_dashboard(sources, months):
    """sources: {"tracker": (d_all|None, err), "sample_summary": (parsed|None, err),
                 "overview_fabricators": (parsed|None, err), "fabric_po": (parsed|None, err)}"""
    months = list(months or [])

    def by_month(df, col):
        if df is None or df.empty or not months:
            return df
        return df[df[col].isin(months)]

    master, m_err = sources["tracker"]
    smp_p, s_err = sources["sample_summary"]
    fab_p, f_err = sources["overview_fabricators"]
    po_p, p_err = sources["fabric_po"]
    ff_p, ff_err = sources.get("flo_future", (None, None))
    smp_d = smp_p["d"] if smp_p else None
    fab_d = fab_p["df"] if fab_p else None
    po_d = po_p["d"] if po_p else None

    xm = by_month(master, "month")
    xs = by_month(smp_d, "month")
    if fab_d is not None and not fab_d.empty:
        fab_base = fab_d[~fab_d["is_all"]] if (~fab_d["is_all"]).any() else fab_d[fab_d["is_all"]]
        xf = by_month(fab_base, "Month")
    else:
        xf = None
    xp = by_month(po_d, "month")

    alerts, errors, sections = [], [], {}
    for label, err in (("Master Sheet", m_err), ("Sample Summary", s_err), ("Fabricator Report", f_err),
                       ("Fabric PO", p_err), ("FLO Future", ff_err)):
        if err:
            errors.append(notice(f"{label} could not be loaded: {err}", "error"))

    # ---- Orders & production (Master Sheet) ----
    if xm is not None:
        ok = mst.overview_order_stats(xm)
        dk = mst.designer_kpi_values(xm)
        by_fab = ovw_group(xm, "fabricator", "Fabricator", mst.overview_order_stats, ORDER_STAT_COLS)
        by_cat = ovw_group(xm, "category", "Category", mst.overview_order_stats, SHORT_COLS)
        by_cli = ovw_group(xm, "client", "Client", mst.overview_order_stats, SHORT_COLS)
        n_overdue = int(((xm["production"] > 0) & (xm["delay"] > 0)).sum())
        if ok["Pending"] > 0:
            parts = []
            for lbl, df in (("Fabricator", by_fab), ("Category", by_cat), ("Client", by_cli)):
                name, val = _top(df, lbl, "Pending")
                if name is not None:
                    parts.append({"dimension": lbl, "name": name, "value": val})
            alerts.append({"kind": "warning", "area": "orders",
                           "title": f"{_pcs(ok['Pending'])} pending",
                           "text": f"{_pcs(ok['Pending'])} pending of {_pcs(ok['In Production'])} in production "
                                   f"({safe_div_pct(ok['Pending'], ok['In Production']):.1f}%).",
                           "top": parts})
        if ok["Overdue Pcs"] > 0:
            alerts.append({"kind": "error" if ok["On-Time %"] < 50 else "warning", "area": "overdue",
                           "title": f"{_pcs(ok['Overdue Pcs'])} overdue",
                           "text": f"{_pcs(ok['Overdue Pcs'])} across {n_overdue:,} designs, on average "
                                   f"{ok['Avg Overdue Days']:.1f} days late. On-time delivery "
                                   f"{ok['On-Time %']:.1f}%."})
        elif ok["In Production"] > 0:
            alerts.append({"kind": "success", "area": "overdue", "title": "Nothing overdue",
                           "text": "No design in production is past its delivery date."})

        axis = [m for m in mst.month_list(master) if (not months or m in months)]
        mm = xm.groupby("month")[["received", "pending"]].sum().reindex(axis, fill_value=0)
        mm = mm[(mm.sum(axis=1) > 0) | mm.index.isin(FY_MONTH_LABELS)]
        fb = by_fab[by_fab["Fabricator"] != "TOTAL"].sort_values("Pending") if not by_fab.empty else by_fab
        sections["orders"] = {
            "kpis": [
                kpi("Total designs", dk["designs"], "", id="designs"),
                kpi("Order qty", ok["Order Qty"], "pcs", id="qty"),
                kpi("New / repeat", f"{fmt(dk['new_qty'])} / {fmt(dk['repeat_qty'])}", "pcs", "text", id="new_repeat"),
                kpi("In production", ok["In Production"], "pcs", id="production"),
                kpi("Received", ok["Received"], "pcs", id="received", tone="good"),
                kpi("Pending", ok["Pending"], "pcs", id="pending", tone="alert"),
                kpi("Overdue pcs", ok["Overdue Pcs"], "pcs", id="overdue", tone="alert"),
                kpi("On-time delivery", ok["On-Time %"], "", "pct", id="ontime"),
                kpi("Avg overdue", ok["Avg Overdue Days"], "days", "dec1", id="avg_overdue"),
            ],
            "stats": ok,
            "tables": {
                "fabricators": table(by_fab, {"On-Time %": "pct", "Avg Overdue Days": "dec"}, key_col="Pending",
                                     rates={"On-Time %": RATE_APPROVAL}),
                "categories": table(by_cat, key_col="Pending"),
                "clients": table(by_cli, key_col="Pending"),
            },
            "charts": {
                "monthly": {"categories": list(mm.index), "series": [
                    {"name": "Received", "values": [float(v) for v in mm["received"]]},
                    {"name": "Pending", "values": [float(v) for v in mm["pending"]]}]},
                "fabricators": {"categories": list(fb["Fabricator"]) if not fb.empty else [], "series": [
                    {"name": "Received", "values": [float(v) for v in fb["Received"]] if not fb.empty else []},
                    {"name": "Pending", "values": [float(v) for v in fb["Pending"]] if not fb.empty else []}]},
            },
        }

    # ---- Fabricator stock ----
    if xf is not None:
        ft = xf[fab.FAB_METRICS].sum()
        f_pct = safe_div_pct(ft["RCVD (Pcs)"], ft["Pcs Under Production"])
        fg = xf.groupby("Fabricator", sort=False)[["Pcs Under Production", "RCVD (Pcs)", "Remaining (Pcs)"]].sum()
        fg = fg[fg.abs().sum(axis=1) > 0]
        fg["RCVD %"] = np.where(fg["Pcs Under Production"] > 0,
                                fg["RCVD (Pcs)"] / fg["Pcs Under Production"].replace(0, np.nan) * 100, 0.0)
        fg.index.name = "Fabricator"
        fab_tbl = with_total(fg.reset_index(), "Fabricator", pct=("RCVD %", "RCVD (Pcs)", "Pcs Under Production"))
        name, val = _top(fab_tbl, "Fabricator", "Remaining (Pcs)")
        if ft["Remaining (Pcs)"] > 0:
            alerts.append({"kind": "warning", "area": "stock",
                           "title": f"{_pcs(ft['Remaining (Pcs)'])} with fabricators",
                           "text": f"{_pcs(ft['Remaining (Pcs)'])} remaining ({f_pct:.1f}% received)."
                                   + (f" Most pending: {name} ({fmt(val)})." if name else "")})
        o = fab_tbl[fab_tbl["Fabricator"] != "TOTAL"].sort_values("Remaining (Pcs)") if not fab_tbl.empty else fab_tbl
        sections["stock"] = {
            "kpis": [
                kpi("Fabric issued", ft["Fabric Issue (mtr)"], "mtr", id="fabric"),
                kpi("Pcs under production", ft["Pcs Under Production"], "pcs", id="production"),
                kpi("Received", ft["RCVD (Pcs)"], "pcs", id="received", tone="good"),
                kpi("Remaining", ft["Remaining (Pcs)"], "pcs", id="remaining", tone="alert"),
                kpi("Received rate", f_pct, "", "pct", id="received_pct"),
                kpi("Monthly incoming", ft["Monthly Incoming (Pcs)"], "pcs", id="incoming"),
            ],
            "table": table(fab_tbl, {"RCVD %": "pct"}, key_col="Remaining (Pcs)", rates={"RCVD %": RATE_APPROVAL}),
            "chart": {"categories": list(o["Fabricator"]) if not o.empty else [], "series": [
                {"name": "Received", "values": [float(v) for v in o["RCVD (Pcs)"]] if not o.empty else []},
                {"name": "Remaining", "values": [float(v) for v in o["Remaining (Pcs)"]] if not o.empty else []}]},
        }

    # ---- Fabric PO ----
    if xp is not None and not xp.empty:
        ps = fpo.fabpo_stats(xp)
        overdue_po, op_tbl = fpo.overdue_list(xp)
        if len(overdue_po):
            od = xp[xp["timing"] == "Overdue (Pending)"]
            w = od.loc[od["delay_days"].idxmax()]
            alerts.append({"kind": "error", "area": "po", "title": f"{len(overdue_po):,} POs overdue",
                           "text": f"{len(overdue_po):,} fabric POs are past due and not yet received; "
                                   f"{fmt(ps['Pending (mtr)'])} mtr pending. Longest: {int(w['delay_days'])} days, "
                                   f"PO {w['po']} ({w['vendor']})."})
        else:
            alerts.append({"kind": "success", "area": "po", "title": "No overdue POs",
                           "text": f"No fabric PO is overdue. {fmt(ps['Pending (mtr)'])} mtr pending."})
        vend = ovw_group(xp, "vendor", "Vendor", po_stats)
        tm = xp["timing"].value_counts()
        sections["po"] = {
            "kpis": [
                kpi("Total POs", ps["POs"], "POs", id="pos"),
                kpi("Fabric ordered", ps["Fabric Ordered (mtr)"], "mtr", id="ordered"),
                kpi("Fabric received", ps["Fabric Rcvd (mtr)"], "mtr", id="received", tone="good"),
                kpi("Pending fabric", ps["Pending (mtr)"], "mtr", id="pending", tone="alert"),
                kpi("Received rate", ps["RCVD %"], "", "pct", id="received_pct"),
                kpi("Overdue, not received", len(overdue_po), "POs", id="overdue", tone="alert"),
                kpi("Delayed POs", ps["Delayed POs"], "POs", id="delayed"),
                kpi("On-time delivery", ps["On-Time %"], "", "pct", id="ontime"),
            ],
            "tables": {
                "vendors": table(vend, {"RCVD %": "pct", "On-Time %": "pct", "Fabric Ordered (mtr)": "dec",
                                        "Pending (mtr)": "dec", "Avg Delay (days)": "dec"}, key_col="Pending (mtr)",
                                 rates={"RCVD %": RATE_APPROVAL, "On-Time %": RATE_APPROVAL}),
                "overdue": table(op_tbl, {"Pending (mtr)": "dec"}, key_col="Days Overdue"),
            },
            "overdue_total": int(len(overdue_po)),
            "timing": [{"label": str(k), "value": float(v)} for k, v in tm.items()],
        }

    # ---- Samples ----
    if xs is not None and not xs.empty:
        st = smp.sample_totals(xs)
        alerts.append({"kind": "success" if st["approval_pct"] >= 50 else "warning", "area": "samples",
                       "title": f"{st['approval_pct']:.1f}% samples approved",
                       "text": f"Approval {st['approval_pct']:.1f}% ({fmt(st['approved'])} of {fmt(st['total'])}), "
                               f"{fmt(st['rejected'])} rejected, {fmt(st['on_hold'] + st['in_process'])} on hold "
                               "or in process."})
        vnames = [n for n in xs["vendor"].unique() if not n.startswith("(")]
        vt = smp.sample_entity_table(xs, "vendor", vnames, "Vendor")
        vt = vt[["Vendor", "Total", "Approved", "Rejected", "On Hold", "In Process", "Approval %"]]
        mt = smp.sample_monthly(xs)
        mt = mt[mt["Total"] > 0]
        sections["samples"] = {
            "kpis": [
                kpi("Total samples", st["total"], "pcs", id="total"),
                kpi("Approved", st["approved"], "pcs", id="approved", tone="good"),
                kpi("Approval rate", st["approval_pct"], "", "pct", id="approval_pct"),
                kpi("Rejected", st["rejected"], "pcs", id="rejected", tone="alert"),
                kpi("On hold", st["on_hold"], "pcs", id="on_hold"),
                kpi("In process", st["in_process"], "pcs", id="in_process"),
            ],
            "table": table(with_total(vt, "Vendor", pct=("Approval %", "Approved", "Total")), {"Approval %": "pct"},
                           key_col="Total", rates={"Approval %": RATE_APPROVAL}),
            "chart": {"categories": list(mt["Month"]), "series": [
                {"name": s_, "values": [float(v) for v in mt[s_]]} for s_ in smp.SAMPLE_STATUSES]},
        }

    # ---- FLO Future (this month's promises; the month filter does not apply) ----
    ff_alert = ffu.overview_alert(ff_p) if ff_p else None
    if ff_alert:
        alerts.append(ff_alert)

    # ---- Designer snapshot (orders + samples) ----
    if xm is not None or (xs is not None and not xs.empty):
        parts = []
        if xm is not None:
            g = xm.groupby("designer")
            parts.append(pd.DataFrame({
                "Order Qty": g["qty"].sum(),
                "New Pcs": xm[xm["order_type"] == "NEW"].groupby("designer")["qty"].sum(),
                "Repeat Pcs": xm[xm["order_type"] == "REPEAT"].groupby("designer")["qty"].sum(),
                "Pending Pcs": g["pending"].sum()}))
        if xs is not None and not xs.empty:
            sd = xs.assign(designer=xs["designer"].str.upper().replace({"(BLANK)": "(NOT ASSIGNED)"}))
            parts.append(pd.DataFrame({
                "Samples": sd.groupby("designer")["qty"].sum(),
                "Approved": sd[sd["status"] == "Approved"].groupby("designer")["qty"].sum()}))
        des = pd.concat(parts, axis=1).fillna(0.0)
        for col_ in ("Order Qty", "New Pcs", "Repeat Pcs", "Pending Pcs", "Samples", "Approved"):
            if col_ not in des.columns:
                des[col_] = 0.0
        des = des[des.abs().sum(axis=1) > 0]
        des["Approval %"] = np.where(des["Samples"] > 0, des["Approved"] / des["Samples"].replace(0, np.nan) * 100,
                                     0.0)
        des.index.name = "Designer"
        des = des.reset_index()[["Designer", "Order Qty", "New Pcs", "Repeat Pcs", "Pending Pcs", "Samples",
                                 "Approved", "Approval %"]]
        des = with_total(des, "Designer", pct=("Approval %", "Approved", "Samples"))
        sections["designers"] = {
            "table": table(des, {"Approval %": "pct"}, key_col="Order Qty", rates={"Approval %": RATE_APPROVAL},
                           note="Order Qty and Pending come from the Master Sheet; Samples and Approved come from "
                                "the sample sheet, joined by designer name."),
        }

    if not alerts and not errors:
        alerts.append({"kind": "info", "area": "none", "title": "No data",
                       "text": "There is no data for the selected months."})
    return {"options": {"month": FY_MONTH_LABELS}, "alerts": alerts, "errors": errors, "sections": sections}
