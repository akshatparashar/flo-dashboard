"""Stock Ageing (FIFO) dashboard: finished-goods PCS stock from EasyTrade (SQL Server, F2ETrade11).

The dashboard server does not connect to SQL itself. It reads a snapshot file, stock_ageing.json, from the folder in
SQL_SNAPSHOT_DIR (one row per design with the closing pcs already split FIFO into age buckets). The file holds company
figures, so it lives outside the repository. Without it, made-up demo rows are shown and the page says so.
"""
from __future__ import annotations

import json
import os
import random
import re
from datetime import date, timedelta

import numpy as np
import pandas as pd

from ..tables import kpi, notice, table

BUCKETS = ["0-30 days", "31-60 days", "61-90 days", "91-180 days", "181-365 days", "Over 365 days"]
Q = [f"q{i}" for i in range(1, 7)]
V = [f"v{i}" for i in range(1, 7)]
def design_series(code: str) -> str:
    """The two-digit prefix of the design code ("70- 10110/S" -> "Series 70"). The EasyTrade category is only an HSN
    code and descriptions are free text, so the code prefix is the one exact grouping the data offers."""
    m = re.match(r"\s*(\d{2})\s*-", str(code or ""))
    return f"Series {m.group(1)}" if m else "No series"


def load_snapshot():
    folder = os.getenv("SQL_SNAPSHOT_DIR", "").strip()
    path = os.path.join(folder, "stock_ageing.json") if folder else ""
    if path and os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            return {**json.load(fh), "demo": False}
    return demo_snapshot()


def demo_snapshot(seed: int = 7):
    rng = random.Random(seed)
    names = ["KURTA WITH PANT", "CO-ORD SET", "GOWN DRESS", "KAFTAN", "KURTA PANT DUPATTA", "PRINTED TOP"]
    as_on = date(2026, 11, 25)
    items = []
    for i in range(220):
        age = int(rng.choice([10, 20, 45, 75, 130, 250, 500]))
        b = rng.choice([1, 2, 3, 4, 6, 10, 18, 30])
        rate = rng.randint(400, 2200)
        slot = 0 if age <= 30 else 1 if age <= 60 else 2 if age <= 90 else 3 if age <= 180 else 4 if age <= 365 else 5
        row = {"c": "620419", "p": "Suit Stitched", "d": f"{rng.choice([11, 70, 99])}- {1000 + i}", "n": f"DEMO {rng.choice(names)} {i}", "b": b,
               "oi": str(as_on - timedelta(days=age)), "li": str(as_on - timedelta(days=age)), "wa": age}
        row.update({k: 0 for k in Q + V})
        row[Q[slot]], row[V[slot]] = b, b * rate
        items.append(row)
    return {"as_on": str(as_on), "source": "made-up demo rows", "unit": "PCS", "items": items, "demo": True,
            "control": {"items": len(items), "qty": sum(x["b"] for x in items)}}


def _frame(snapshot):
    d = pd.DataFrame(snapshot["items"])
    if d.empty:
        return d
    for c in Q + V + ["b", "wa"]:
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0.0)
    d["type"] = d["d"].map(design_series)
    small = d["type"].value_counts()
    d.loc[d["type"].isin(small[small < 30].index) & (d["type"] != "No series"), "type"] = "Smaller series"
    d["qty"] = d["b"]
    d["value"] = d[V].sum(axis=1)
    oldest = np.zeros(len(d), dtype=int)
    for i, c in enumerate(Q):                       # the oldest bucket that still holds pcs
        oldest = np.where(d[c] > 0, i, oldest)
    d["oldest_bucket"] = [BUCKETS[i] for i in oldest]
    return d


def _share(a, b) -> float:
    return float(a / b * 100) if b else 0.0


def _inr(v) -> str:
    return f"₹{v / 1e7:,.2f} Cr" if v >= 1e7 else f"₹{v / 1e5:,.2f} L" if v >= 1e5 else f"₹{v:,.0f}"


