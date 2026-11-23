"""Master Sheet (order tracker) -> Designer, Client and Production dashboards.

Source tab columns (letters on the sheet):
  B order date | C designer | D type (NEW / REPEAT) | F category | J qty | N client | AA fabricator |
  AC production date | AH delay days (>0 = overdue) | AS in production pcs | AT received pcs | AU pending pcs |
  AX status
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from ..core import (CATEGORIES_LIST, today_ist, FY_MONTH_LABELS, KNOWN_DESIGNERS, clean_delay_days, clean_text, col_to_idx,
                    month_label, month_sort_key, norm_key, num, parse_dates, safe_div_pct)
from ..tables import add_total, kpi, notice, table

MASTER_COLS = {
    "date_client": "B", "designer": "C", "type": "D", "category": "F", "qty": "J", "client": "N",
    "fabricator": "AA", "date_prod": "AC", "delay": "AH", "production": "AS", "received": "AT",
    "pending": "AU", "status": "AX", "due60": "AG",
}

CATEGORY_ALIASES = {norm_key(c): c for c in CATEGORIES_LIST}
CATEGORY_ALIASES.update({
    "COORD": "CO-ORD SET", "COORDSETS": "CO-ORD SET", "CORDSET": "CO-ORD SET",
    "KURTAPANTS": "KURTA PANT", "KURTAPANTSET": "KURTA PANT",
    "TOPS": "TOP",
    "KURTAPANTDUPPATA": "KURTA PANT DUPATTA", "KURTAPANTSDUPATTA": "KURTA PANT DUPATTA",
    "KURTAPANTDUPATTASET": "KURTA PANT DUPATTA",
    "DRESSES": "DRESS", "KAFTANS": "KAFTAN", "KURTAS": "KURTA",
})

RISK_OPTIONS = ["Overdue", "On time"]


def canon_category(v):
    v = str(v).strip()
    if not v:
        return ""
    return CATEGORY_ALIASES.get(norm_key(v), v.upper())


# ----------------------------------------------------------------------------------------------- parsing
def build_raw(values):
    """Returns data rows (index = actual sheet row number) and the first data row number."""
    needed_width = col_to_idx("AX") + 1

    def is_row_no(v):
        t = str(v).strip()
        return bool(re.fullmatch(r"\d+(\.0+)?", t)) and float(t) > 0

    first = None
    for i, r in enumerate(values):
        if i < 2 or not r:          # row 1 = title, row 2 = totals row
            continue
        if is_row_no(r[0]) and len(r) > 1 and str(r[1]).strip():
            first = i
            break
    if first is None:
        first = next((i for i, r in enumerate(values) if i >= 2 and r and is_row_no(r[0])),
                     min(4, len(values)))

    rows = values[first:]
    if not rows:
        return pd.DataFrame(), first + 1
    width = max([len(r) for r in rows] + [needed_width])
    df = pd.DataFrame([list(r) + [""] * (width - len(r)) for r in rows],
                      index=range(first + 1, first + 1 + len(rows)))

    b = df[col_to_idx("B")].astype(str).str.strip()
    j_val = num(df[col_to_idx("J")])
    first_cells = df[[0, 1, 2]].apply(lambda c: c.map(norm_key))
    is_total_row = first_cells.isin(["TOTAL", "GRANDTOTAL"]).any(axis=1)
    keep = ((b != "") | (j_val != 0)) & ~is_total_row
    return df[keep], first + 1


def prepare(raw):
    def col(key):
        i = col_to_idx(MASTER_COLS[key])
        if i in raw.columns:
            return raw[i]
        return pd.Series([""] * len(raw), index=raw.index, dtype=object)

    d = pd.DataFrame(index=raw.index)
    d.index.name = "sheet_row"
    d["date_client"] = parse_dates(col("date_client"))
    d["date_prod"] = parse_dates(col("date_prod"))
    d["designer"] = clean_text(col("designer")).str.upper().replace("", "(NOT ASSIGNED)")

    t = clean_text(col("type")).str.upper()
    d["type_raw"] = t
    d["order_type"] = np.select(
        [t.eq("NEW"), t.eq("REPEAT"), t.str.contains("REPEAT"), t.str.contains("NEW")],
        ["NEW", "REPEAT", "REPEAT", "NEW"], default="OTHER")

    d["category"] = clean_text(col("category")).map(canon_category).replace("", "(NO CATEGORY)")
    d["qty"] = num(col("qty"))
    d["client"] = clean_text(col("client")).str.upper().replace("", "(NO CLIENT)")
    d["fabricator"] = clean_text(col("fabricator")).str.upper().replace("", "(NOT ASSIGNED)")
    d["due60"] = parse_dates(col("due60"))      # "60 DAYS DELIVERY DATE": production date + 60 days
    d["delay"] = clean_delay_days(col("delay"))
    d["production"] = num(col("production"))
    d["received"] = num(col("received"))
    d["pending"] = num(col("pending"))
    d["status"] = clean_text(col("status")).str.upper().replace("", "(BLANK)")
    d["month"] = month_label(d["date_client"])
    return d


def parse_master(values):
    """Raw grid -> (DataFrame or None, error text or None)."""
    if not values:
        return None, "The order data tab is empty."
    raw, _first = build_raw(values)
    if raw.empty:
        return None, "No order rows found (expected a serial number in column A and a date in column B)."
    return prepare(raw), None


# ----------------------------------------------------------------------------------------------- filters
def month_list(d):
    """12 FY months always, plus any other month labels that actually carry data (e.g. (NO DATE))."""
    active = d[(d["qty"] != 0) | (d["production"] != 0)]
    extra = [m for m in active["month"].unique() if m not in FY_MONTH_LABELS]
    return FY_MONTH_LABELS + sorted(extra, key=month_sort_key)


def opt_list(d, col, known=(), first=()):
    present = {v for v in d[col].unique() if v}
    rest = sorted((present | set(known)) - set(first))
    return list(first) + rest


def filter_data(d, f):
    """f: {field: [values]} ([] / missing = all) plus "risk": "Overdue" | "On time" | ""."""
    x = d
    for field in ["month", "designer", "client", "fabricator", "status", "category", "order_type"]:
        v = f.get(field) or []
        if v:
            x = x[x[field].isin(v)]
    risk = (f.get("risk") or "").lower()
    if risk.startswith("overdue"):
        x = x[x["delay"] > 0]
    elif risk.startswith("on"):
        x = x[x["delay"] <= 0]
    return x


def master_options(d):
    return {
        "month": month_list(d),
        "designer": opt_list(d, "designer", known=KNOWN_DESIGNERS),
        "client": opt_list(d, "client"),
        "fabricator": opt_list(d, "fabricator"),
        "status": opt_list(d, "status"),
        "category": opt_list(d, "category", first=tuple(CATEGORIES_LIST)),
        "order_type": opt_list(d, "order_type", first=("NEW", "REPEAT")),
        "risk": RISK_OPTIONS,
    }


# ----------------------------------------------------------------------------------------------- KPIs
def designer_kpi_values(x):
    return {
        "designs": int((x["qty"] > 0).sum()),
        "qty": float(x["qty"].sum()),
        "new_qty": float(x.loc[x["order_type"] == "NEW", "qty"].sum()),
        "repeat_qty": float(x.loc[x["order_type"] == "REPEAT", "qty"].sum()),
    }


def client_kpi_values(x):
    return {
        "designs": int((x["qty"] > 0).sum()),
        "qty": float(x["qty"].sum()),
        "production": float(x["production"].sum()),
        "received": float(x["received"].sum()),
        "pending": float(x["pending"].sum()),
        "repeat_qty": float(x.loc[x["order_type"] == "REPEAT", "qty"].sum()),
        "new_qty": float(x.loc[x["order_type"] == "NEW", "qty"].sum()),
        "category_qty": float(x.loc[x["category"].isin(CATEGORIES_LIST), "qty"].sum()),
    }


def production_kpi_values(x):
    base = x[x["production"] > 0]                 # an "order" = a design that is in production
    overdue = base[base["delay"] > 0]
    ontime = base[base["delay"] <= 0]
    n = len(base)
    return {
        "designs": int(n),
        "production": float(x["production"].sum()),
        "received": float(x["received"].sum()),
        "pending": float(x["pending"].sum()),
        "overdue_pcs": float(overdue["production"].sum()),
        "avg_overdue_days": float(overdue["delay"].mean()) if len(overdue) else 0.0,
        "ontime_pct": (len(ontime) / n * 100) if n else 0.0,
        "ontime_pcs": float(ontime["production"].sum()),
        "overdue_designs": int(len(overdue)),
    }


def _with_other_categories(columns_present, nonzero):
    other = [c for c in columns_present if c not in CATEGORIES_LIST and nonzero(c)]
    return CATEGORIES_LIST + other


def _series(categories, named_values):
    return {"categories": list(categories),
            "series": [{"name": n, "values": [float(v) for v in vals]} for n, vals in named_values]}


# ----------------------------------------------------------------------------------------------- dashboards
def designer_dashboard(d_all, f):
    x = filter_data(d_all, f)
    sel = f.get("designer") or []
    if sel:
        designers = list(sel)
    else:
        with_vol = {v for v in d_all.loc[d_all["qty"] > 0, "designer"].unique()}
        designers = sorted((set(KNOWN_DESIGNERS) | with_vol) - {"(NOT ASSIGNED)"})
        if "(NOT ASSIGNED)" in with_vol:
            designers.append("(NOT ASSIGNED)")

    total_qty = x["qty"].sum()
    rows = []
    for des in designers:
        sub = x[x["designer"] == des]
        vol = sub["qty"].sum()
        rows.append({
            "Designer": des,
            "New Orders (Pcs)": sub.loc[sub["order_type"] == "NEW", "qty"].sum(),
            "Repeat Orders (Pcs)": sub.loc[sub["order_type"] == "REPEAT", "qty"].sum(),
            "Total Volume (Pcs)": vol,
            "Share %": (vol / total_qty * 100) if total_qty else 0.0,
            "Design Count": int((sub["qty"] > 0).sum()),
        })
    g = pd.DataFrame(rows, columns=["Designer", "New Orders (Pcs)", "Repeat Orders (Pcs)",
                                    "Total Volume (Pcs)", "Share %", "Design Count"])

    k = designer_kpi_values(x)
    if not g.empty and g["Total Volume (Pcs)"].max() > 0:
        top = g.loc[g["Total Volume (Pcs)"].idxmax()]
        top_name, top_val = top["Designer"], float(top["Total Volume (Pcs)"])
    else:
        top_name, top_val = None, 0.0

    pv = x.groupby(["designer", "category"])["qty"].sum().unstack(fill_value=0)
    cats = _with_other_categories(pv.columns, lambda c: pv[c].sum() != 0)
    pv = pv.reindex(index=designers, columns=cats, fill_value=0)
    pv["TOTAL"] = pv[cats].sum(axis=1)
    cat_df = pv.reset_index()
    cat_df.columns = ["Designer"] + list(cat_df.columns[1:])

    months = month_list(d_all)
    trend = x[x["qty"] != 0].groupby(["month", "designer"], as_index=False)["qty"].sum()
    t_months = [m for m in months if m in set(trend["month"])]
    t_designers = sorted(trend["designer"].unique())
    piv = trend.pivot_table(index="month", columns="designer", values="qty", aggfunc="sum", fill_value=0) \
        if not trend.empty else pd.DataFrame()

    return {
        "kpis": [
            kpi("Total designs", k["designs"], "", "int", "Designs with a quantity above 0", id="designs"),
            kpi("Total quantity", k["qty"], "pcs", id="qty"),
            kpi("New order qty", k["new_qty"], "pcs", id="new_qty"),
            kpi("Repeat order qty", k["repeat_qty"], "pcs", id="repeat_qty"),
            kpi("Top performer", top_name or "—", "", "text", id="top",
                hint=f"{top_val:,.0f} pcs" if top_name else None),
        ],
        "tables": {
            "designers": table(add_total(g, "Designer"), {"Share %": "pct"}, key_col="Total Volume (Pcs)"),
            "categories": table(add_total(cat_df, "Designer"), key_col="TOTAL"),
        },
        "charts": {
            "new_vs_repeat": _series(g["Designer"], [("New", g["New Orders (Pcs)"]),
                                                     ("Repeat", g["Repeat Orders (Pcs)"])]),
            "monthly_trend": _series(t_months, [(des, [float(piv.at[m, des]) if m in piv.index else 0.0
                                                       for m in t_months]) for des in t_designers]),
        },
    }


def delivery60(x, today=None):
    """Pending pcs against the 60-day delivery date (sheet column AG). Only rows that still have pcs pending count.
    A design is overdue when its delivery date is before today; rows without a delivery date are listed apart."""
    if "due60" not in x.columns:
        return None
    today = pd.Timestamp(today if today is not None else today_ist()).normalize()
    p = x[x["pending"] > 0].copy()
    if p.empty:
        return None
    due = p["due60"]
    days = (due - today).dt.days
    p["overdue"] = due.notna() & (days < 0)
    buckets = [("overdue", "Overdue", p["overdue"], "alert"),
               ("due7", "Due in 7 days", due.notna() & (days >= 0) & (days <= 7), None),
               ("due30", "Due in 8-30 days", due.notna() & (days > 7) & (days <= 30), None),
               ("later", "Due later", due.notna() & (days > 30), None),
               ("nodate", "No delivery date", due.isna(), None)]
    kpis = [kpi(label, float(p.loc[m, "pending"].sum()), "pcs", id=key, tone=tone,
                hint=f"{int(m.sum())} designs") for key, label, m, tone in buckets]
    kpis.insert(0, kpi("Pending", float(p["pending"].sum()), "pcs", id="total", hint=f"{len(p)} designs · sheet column AU"))

    dated = p[due.notna()].copy()
    dated["due_month"] = month_label(dated["due60"])
    # every month from the first to the last delivery month, so a month with nothing due shows as 0
    span = pd.Series(pd.date_range(dated["due60"].min().replace(day=1), dated["due60"].max(), freq="MS"))
    order = list(month_label(span)) if len(span) else sorted(dated["due_month"].unique(), key=month_sort_key)
    g = dated.groupby("due_month")
    pend = g["pending"].sum().reindex(order, fill_value=0)
    over = dated[dated["overdue"]].groupby("due_month")["pending"].sum().reindex(order, fill_value=0)
    mt = pd.DataFrame({"Delivery month": order, "Designs": g.size().reindex(order, fill_value=0).to_numpy(),
                       "Pending pcs": pend.to_numpy(), "Overdue pcs": over.to_numpy()})
    gc = p.groupby("client")
    ct = pd.DataFrame({"Client": list(gc.groups)})
    ct["Designs"] = gc.size().reindex(ct["Client"]).to_numpy()
    ct["Pending pcs"] = gc["pending"].sum().reindex(ct["Client"]).to_numpy()
    ct["Overdue pcs"] = p[p["overdue"]].groupby("client")["pending"].sum().reindex(ct["Client"], fill_value=0).to_numpy()
    oldest = dated.groupby("client")["due60"].min().reindex(ct["Client"])
    ct["Oldest delivery date"] = [d.strftime("%d/%m/%Y") if pd.notna(d) else "" for d in oldest]
    return {
        "today": today.strftime("%d/%m/%Y"),
        "kpis": kpis,
        "chart": _series(order, [("Overdue", [float(v) for v in over]),
                                 ("Not yet due", [float(a - b) for a, b in zip(pend, over)])]),
        "tables": {"months": table(add_total(mt, "Delivery month"), key_col="Pending pcs", sort=False),
                   "clients": table(add_total(ct, "Client"), fmt={"Oldest delivery date": "text"}, key_col="Pending pcs")},
    }


def client_dashboard(d_all, f, today=None):
    x = filter_data(d_all, f)
    k = client_kpi_values(x)
    months = month_list(d_all)

    m = x.groupby("month")[["qty", "production", "received", "pending"]].sum().reindex(months, fill_value=0)
    m = m.reset_index()
    m.columns = ["Month", "Order Qty", "In Production", "Received", "Pending"]

    pv = x.groupby(["month", "category"])["qty"].sum().unstack(fill_value=0)
    cats = _with_other_categories(pv.columns, lambda c: pv[c].sum() != 0)
    pv = pv.reindex(index=months, columns=cats, fill_value=0)
    pv["TOTAL"] = pv[cats].sum(axis=1)
    cat_df = pv.reset_index()
    cat_df.columns = ["Month"] + list(cat_df.columns[1:])

    pie = m[m["Order Qty"] > 0]
    cl = x.groupby("client")["qty"].sum().sort_values(ascending=False)
    cl = cl[cl > 0]
    if len(cl) > 8:                       # a pie stays readable with a handful of slices; the rest is one slice
        cl = pd.concat([cl.iloc[:7], pd.Series({"OTHER CLIENTS": cl.iloc[7:].sum()})])
    cat_months = [mo for mo in months if cat_df.loc[cat_df["Month"] == mo, cats].to_numpy().sum() != 0]
    cat_used = [c for c in cats if cat_df[c].sum() != 0]
    return {
        "kpis": [
            kpi("Total designs", k["designs"], id="designs"),
            kpi("Total quantity", k["qty"], "pcs", id="qty"),
            kpi("In production", k["production"], "pcs", id="production", hint="Sheet column AS"),
            kpi("Received", k["received"], "pcs", id="received", hint="Sheet column AT"),
            kpi("Pending", k["pending"], "pcs", id="pending", hint="Sheet column AU", tone="alert"),
            kpi("Repeat orders", k["repeat_qty"], "pcs", id="repeat_qty"),
            kpi("New orders", k["new_qty"], "pcs", id="new_qty"),
            kpi("Category total", k["category_qty"], "pcs", id="category_qty",
                hint="Quantity in the 7 standard categories"),
        ],
        "delivery60": delivery60(x, today),
        "tables": {
            "monthly": table(add_total(m, "Month"), key_col="Order Qty", sort=False),
            "categories": table(add_total(cat_df, "Month"), key_col="TOTAL", sort=False),
        },
        "charts": {
            "monthly_share": [{"label": r["Month"], "value": float(r["Order Qty"])} for _, r in pie.iterrows()],
            "client_share": [{"label": str(n), "value": float(v)} for n, v in cl.items()],
            "fulfilment": [{"label": "Received", "value": k["received"]}, {"label": "Pending", "value": k["pending"]}]
            if k["received"] + k["pending"] > 0 else [],
            "category_by_month": _series(cat_months, [
                (c, [float(cat_df.loc[cat_df["Month"] == mo, c].iloc[0]) for mo in cat_months]) for c in cat_used]),
        },
    }


def production_dashboard(d_all, f):
    x = filter_data(d_all, f)
    k = production_kpi_values(x)

    cat = x.groupby("category")[["production", "received", "pending"]].sum()
    other = [c for c in cat.index if c not in CATEGORIES_LIST and cat.loc[c].abs().sum() != 0]
    cat = cat.reindex(CATEGORIES_LIST + other, fill_value=0).reset_index()
    cat.columns = ["Category", "In Production", "Received", "Pending"]

    fab = x.groupby("fabricator", as_index=False)["pending"].sum()
    fab = fab[fab["pending"] > 0].sort_values("pending", ascending=False)
    fab_tbl = fab.rename(columns={"fabricator": "Fabricator", "pending": "Pending Pcs"})
    if not fab_tbl.empty:
        fab_tbl["Share %"] = fab_tbl["Pending Pcs"] / fab_tbl["Pending Pcs"].sum() * 100

    months = month_list(d_all)
    grp = x.groupby("month")
    mdf = pd.DataFrame({
        "Orders": grp["production"].apply(lambda s: int((s > 0).sum())),
        "In Production": grp["production"].sum(),
        "Received": grp["received"].sum(),
        "Pending": grp["pending"].sum(),
    }).reindex(months, fill_value=0).reset_index()
    mdf.columns = ["Month", "Orders", "In Production", "Received", "Pending"]

    return {
        "kpis": [
            kpi("Designs in production", k["designs"], "", id="designs"),
            kpi("In production", k["production"], "pcs", id="production", hint="Sheet column AS"),
            kpi("Received", k["received"], "pcs", id="received", hint="Sheet column AT"),
            kpi("Pending", k["pending"], "pcs", id="pending", hint="Sheet column AU"),
            kpi("Overdue pcs", k["overdue_pcs"], "pcs", id="overdue_pcs", tone="alert",
                hint="In-production pcs with delay days above 0 (column AH)"),
            kpi("Avg overdue", k["avg_overdue_days"], "days", "dec1", id="avg_overdue_days"),
            kpi("On-time delivery", k["ontime_pct"], "", "pct", id="ontime_pct",
                hint="Share of designs in production with delay days of 0 or less"),
            kpi("On-time pcs", k["ontime_pcs"], "pcs", id="ontime_pcs"),
        ],
        "tables": {
            "categories": table(add_total(cat, "Category"), key_col="Pending"),
            "fabricators": table(add_total(fab_tbl, "Fabricator"), {"Share %": "pct"}, key_col="Pending Pcs")
            if not fab_tbl.empty else table(None),
            "monthly": table(add_total(mdf, "Month"), key_col="Pending", sort=False),
        },
        "charts": {
            "by_category": _series(cat["Category"], [("In production", cat["In Production"]),
                                                     ("Received", cat["Received"]), ("Pending", cat["Pending"])]),
            "pending_share": [{"label": r["fabricator"], "value": float(r["pending"])} for _, r in fab.iterrows()],
            "monthly": _series(mdf["Month"], [("In production", mdf["In Production"]),
                                              ("Received", mdf["Received"]), ("Pending", mdf["Pending"])]),
        },
        "summary": {"overdue_designs": k["overdue_designs"],
                    "pending_pct": safe_div_pct(k["pending"], k["production"])},
    }


def overview_order_stats(g):
    """Order / production numbers for any slice - same definitions as the Production dashboard KPIs."""
    k = production_kpi_values(g)
    return {"Designs": int(k["designs"]), "Order Qty": float(g["qty"].sum()),
            "In Production": k["production"], "Received": k["received"],
            "Pending": k["pending"], "Overdue Pcs": k["overdue_pcs"],
            "Avg Overdue Days": k["avg_overdue_days"], "On-Time %": k["ontime_pct"]}


def empty_notice():
    return notice("No data for the selected filters.")
