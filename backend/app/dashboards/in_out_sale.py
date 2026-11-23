"""In / Out / Sale dashboard (sheet "IN/OUT/SALE 2026-27", tab "2026-27").

The tab holds, one under the other:
  1. a month table, this year (2026-27) next to last year (2025-26): Order pieces, Pieces under production,
     Incoming pieces, then Sale pieces / Sale amount / Net sale for both years, and a TOTAL row;
  2. fabricator-wise incoming pieces per month, in several blocks. A block starts at a "FABRICATOR'S" header cell
     and the headers to its right name the month ("APRIL INCOMING") and, where the sheet tracks them, the pcs
     PROMISED for that month and what is still PENDING.
Tables are found by their header text, never by fixed cell addresses, so rows can be added and blocks moved.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from ..core import FY_MONTH_LABELS, FY_START_YEAR, MONTHS, norm_key
from ..tables import kpi, notice, table

TAB = "2026-27"
MONTH_PREFIX = {m[:3].upper(): lab for m, lab in zip(MONTHS, FY_MONTH_LABELS)}
THIS_YEAR = f"{FY_START_YEAR}-{(FY_START_YEAR + 1) % 100:02d}"
LAST_YEAR = f"{FY_START_YEAR - 1}-{FY_START_YEAR % 100:02d}"
MONTH_COLS = {"ORDERPIECES": "order", "PIECESUNDERPRODUCTION": "production", "INCOMINGPIECES": "incoming"}
OUTSOURCE = re.compile(r"\(\s*OUT\s*SOURCE\s*\)", re.I)


def _num(v) -> float:
    if v is None or isinstance(v, bool):
        return 0.0
    if isinstance(v, (int, float)):
        return 0.0 if v != v else float(v)
    s = re.sub(r"[₹,\s]", "", str(v))
    try:
        return float(s)
    except ValueError:
        return 0.0


def _get(grid, r, c):
    return grid[r][c] if 0 <= r < len(grid) and 0 <= c < len(grid[r]) else ""


def month_label_of(v):
    """A month cell -> "April-26". The sheet shows dates formatted as month-year, so a cell holds a real date (a
    Google serial number) or already the text "April-26"."""
    if isinstance(v, datetime):
        return f"{MONTHS[(v.month - 4) % 12]}-{v.year % 100:02d}"
    if isinstance(v, (int, float)) and not isinstance(v, bool) and 20000 < v < 80000:
        d = datetime(1899, 12, 30) + timedelta(days=float(v))
        return f"{MONTHS[(d.month - 4) % 12]}-{d.year % 100:02d}"
    m = re.match(r"\s*([A-Za-z]{3})[A-Za-z]*[\s\-'.]*(?:20)?(\d{2})\s*$", str(v))
    if m and m.group(1).upper() in MONTH_PREFIX:
        return f"{MONTHS[[x[:3].upper() for x in MONTHS].index(m.group(1).upper())]}-{m.group(2)}"
    return None


# ------------------------------------------------------------------------------------------------ month table
def parse_month_table(grid):
    hr = None
    for r, row in enumerate(grid):
        keys = [norm_key(v) for v in row]
        if "MONTH" in keys and keys.count("SALEPIECES") >= 1:
            hr = r
            break
    if hr is None:
        return None
    keys = [norm_key(v) for v in grid[hr]]
    cols = {"month": keys.index("MONTH")}
    for k, name in MONTH_COLS.items():
        if k in keys:
            cols[name] = keys.index(k)
    sale = [i for i, k in enumerate(keys) if k == "SALEPIECES"]
    amount = [i for i, k in enumerate(keys) if k == "SALEAMOUNT"]
    net = [i for i, k in enumerate(keys) if k == "NETSALE"]
    for names, found in ((("pcs", "ly_pcs"), sale), (("amount", "ly_amount"), amount), (("net", "ly_net"), net)):
        for n, i in zip(names, found):
            cols[n] = i
    # year labels sit in the row above ("2026-27" ... "2025-26")
    years = [str(v).strip() for v in (grid[hr - 1] if hr else []) if re.fullmatch(r"\s*\d{4}-\d{2}\s*", str(v))]
    rows, total = [], None
    for r in range(hr + 1, len(grid)):
        first = str(_get(grid, r, 0)).strip().upper()
        month = month_label_of(_get(grid, r, cols["month"]))
        row = {n: _num(_get(grid, r, c)) for n, c in cols.items() if n != "month"}
        if first == "TOTAL":
            total = row
            break
        if month is None:
            if rows:
                break
            continue
        rows.append({"month": month, **row})
    return {"rows": rows, "total": total, "years": years[:2] if len(years) >= 2 else [THIS_YEAR, LAST_YEAR]}


# ------------------------------------------------------------------------------------------------ fabricator blocks
def _clean_name(raw):
    name = re.sub(r"\s+", " ", str(raw)).strip().upper()
    out = bool(OUTSOURCE.search(name))
    return re.sub(r"\s+", " ", OUTSOURCE.sub("", name)).strip(), out


def parse_fabricator_blocks(grid):
    """-> (records, block_totals). records: one per fabricator and month with incoming / promised."""
    records, block_totals = [], {}
    for hr, row in enumerate(grid):
        fcols = [c for c, v in enumerate(row) if norm_key(v) == "FABRICATORS"]
        for n, fc in enumerate(fcols):
            end = fcols[n + 1] if n + 1 < len(fcols) else len(row)
            month, cols = None, {}              # month label -> {"incoming": col, "promised": col, "pending": col}
            for c in range(fc + 1, end):
                text = str(row[c]).strip().upper()
                m = re.match(r"([A-Z]{3})[A-Z]*\.?\s*INCOMING", text)
                if m and m.group(1) in MONTH_PREFIX:
                    month = MONTH_PREFIX[m.group(1)]
                    cols[month] = {"incoming": c}
                elif month and text in ("PROMISED", "PENDING"):
                    cols[month].setdefault(text.lower(), c)
            if not cols:
                continue
            for r in range(hr + 1, len(grid)):
                label = _get(grid, r, fc)
                if str(label).strip() == "" or norm_key(label) == "FABRICATORS":
                    break
                name, outsource = _clean_name(label)
                if name == "TOTAL":
                    for mo, cc in cols.items():
                        block_totals[mo] = _num(_get(grid, r, cc["incoming"]))
                    continue
                for mo, cc in cols.items():
                    promised = _num(_get(grid, r, cc["promised"])) if "promised" in cc else 0.0
                    records.append({"fabricator": name, "outsource": outsource, "month": mo,
                                    "incoming": _num(_get(grid, r, cc["incoming"])),
                                    "promised": promised or None,
                                    "sheet_pending": _num(_get(grid, r, cc["pending"])) if "pending" in cc else None})
    return records, block_totals


def parse_in_out_sale(grid):
    months = parse_month_table(grid)
    records, block_totals = parse_fabricator_blocks(grid)
    return {"months": months, "fab": records, "block_totals": block_totals}


# ------------------------------------------------------------------------------------------------ dashboard
def _pct_change(now, before):
    return float((now - before) / before * 100) if before else np.nan


def _delta(now, before, label, money=False):
    if not before:
        return f"{label}: no sales"
    ch = (now - before) / before * 100
    return f"{'▲' if ch >= 0 else '▼'} {abs(ch):.1f}% vs {label}"


def _total_row(df, first, pct_cols=None, ratios=None):
    tot = {c: (float(df[c].sum()) if pd.api.types.is_numeric_dtype(df[c]) else "") for c in df.columns}
    tot[first] = "TOTAL"
    for c, f in (ratios or {}).items():
        tot[c] = f(tot)
    return pd.concat([df, pd.DataFrame([tot])], ignore_index=True)


def in_out_sale_options(parsed):
    mt = parsed["months"]
    live = [r["month"] for r in mt["rows"] if _has_data(r)] if mt else []
    fab_months = {r["month"] for r in parsed["fab"] if r["incoming"] or r["promised"]}
    months = [m for m in FY_MONTH_LABELS if m in set(live) | fab_months]
    fabs = sorted({r["fabricator"] for r in parsed["fab"]})
    return {"month": months, "fabricator": fabs, "type": ["In-house", "Outsource"]}


def _has_data(r):
    return any(r.get(k) for k in ("order", "production", "incoming", "pcs", "amount", "net"))


def in_out_sale_dashboard(parsed, f):
    mt = parsed["months"]
    if not mt or not mt["rows"]:
        return {"empty": True, "notices": [notice("The 2026-27 tab has no month table (a header row with Month and "
                                                  "Sale pieces) yet.", "warning")]}
    this_y, last_y = mt["years"]
    opts = in_out_sale_options(parsed)
    sel = [m for m in opts["month"] if not f.get("month") or m in f["month"]]
    rows = [r for r in mt["rows"] if r["month"] in sel]
    d = pd.DataFrame(rows)
    d = d.set_index("month").reindex(sel).fillna(0).reset_index() if len(d) else pd.DataFrame(
        columns=["month", "order", "production", "incoming", "pcs", "amount", "net", "ly_pcs", "ly_amount", "ly_net"])
    s = {c: float(d[c].sum()) for c in d.columns if c != "month"}
    per_pc = s["net"] / s["pcs"] if s["pcs"] else 0.0
    ded = (s["amount"] - s["net"]) / s["amount"] * 100 if s["amount"] else 0.0
    sale_vs_in = s["pcs"] / s["incoming"] * 100 if s["incoming"] else 0.0
    label = f"{last_y} (same months)"

    kpis = [
        kpi("Sale pcs", s["pcs"], "pcs", id="sale_pcs", hint=_delta(s["pcs"], s["ly_pcs"], label)),
        kpi("Sale amount", s["amount"], "", fmt="inr", id="sale_amount", hint=_delta(s["amount"], s["ly_amount"], label)),
        kpi("Net sale", s["net"], "", fmt="inr", id="net_sale",
            hint=f"{_delta(s['net'], s['ly_net'], label)} · {ded:.1f}% deducted from sale amount"),
        kpi("Net sale per pc", per_pc, "", fmt="inr", id="net_per_pc",
            hint=f"{last_y}: ₹{s['ly_net'] / s['ly_pcs']:,.0f}" if s["ly_pcs"] else None),
        kpi("Incoming pcs", s["incoming"], "pcs", id="incoming", hint=f"Sale pcs are {sale_vs_in:.0f}% of incoming"),
        kpi("Order pcs", s["order"], "pcs", id="order"),
        kpi("Sent to production", s["production"], "pcs", id="production", hint="Pieces under production"),
    ]

    ms = list(d["month"])
    comp = pd.DataFrame({"Month": ms,
                         f"Sale pcs {this_y}": d["pcs"], f"Sale pcs {last_y}": d["ly_pcs"],
                         "Pcs change %": [_pct_change(a, b) for a, b in zip(d["pcs"], d["ly_pcs"])],
                         f"Net sale {this_y}": d["net"], f"Net sale {last_y}": d["ly_net"],
                         "Net change %": [_pct_change(a, b) for a, b in zip(d["net"], d["ly_net"])]})
    comp_t = _total_row(comp, "Month", ratios={
        "Pcs change %": lambda t: _pct_change(t[f"Sale pcs {this_y}"], t[f"Sale pcs {last_y}"]),
        "Net change %": lambda t: _pct_change(t[f"Net sale {this_y}"], t[f"Net sale {last_y}"])})
    flow = pd.DataFrame({"Month": ms, "Order pcs": d["order"], "Sent to production": d["production"],
                         "Incoming pcs": d["incoming"], "Sale pcs": d["pcs"], "Sale amount": d["amount"],
                         "Net sale": d["net"],
                         "Net per pc": [n / p if p else np.nan for n, p in zip(d["net"], d["pcs"])],
                         "Deducted %": [(a - n) / a * 100 if a else np.nan for a, n in zip(d["amount"], d["net"])]})
    flow_t = _total_row(flow, "Month", ratios={
        "Net per pc": lambda t: t["Net sale"] / t["Sale pcs"] if t["Sale pcs"] else np.nan,
        "Deducted %": lambda t: (t["Sale amount"] - t["Net sale"]) / t["Sale amount"] * 100 if t["Sale amount"] else np.nan})

    cum = lambda xs: [float(v) for v in np.cumsum(xs)]
    charts = {
        "sale_pcs": _series(ms, [(f"Sale pcs {this_y}", d["pcs"]), (f"Sale pcs {last_y}", d["ly_pcs"])]),
        "net_sale": _series(ms, [(f"Net sale {this_y}", d["net"]), (f"Net sale {last_y}", d["ly_net"])]),
        "cumulative_net": _series(ms, [(f"{this_y}", cum(d["net"])), (f"{last_y}", cum(d["ly_net"]))]),
        "flow": _series(ms, [("Order pcs", d["order"]), ("Sent to production", d["production"]),
                             ("Incoming pcs", d["incoming"]), ("Sale pcs", d["pcs"])]),
    }

    fab, fab_tables, fab_charts, checks = _fabricator_part(parsed, f, sel, d)
    checks += _month_checks(mt, parsed, sel)
    return {
        "options": opts,
        "years": {"this": this_y, "last": last_y},
        "kpis": kpis,
        "summary": {"months": len(ms), "sale_pcs": s["pcs"], "net_sale": s["net"],
                    "sale_change_pct": None if not s["ly_pcs"] else round(_pct_change(s["pcs"], s["ly_pcs"]), 1)},
        "tables": {"compare": table(comp_t, fmt={f"Net sale {this_y}": "inr", f"Net sale {last_y}": "inr",
                                                 "Pcs change %": "pct", "Net change %": "pct"}, sort=False),
                   "flow": table(flow_t, fmt={"Sale amount": "inr", "Net sale": "inr", "Net per pc": "inr",
                                              "Deducted %": "pct"}, sort=False),
                   **fab_tables},
        "charts": {**charts, **fab_charts},
        "fabricators": fab,
        "checks": checks,
    }


def _series(categories, named):
    return {"categories": list(categories),
            "series": [{"name": n, "values": [float(v) for v in vals]} for n, vals in named]}


def _fabricator_part(parsed, f, sel, d):
    recs = pd.DataFrame(parsed["fab"])
    if recs.empty:
        return {"count": 0}, {}, {}, []
    recs = recs[recs["month"].isin(sel)]
    kind = f.get("type") or []
    if kind and len(kind) == 1:
        recs = recs[recs["outsource"] == (kind[0] == "Outsource")]
    elif kind:
        recs = recs[recs["outsource"].isin([k == "Outsource" for k in kind])]
    if f.get("fabricator"):
        recs = recs[recs["fabricator"].isin(f["fabricator"])]
    if recs.empty:
        return {"count": 0}, {}, {}, []
    out_flag = parsed_outsource(parsed)
    months = [m for m in FY_MONTH_LABELS if m in set(recs["month"])]
    piv = recs.pivot_table(index="fabricator", columns="month", values="incoming", aggfunc="sum", fill_value=0)
    piv = piv.reindex(columns=months, fill_value=0)
    piv["Total"] = piv[months].sum(axis=1)
    piv = piv.sort_values("Total", ascending=False)
    grand = float(piv["Total"].sum())
    tbl = piv.reset_index().rename(columns={"fabricator": "Fabricator"})
    tbl.insert(1, "Type", ["Outsource" if out_flag.get(n) else "In-house" for n in tbl["Fabricator"]])
    tbl["Share %"] = [v / grand * 100 if grand else 0.0 for v in tbl["Total"]]
    tot = {c: (float(tbl[c].sum()) if pd.api.types.is_numeric_dtype(tbl[c]) else "") for c in tbl.columns}
    tot.update({"Fabricator": "TOTAL", "Type": "", "Share %": 100.0 if grand else 0.0})
    tbl_t = pd.concat([tbl, pd.DataFrame([tot])], ignore_index=True)

    split_in = float(piv.loc[[n for n in piv.index if not out_flag.get(n)], "Total"].sum())
    prom = recs[recs["promised"].notna()].copy()
    prom["pending"] = prom["promised"] - prom["incoming"]
    prom["achieved"] = prom["incoming"] / prom["promised"] * 100
    prom["order"] = prom["month"].map({m: i for i, m in enumerate(FY_MONTH_LABELS)})
    ptab = prom.sort_values(["order", "pending"], ascending=[True, False]).rename(columns={
        "fabricator": "Fabricator", "month": "Month", "promised": "Promised", "incoming": "Incoming",
        "pending": "Pending", "achieved": "Achieved %"})[["Month", "Fabricator", "Promised", "Incoming", "Pending", "Achieved %"]]
    pm = prom.groupby("month")[["promised", "incoming"]].sum().reindex([m for m in months if m in set(prom["month"])])
    fab = {"count": int(len(piv)), "incoming": grand, "top": piv.index[0],
           "top_pct": round(float(piv["Total"].iloc[0] / grand * 100), 1) if grand else 0.0,
           "promised": float(prom["promised"].sum()), "promise_pending": float(prom["pending"].clip(lower=0).sum())}
    tables = {"fabricators": table(tbl_t, fmt={"Share %": "pct", "Type": "text"}, sort=False),
              "promises": table(ptab, fmt={"Achieved %": "pct", "Month": "text"}, sort=False) if len(ptab) else
              table(None)}
    charts = {
        "fab_share": [{"label": n, "value": float(v)} for n, v in piv["Total"].items() if v > 0],
        "fab_split": [{"label": "In-house", "value": split_in}, {"label": "Outsource", "value": grand - split_in}],
        "fab_heat": {"rows": list(piv.index), "columns": months,
                     "values": [[float(piv.loc[n, m]) for m in months] for n in piv.index]},
        "fab_months": _series(months, [(n, [piv.loc[n, m] for m in months]) for n in piv.index[:8]]),
        "promise": _series(list(pm.index), [("Promised", pm["promised"]), ("Incoming", pm["incoming"])]),
    }
    return fab, tables, charts, []


def parsed_outsource(parsed):
    flag = {}
    for r in parsed["fab"]:
        flag[r["fabricator"]] = flag.get(r["fabricator"], False) or r["outsource"]
    return flag


def _month_checks(mt, parsed, sel):
    out = []
    if not mt:
        return out
    rows = {r["month"]: r for r in mt["rows"]}
    t = mt.get("total")
    if t:
        for key, name in (("order", "Order pieces"), ("pcs", "Sale pieces"), ("amount", "Sale amount"), ("net", "Net sale")):
            got = sum(r[key] for r in mt["rows"])
            if abs(got - t.get(key, 0)) > 1:
                out.append(notice(f"{name}: the months add up to {got:,.0f} but the sheet's TOTAL row says "
                                  f"{t.get(key, 0):,.0f}.", "warning"))
    by_fab = {}
    for r in parsed["fab"]:
        by_fab[r["month"]] = by_fab.get(r["month"], 0.0) + r["incoming"]
    for mo in sel:
        if mo in rows and mo in by_fab and abs(rows[mo]["incoming"] - by_fab[mo]) > 0.5:
            out.append(notice(f"{mo}: Incoming pieces is {rows[mo]['incoming']:,.0f} in the month table but the "
                              f"fabricator-wise table adds up to {by_fab[mo]:,.0f}.", "warning"))
    for mo, tot in parsed["block_totals"].items():
        if mo in sel and mo in by_fab and abs(tot - by_fab[mo]) > 0.5:
            out.append(notice(f"{mo}: the fabricator list adds up to {by_fab[mo]:,.0f} but its TOTAL line says {tot:,.0f}.",
                              "warning"))
    return out