def stock_ageing_dashboard(snapshot, f):
    d = _frame(snapshot)
    head = {"as_on": pd.Timestamp(snapshot["as_on"]).strftime("%d %b %Y"), "source": snapshot.get("source", ""),
            "demo": bool(snapshot.get("demo"))}
    notices = [notice("Demo rows: set SQL_SNAPSHOT_DIR to show the EasyTrade snapshot.", "warning")] if head["demo"] else []
    if d.empty:
        return {**head, "empty": True, "notices": notices}
    options = {"type": sorted(d["type"].unique()), "age": BUCKETS}
    x = d
    if f.get("type"):
        x = x[x["type"].isin(f["type"])]
    if f.get("age"):
        x = x[x["oldest_bucket"].isin(f["age"])]
    q = (f.get("q") or [""])[0].strip().lower()
    if q:
        x = x[x["d"].str.lower().str.contains(q, regex=False) | x["n"].str.lower().str.contains(q, regex=False)]
    if x.empty:
        return {**head, "options": options, "no_match": True, "notices": notices}

    qty, value = float(x["qty"].sum()), float(x["value"].sum())
    bq = [float(x[c].sum()) for c in Q]
    bv = [float(x[c].sum()) for c in V]
    old_q, old_v = sum(bq[4:]), sum(bv[4:])
    avg_age = float((x["wa"] * x["qty"]).sum() / qty) if qty else 0.0
    kpis = [
        kpi("Closing stock", qty, "pcs", id="qty", hint=f"{len(x):,} designs"),
        kpi("Stock value", value, "", "inr", id="value", hint="Inward cost, before GST"),
        kpi("Average age", round(avg_age), "days", id="age", hint="Weighted by pcs"),
        kpi("Over 180 days", old_q, "pcs", id="old_qty", tone="alert", hint=f"{_share(old_q, qty):.1f}% of stock"),
        kpi("Value over 180 days", old_v, "", "inr", id="old_value", tone="alert", hint=f"{_share(old_v, value):.1f}% of value"),
        kpi("Over 365 days", bq[5], "pcs", id="dead_qty", tone="alert", hint=f"{_inr(bv[5])} at cost"),
        kpi("Fresh (0-30 days)", bq[0], "pcs", id="fresh", hint=f"{_share(bq[0], qty):.1f}% of stock"),
    ]

    bt = pd.DataFrame({"Age": BUCKETS, "Pcs": bq, "Pcs %": [_share(v, qty) for v in bq],
                       "Value": bv, "Value %": [_share(v, value) for v in bv]})
    bt.loc[len(bt)] = ["TOTAL", qty, 100.0, value, 100.0]

    g = x.groupby("type")
    tt = pd.DataFrame({"Design series": list(g.groups)})
    tt["Designs"] = g.size().reindex(tt["Design series"]).to_numpy()
    tt["Pcs"] = g["qty"].sum().reindex(tt["Design series"]).to_numpy()
    tt["Value"] = g["value"].sum().reindex(tt["Design series"]).to_numpy()
    over = x.assign(o=x[V[4]] + x[V[5]]).groupby("type")["o"].sum()
    tt["Value over 180 days"] = over.reindex(tt["Design series"]).to_numpy()
    tt["Over 180 %"] = [_share(a, b) for a, b in zip(tt["Value over 180 days"], tt["Value"])]
    tt = tt.sort_values("Value", ascending=False).reset_index(drop=True)
    type_order = list(tt["Design series"])
    tt.loc[len(tt)] = ["TOTAL", len(x), qty, value, old_v, _share(old_v, value)]

    stuck = x.assign(oq=x[Q[4]] + x[Q[5]], ov=x[V[4]] + x[V[5]])
    stuck = stuck[stuck["oq"] > 0].sort_values(["ov", "oq"], ascending=False)

    def design_table(r, extra=None):
        out = {"Design": r["d"], "Description": r["n"], "Series": r["type"], "Pcs": r["qty"], "Value": r["value"]}
        out.update(extra or {})
        return pd.DataFrame(out)

    top = stuck.head(25)
    all_rows = x.sort_values(["value", "qty"], ascending=False)
    zero = int((x["value"] <= 0).sum())
    if zero:
        notices.append(notice(f"{zero} design(s) have stock but no inward rate in EasyTrade, so they count as ₹0 in value.",
                              "info"))
    ctl = snapshot.get("control") or {}
    full_qty = float(d["qty"].sum())
    if ctl.get("qty") is not None and abs(full_qty - ctl["qty"]) > 0.5:
        notices.append(notice(f"The snapshot adds up to {full_qty:,.0f} pcs but the EasyTrade ledger total was "
                              f"{ctl['qty']:,.0f}.", "warning"))

    return {
        **head,
        "options": options,
        "notices": notices,
        "kpis": kpis,
        "summary": {"qty": qty, "value": value, "designs": int(len(x)), "avg_age": round(avg_age),
                    "old_qty": old_q, "old_value": old_v, "old_value_pct": _share(old_v, value)},
        "insights": _insights(x, qty, value, bq, bv, tt, stuck),
        "charts": {
            "value_by_age": [{"label": b, "value": v} for b, v in zip(BUCKETS, bv)],
            "qty_by_age": [{"label": b, "value": v} for b, v in zip(BUCKETS, bq)],
            "type_age": {"rows": type_order, "columns": BUCKETS,
                         "values": [[float(x.loc[x["type"] == t, c].sum()) for c in Q] for t in type_order]},
        },
        "tables": {
            "ages": table(bt, {"Pcs %": "pct", "Value %": "pct", "Value": "inr"}, sort=False),
            "types": table(tt, {"Value": "inr", "Value over 180 days": "inr", "Over 180 %": "pct"}, sort=False),
            "stuck": table(design_table(top, {"Pcs over 180 days": top["oq"], "Value over 180 days": top["ov"],
                                              "Oldest inward": pd.to_datetime(top["oi"]), "Avg age (days)": top["wa"]}),
                           {"Value": "inr", "Value over 180 days": "inr", "Oldest inward": "date"}, sort=False),
            "designs": table(design_table(all_rows, {"Avg age (days)": all_rows["wa"], "Oldest age band": all_rows["oldest_bucket"],
                                                     "Last inward": pd.to_datetime(all_rows["li"])}),
                             {"Value": "inr", "Last inward": "date"}, sort=False),
        },
    }


def _insights(x, qty, value, bq, bv, tt, stuck):
    out = [f"{sum(bq[:3]) / qty * 100:.0f}% of pieces are 90 days old or less; {sum(bv[4:]) / value * 100 if value else 0:.0f}% "
           f"of the value ({_inr(sum(bv[4:]))}) has been in stock for over 180 days."]
    if bq[5]:
        out.append(f"{bq[5]:,.0f} pcs ({_inr(bv[5])} at cost) are over a year old: candidates for clearance.")
    body = tt[tt["Design series"] != "TOTAL"]
    if len(body) > 1:
        worst = body.loc[body["Value over 180 days"].idxmax()]
        if worst["Value over 180 days"] > 0:
            out.append(f"{worst['Design series']} holds the most old stock: {_inr(worst['Value over 180 days'])} over 180 days "
                       f"({worst['Over 180 %']:.0f}% of its value).")
    if len(stuck) and sum(bv[4:]):
        top = stuck.head(25)["ov"].sum()
        out.append(f"The 25 designs with the most old value hold {top / sum(bv[4:]) * 100:.0f}% of everything over 180 days.")
    return out
