"""Target & Revenue dashboard (sheet: "DESIGNER'S TARGET ACHIEVED 2026-27").

Source tabs "NEW" and "REPEAT": row 1 = title, row 2 = header, data from row 3.
Columns (A..K): S.NO | ORDER DATE | IMAGE | BARCODE | ITEM NAME | SIZE | NO.OF PCS | RATE | ORDER BY | DESIGNER |
TOTAL AMOUNT. Revenue = NO.OF PCS x RATE (RATE = price of one piece). The sheet's TOTAL AMOUNT column is only
used to cross-check the calculation. The yearly target is for NEW orders only, tracked by ORDER DATE month.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from ..core import (FY_MONTH_LABELS, FY_MONTH_NOS, FY_START_YEAR, clean_text, inr, inr_short, month_label,
                    month_sort_key, norm_key, num, parse_dates, safe_div_pct, today_ist)
from ..tables import RATE_TARGET, kpi, notice, records, table

NEW_TARGET_CR = 50.2
NEW_MONTHLY_WEIGHTS = [1] * 12       # Apr..Mar. Equal = target / 12 per month.
TGT_COLS = {
    "sno": ("SNO", 0), "date": ("ORDERDATE", 1), "image": ("IMAGE", 2), "barcode": ("BARCODE", 3),
    "item": ("ITEMNAME", 4), "size": ("SIZE", 5), "pcs": ("NOOFPCS", 6), "rate": ("RATE", 7),
    "order_by": ("ORDERBY", 8), "designer": ("DESIGNER", 9), "sheet_total": ("TOTALAMOUNT", 10),
}
REV_FMT = {"New Revenue": "inr", "Repeat Revenue": "inr", "Total Revenue": "inr", "Avg Rate (₹/pc)": "inr",
           "Share %": "pct"}
FILTER_FIELDS = {"month": "month", "designer": "designer", "item": "item", "order_by": "order_by",
                 "source": "source"}


def tgt_header_row(grid):
    for r in range(min(10, len(grid))):
        keys = {norm_key(c) for c in grid[r]}
        if "ORDERDATE" in keys and ({"NOOFPCS", "RATE", "BARCODE"} & keys):
            return r
    return None


def tgt_col_map(header):
    keys = [norm_key(h) for h in header]
    out = {}
    for field, (name, pos) in TGT_COLS.items():
        idx = keys.index(name) if name in keys else next((i for i, k in enumerate(keys) if k.startswith(name)), None)
        out[field] = idx if idx is not None else pos
    return out


def build_target_orders(values, source):
    """Raw tab grid (unformatted) -> one clean row per order line. Returns (df, header_found)."""
    hr = tgt_header_row(values)
    header_ok = hr is not None
    if hr is None:
        hr = 1 if len(values) > 1 else 0
    if not values:
        return pd.DataFrame(), header_ok
    cmap = tgt_col_map(values[hr])
    rows = values[hr + 1:]
    if not rows:
        return pd.DataFrame(), header_ok
    width = max(max(len(r) for r in rows), max(cmap.values()) + 1)
    grid = pd.DataFrame([list(r) + [""] * (width - len(r)) for r in rows], index=range(hr + 2, hr + 2 + len(rows)))

    def col(field):
        return grid[cmap[field]]

    pcs, rate, sno = num(col("pcs")), num(col("rate")), num(col("sno"))
    barcode = clean_text(col("barcode")).str.upper()
    item = clean_text(col("item")).str.upper()
    label_cells = pd.concat([clean_text(col(f)).str.upper() for f in ("sno", "date", "barcode", "item")], axis=1)
    totalish = label_cells.apply(lambda c: c.str.contains(r"\bTOTAL\b", regex=True)).any(axis=1)
    has_id = (barcode != "") | (item != "") | (sno > 0)
    keep = (pcs > 0) & has_id & ~totalish            # drops blank rows, TOTAL rows, helper rows

    d = pd.DataFrame(index=grid.index)
    d.index.name = "sheet_row"
    d["source"] = source
    d["date"] = parse_dates(col("date"))
    d["month"] = month_label(d["date"])
    d["barcode"] = barcode.replace("", "(NO BARCODE)")
    d["item"] = item.replace("", "(NO ITEM)")
    d["size"] = clean_text(col("size"))
    d["pcs"] = pcs
    d["rate"] = rate
    d["order_by"] = clean_text(col("order_by")).str.upper().replace("", "(BLANK)")
    d["designer"] = clean_text(col("designer")).str.upper().replace("", "(NOT ASSIGNED)")
    d["sheet_total"] = num(col("sheet_total"))
    d["revenue"] = d["pcs"] * d["rate"]
    return d[keep], header_ok


def img_url(cell):
    """=IMAGE("url") formula or a plain link -> usable image URL ('' if none). Drive links become thumbnails."""
    t = str(cell or "").strip()
    m = re.search(r'IMAGE\(\s*"([^"]+)"', t, re.I)
    url = m.group(1) if m else (t if re.match(r"https?://", t, re.I) else "")
    if not url:
        return ""
    d = re.search(r"drive\.google\.com/(?:file/d/|open\?id=|uc\?(?:export=\w+&)?id=)([\w-]+)", url)
    return f"https://drive.google.com/thumbnail?id={d.group(1)}&sz=w300" if d else url


def image_map(formula_rows):
    """FORMULA-rendered single-column values -> {sheet_row: url}."""
    out = {}
    for i, row in enumerate(formula_rows or [], start=1):
        u = img_url(row[0] if row else "")
        if u:
            out[i] = u
    return out


def parse_target(tab_packs):
    """tab_packs: [(source, tab_title or None, values, formulas_or_None), ...] -> {"d": df, "notes": [...]}"""
    frames, notes = [], []
    for source, tab, values, formulas in tab_packs:
        if tab is None:
            names = "NEW" if source == "NEW" else "REPEAT"
            notes.append(f"The '{names}' tab was not found on the sheet, so its orders are not counted.")
            continue
        df, header_ok = build_target_orders(values, source)
        if not df.empty:
            imgs = image_map(formulas)
            df["image"] = [imgs.get(r, "") for r in df.index]
        if not header_ok:
            notes.append(f"No header row (ORDER DATE / NO.OF PCS / RATE) found on the '{tab}' tab. Default columns "
                         "(A..K) were used; please check the numbers.")
        if not df.empty:
            df["tab"] = tab
            frames.append(df)
    d = pd.concat(frames).reset_index() if frames else pd.DataFrame()
    return {"d": d, "notes": notes}


def _month_start(i):
    return pd.Timestamp(year=FY_START_YEAR if i < 9 else FY_START_YEAR + 1, month=FY_MONTH_NOS[i], day=1)


def target_monthly(d, annual_target, today):
    """Month-wise NEW target vs achieved. Returns (table without TOTAL row, FY month start dates)."""
    extra = sorted({m for m in d["month"].unique() if m not in FY_MONTH_LABELS}, key=month_sort_key)
    months = FY_MONTH_LABELS + extra
    w = np.asarray(NEW_MONTHLY_WEIGHTS, dtype=float)
    w = w / w.sum() if w.sum() > 0 else np.full(12, 1 / 12)
    tgt = pd.Series(0.0, index=months)
    tgt.loc[FY_MONTH_LABELS] = annual_target * w
    is_new = d["source"] == "NEW"
    new = d[is_new].groupby("month")["revenue"].sum().reindex(months, fill_value=0.0)
    rep = d[~is_new].groupby("month")["revenue"].sum().reindex(months, fill_value=0.0)
    starts = pd.Series([_month_start(i) for i in range(12)] + [pd.NaT] * len(extra), index=months)
    in_fy = pd.Series([True] * 12 + [False] * len(extra), index=months)
    future = in_fy & (starts > today) & (new == 0)          # month not started yet -> no % / variance shown

    pct = pd.Series(np.where(tgt > 0, new / tgt.replace(0, np.nan) * 100, np.nan), index=months)
    pct[future] = np.nan
    var = (new - tgt).where(in_fy & ~future)
    cum_t = tgt.where(in_fy).cumsum()
    cum_a = new.where(in_fy).cumsum().where(~future)
    cum_p = cum_a / cum_t.replace(0, np.nan) * 100
    df = pd.DataFrame({
        "Month": months, "Target": tgt.values, "Achieved (New)": new.values, "Achieved %": pct.values,
        "Variance": var.values, "Cum. Target": cum_t.values, "Cum. Achieved": cum_a.values, "Cum. %": cum_p.values,
        "Repeat Revenue": rep.values, "New + Repeat": (new + rep).values})
    return df, starts


def rev_stats(g):
    rev, pcs = float(g["revenue"].sum()), float(g["pcs"].sum())
    return {"New Revenue": float(g.loc[g["source"] == "NEW", "revenue"].sum()),
            "Repeat Revenue": float(g.loc[g["source"] == "REPEAT", "revenue"].sum()),
            "Total Revenue": rev, "Total Pcs": pcs, "Orders": int(len(g)),
            "Avg Rate (₹/pc)": (rev / pcs) if pcs else 0.0}


def rev_group(x, col, label, index=None, share=True):
    """Revenue table grouped by `col` (+ TOTAL row, totals recomputed - averages are never summed)."""
    total = float(x["revenue"].sum())
    keys = list(index) if index is not None else list(dict.fromkeys(x[col]))
    rows = []
    for k in keys:
        s = rev_stats(x[x[col] == k])
        if share:
            s["Share %"] = safe_div_pct(s["Total Revenue"], total)
        rows.append({label: k, **s})
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    if index is None:
        df = df.sort_values("Total Revenue", ascending=False).reset_index(drop=True)
    tot = {label: "TOTAL", **rev_stats(x)}
    if share:
        tot["Share %"] = 100.0 if total else 0.0
    cols = [label, "New Revenue", "Repeat Revenue", "Total Revenue"] + (["Share %"] if share else []) + \
           ["Total Pcs", "Orders", "Avg Rate (₹/pc)"]
    return pd.concat([df, pd.DataFrame([tot])], ignore_index=True)[cols]


def tracker(d, annual_cr, today=None):
    """Section A: the overall NEW-order target tracker (filters never apply)."""
    today = today if today is not None else today_ist()
    annual_target = float(annual_cr) * 1e7
    mt, starts = target_monthly(d, annual_target, today)
    new_total = float(d.loc[d["source"] == "NEW", "revenue"].sum())
    rep_total = float(d.loc[d["source"] == "REPEAT", "revenue"].sum())
    ach_pct = safe_div_pct(new_total, annual_target)
    remaining = max(annual_target - new_total, 0.0)
    elapsed = [m for m in FY_MONTH_LABELS if starts[m] <= today]
    months_left = sum(1 for m in FY_MONTH_LABELS if (starts[m] + pd.offsets.MonthEnd(0)) >= today)
    sched = float(mt.loc[mt["Month"].isin(elapsed), "Target"].sum())
    gap = new_total - sched
    return {"mt": mt, "starts": starts, "annual_target": annual_target, "new_total": new_total,
            "rep_total": rep_total, "ach_pct": ach_pct, "remaining": remaining, "elapsed": elapsed,
            "months_left": months_left, "sched": sched, "gap": gap}


def _filter(d, f):
    x = d
    for field, col in FILTER_FIELDS.items():
        sel = f.get(field) or []
        if sel:
            x = x[x[col].isin(sel)]
    return x


def _top_repeat(x):
    rp = x[x["source"] == "REPEAT"]
    if rp.empty:
        return []

    def _first(sr):
        v = [i for i in sr if i]
        return v[0] if v else ""
    g = rp.sort_values("date").groupby("barcode").agg(
        image=("image", _first), item=("item", "first"),
        designer=("designer", lambda v: v.mode().iloc[0] if len(v.mode()) else ""),
        orders=("pcs", "size"), pcs=("pcs", "sum"), revenue=("revenue", "sum"),
        last=("date", "max")).reset_index()
    g = g.sort_values(["orders", "pcs", "revenue"], ascending=False).head(15).reset_index(drop=True)
    g["last"] = g["last"].dt.strftime("%d/%m/%Y").fillna("")
    return records(g, ["barcode", "image", "item", "designer", "orders", "pcs", "revenue", "last"])


def quality(d):
    """Cross-checks Revenue (PCS x RATE) with the sheet's own TOTAL AMOUNT column and flags bad rows."""
    calc, sheet = float(d["revenue"].sum()), float(d["sheet_total"].sum())
    mism = d[(d["sheet_total"] > 0) & ((d["revenue"] - d["sheet_total"]).abs() > 1)]
    no_total = d[(d["sheet_total"] <= 0) & (d["revenue"] > 0)]
    no_rate = d[d["rate"] <= 0]
    no_date = d[d["month"] == "(NO DATE)"]
    out = [notice(f"Order lines: {len(d):,} · Calculated revenue (pcs × rate): {inr(calc)} · "
                  f"Sheet TOTAL AMOUNT sum: {inr(sheet)}", "info")]
    if mism.empty and no_total.empty:
        out.append(notice("The calculation matches the sheet's TOTAL AMOUNT column.", "success"))
    if not mism.empty:
        out.append(notice(f"{len(mism):,} rows have pcs × rate different from the sheet's TOTAL AMOUNT (net "
                          f"difference {inr(mism['revenue'].sum() - mism['sheet_total'].sum())}). The dashboard "
                          "uses pcs × rate.", "warning"))
    if not no_total.empty:
        out.append(notice(f"{len(no_total):,} rows have a blank or zero TOTAL AMOUNT but revenue from pcs × rate; "
                          "they are counted.", "warning"))
    if not no_rate.empty:
        out.append(notice(f"{len(no_rate):,} rows have a blank or zero RATE, so their revenue counts as 0 "
                          f"({int(no_rate['pcs'].sum()):,} pcs).", "warning"))
    if not no_date.empty:
        out.append(notice(f"{len(no_date):,} rows have a blank or unreadable ORDER DATE; they appear under "
                          "'(NO DATE)' in the month-wise table.", "warning"))
    bad = pd.concat([mism, no_rate, no_date]).drop_duplicates(subset=["tab", "sheet_row"])
    rows = None
    if not bad.empty:
        b = pd.DataFrame({"Location": bad["tab"] + " · row " + bad["sheet_row"].astype(int).astype(str),
                          "Barcode": bad["barcode"].values, "Pcs": bad["pcs"].values,
                          "Rate (₹/pc)": bad["rate"].values, "Calculated": bad["revenue"].values,
                          "Sheet Total": bad["sheet_total"].values,
                          "Difference": (bad["revenue"] - bad["sheet_total"]).values})
        rows = table(b, {c: "inr" for c in ("Rate (₹/pc)", "Calculated", "Sheet Total", "Difference")},
                     key_col="Difference", sort_abs=True)
    return {"notices": out, "rows": rows}


def target_dashboard(parsed, f, annual_cr=None, today=None, max_lines=3000):
    d, notes = parsed["d"], parsed["notes"]
    notices = [notice(n, "warning") for n in notes]
    if d.empty:
        notices.append(notice("No order data found on the target sheet. Expected 'NEW' and 'REPEAT' tabs with a "
                              "header on row 2 (ORDER DATE, BARCODE, ITEM NAME, NO.OF PCS, RATE, ORDER BY, DESIGNER, "
                              "TOTAL AMOUNT) and data from row 3.", "warning"))
        return {"empty": True, "notices": notices, "options": {k: [] for k in FILTER_FIELDS}}
    annual_cr = NEW_TARGET_CR if annual_cr is None else float(annual_cr)
    today = today if today is not None else today_ist()
    t = tracker(d, annual_cr, today)
    mt = t["mt"]

    if not t["elapsed"]:
        sched_txt = "FY not started"
    else:
        sched_txt = f"{'Ahead' if t['gap'] >= 0 else 'Behind'} {inr_short(abs(t['gap']))}"
    if t["months_left"] and t["remaining"] > 0:
        req_val, req_hint = t["remaining"] / t["months_left"], f"{t['months_left']} months left"
    else:
        req_val, req_hint = None, ("Target achieved" if t["remaining"] <= 0 and t["annual_target"] > 0 else None)

    tot_row = {"Month": "TOTAL", "Target": float(mt.loc[mt["Month"].isin(FY_MONTH_LABELS), "Target"].sum()),
               "Achieved (New)": t["new_total"], "Achieved %": t["ach_pct"] if t["annual_target"] > 0 else np.nan,
               "Variance": t["new_total"] - t["annual_target"], "Cum. Target": np.nan, "Cum. Achieved": np.nan,
               "Cum. %": np.nan, "Repeat Revenue": t["rep_total"], "New + Repeat": t["new_total"] + t["rep_total"]}
    shown = pd.concat([mt, pd.DataFrame([tot_row])], ignore_index=True)
    money = {c: "inr" for c in ("Target", "Achieved (New)", "Variance", "Cum. Target", "Cum. Achieved",
                                "Repeat Revenue", "New + Repeat")}
    nd = float(d.loc[(d["month"] == "(NO DATE)") & (d["source"] == "NEW"), "revenue"].sum())
    tracker_notes = []
    if nd > 0:
        tracker_notes.append(notice(f"{inr(nd)} of NEW orders have a blank or unreadable order date. They count in "
                                    "the total but not in any month (see the '(NO DATE)' row).", "warning"))

    extra_m = sorted({m for m in d["month"].unique() if m not in FY_MONTH_LABELS}, key=month_sort_key)
    all_months = FY_MONTH_LABELS + extra_m

    def opts(c):
        return sorted(v for v in d[c].unique() if v)

    options = {"month": all_months, "designer": opts("designer"), "item": opts("item"), "order_by": opts("order_by"),
               "source": ["NEW", "REPEAT"]}

    out = {
        "options": options,
        "notices": notices,
        "annual_target_cr": annual_cr,
        "tracker": {
            "kpis": [
                kpi("Yearly target (new)", t["annual_target"], "", "inr", id="target"),
                kpi("Achieved (new)", t["new_total"], "", "inr", id="achieved"),
                kpi("Achieved", t["ach_pct"], "", "pct", id="achieved_pct"),
                kpi("Remaining target", t["remaining"], "", "inr", id="remaining"),
                kpi(f"Vs schedule (to {t['elapsed'][-1] if t['elapsed'] else '-'})", sched_txt, "", "text",
                    id="schedule", tone="good" if t["gap"] >= 0 else "alert",
                    hint="Cumulative target of the months so far (including the current month) minus achieved"),
                kpi("Required per month", req_val if req_val is not None else (req_hint or "—"), "",
                    "inr" if req_val is not None else "text", id="required",
                    hint=req_hint if req_val is not None else None),
                kpi("Repeat revenue", t["rep_total"], "", "inr", id="repeat"),
                kpi("Total revenue (new + repeat)", t["new_total"] + t["rep_total"], "", "inr", id="total"),
            ],
            "gauge": {"value": t["ach_pct"], "achieved": t["new_total"], "target": t["annual_target"]},
            "schedule": {"gap": t["gap"], "scheduled": t["sched"], "elapsed": t["elapsed"],
                         "months_left": t["months_left"]},
            "monthly": {"categories": list(mt["Month"]),
                        "achieved": [float(v) for v in mt["Achieved (New)"]],
                        "target": [float(v) for v in mt["Target"]],
                        "cum_target": [None if pd.isna(v) else float(v) for v in mt["Cum. Target"]],
                        "cum_achieved": [None if pd.isna(v) else float(v) for v in mt["Cum. Achieved"]]},
            "table": table(shown, {**money, "Achieved %": "pct", "Cum. %": "pct"}, key_col="Achieved (New)",
                           sort=False, rates={"Achieved %": RATE_TARGET, "Cum. %": RATE_TARGET}),
            "notices": tracker_notes,
        },
        "quality": quality(d),
    }

    x = _filter(d, f)
    if x.empty:
        out["filtered"] = {"empty": True, "notices": [notice("No orders match the selected filters.")]}
        return out

    s = rev_stats(x)
    des = rev_group(x, "designer", "Designer")
    itm = rev_group(x, "item", "Item Name")
    byc = rev_group(x, "order_by", "Order By")
    des_b, itm_b, byc_b = (tb[tb.iloc[:, 0] != "TOTAL"] for tb in (des, itm, byc))
    mrev = rev_group(x, "month", "Month", index=all_months, share=False)
    mbody = mrev[mrev["Month"] != "TOTAL"]
    o = des_b.sort_values("Total Revenue")

    full = x.sort_values(["date", "sheet_row"]).copy()
    full["Order Date"] = full["date"].dt.strftime("%d/%m/%Y").fillna("")
    full = full[["tab", "sheet_row", "Order Date", "barcode", "item", "size", "pcs", "rate", "revenue",
                 "order_by", "designer"]]
    full.columns = ["Tab", "Sheet Row", "Order Date", "Barcode", "Item Name", "Size", "Pcs", "Rate (₹/pc)",
                    "Revenue", "Order By", "Designer"]
    truncated = len(full) > max_lines

    out["filtered"] = {
        "kpis": [
            kpi("Total revenue", s["Total Revenue"], "", "inr", id="revenue"),
            kpi("New order revenue", s["New Revenue"], "", "inr", id="new"),
            kpi("Repeat order revenue", s["Repeat Revenue"], "", "inr", id="repeat"),
            kpi("Repeat share", safe_div_pct(s["Repeat Revenue"], s["Total Revenue"]), "", "pct", id="repeat_share"),
            kpi("Total pcs", s["Total Pcs"], "pcs", id="pcs"),
            kpi("Order lines", s["Orders"], "", id="lines"),
            kpi("Unique designs", x["barcode"].nunique(), "", id="designs", hint="Distinct barcodes"),
            kpi("Avg rate per pc", s["Avg Rate (₹/pc)"], "", "inr_full", id="avg_rate"),
            kpi("Top designer", des_b.iloc[0, 0] if len(des_b) else "—", "", "text", id="top_designer",
                hint=inr_short(des_b.iloc[0]["Total Revenue"]) if len(des_b) else None),
            kpi("Top item", itm_b.iloc[0, 0] if len(itm_b) else "—", "", "text", id="top_item",
                hint=inr_short(itm_b.iloc[0]["Total Revenue"]) if len(itm_b) else None),
        ],
        "tables": {
            "monthly": table(mrev, REV_FMT, key_col="Total Revenue", sort=False),
            "designers": table(des, REV_FMT, key_col="Total Revenue"),
            "items": table(itm, REV_FMT, key_col="Total Revenue"),
            "order_by": table(byc, REV_FMT, key_col="Total Revenue"),
            "lines": table(full.head(max_lines), {"Rate (₹/pc)": "inr", "Revenue": "inr", "Sheet Row": "text"},
                           sort=False),
        },
        "lines_total": int(len(full)),
        "lines_truncated": truncated,
        "top_repeat": _top_repeat(x),
        "charts": {
            "monthly": {"categories": list(mbody["Month"]), "series": [
                {"name": "New", "values": [float(v) for v in mbody["New Revenue"]]},
                {"name": "Repeat", "values": [float(v) for v in mbody["Repeat Revenue"]]}]},
            "designers": {"categories": list(o["Designer"]), "series": [
                {"name": "New", "values": [float(v) for v in o["New Revenue"]]},
                {"name": "Repeat", "values": [float(v) for v in o["Repeat Revenue"]]}]},
            "items": [{"label": r["Item Name"], "value": float(r["Total Revenue"])} for _, r in itm_b.iterrows()],
            "order_by": [{"label": r["Order By"], "value": float(r["Total Revenue"])} for _, r in byc_b.iterrows()],
        },
    }
    return out
