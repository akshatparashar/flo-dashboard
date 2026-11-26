"""Unsold Inventory Insights: the extra section of the Stock Ageing page.

Two different questions, kept apart so neither is mistaken for the other:

1. Piece age - how long has each remaining piece been waiting? (the FIFO age bands of the stock snapshot).
2. No-sale time - how long has a design's stock been sitting without the design selling at all?
   days = as-on date - the later of (last sale date, arrival of the oldest piece still in stock)
   The second part matters: a design that last sold two years ago, ran out and was restocked last week has been
   waiting one week, not two years. A design with no sale on record counts from its oldest piece.

"More than N days" totals are nested (everything over 90 days is also over 30), so they are never added together.
The exclusive bands do add up to the stock, with each design counted once.

Needs the snapshot's sales fields (ls = last sale date, s90 = pcs sold in 90 days, sa = pcs sold on record, rsr /
radj = pcs of the closing stock whose FIFO lot is a sales return / a stock count or journal entry). A snapshot without
them (`has_sales` false) shows piece age only: nothing about selling is guessed.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..tables import table

THRESHOLDS = [30, 90, 180, 365]
# first FIFO bucket (index into q1..q6) that is entirely older than each threshold
FIRST_BUCKET = {30: 1, 90: 3, 180: 4, 365: 5}
BANDS = [("0-30 days", 0, 30), ("31-90 days", 31, 90), ("91-180 days", 91, 180), ("181-365 days", 181, 365),
         ("Over 365 days", 366, 10**6)]


def _share(a, b) -> float:
    return float(a / b * 100) if b else 0.0


def _inr(v) -> str:
    return f"₹{v / 1e7:,.2f} Cr" if v >= 1e7 else f"₹{v / 1e5:,.2f} L" if v >= 1e5 else f"₹{v:,.0f}"


def _num(x, name) -> pd.Series:
    return pd.to_numeric(x[name], errors="coerce").fillna(0.0) if name in x else pd.Series(0.0, index=x.index)


def _date(x, name) -> pd.Series:
    return pd.to_datetime(x[name], errors="coerce") if name in x else pd.Series(pd.NaT, index=x.index)


def unsold_insights(x: pd.DataFrame, as_on, has_sales: bool, q: list[str], v: list[str]) -> dict:
    """x = the (already filtered) stock rows of the Stock Ageing page, one per design."""
    as_on = pd.Timestamp(as_on).normalize()
    qty, value = float(x["qty"].sum()), float(x["value"].sum())
    older_q = {n: x[q[FIRST_BUCKET[n]:]].sum(axis=1) for n in THRESHOLDS}
    older_v = {n: x[v[FIRST_BUCKET[n]:]].sum(axis=1) for n in THRESHOLDS}

    idle = never = None
    if has_sales:
        last_sale, oldest = _date(x, "ls"), _date(x, "oi")
        since = last_sale.where(last_sale.notna() & (oldest.isna() | (last_sale > oldest)), oldest)
        idle = (as_on - since).dt.days.clip(lower=0)
        never = last_sale.isna()

    cards = []
    for n in THRESHOLDS:
        card = {"days": n, "pcs": float(older_q[n].sum()), "value": float(older_v[n].sum()),
                "designs": int((older_q[n] > 0).sum()), "pcs_pct": _share(older_q[n].sum(), qty),
                "value_pct": _share(older_v[n].sum(), value), "no_sale": None}
        if has_sales:
            m = idle > n
            card["no_sale"] = {"designs": int(m.sum()), "pcs": float(x.loc[m, "qty"].sum()),
                               "value": float(x.loc[m, "value"].sum()), "value_pct": _share(x.loc[m, "value"].sum(), value)}
        cards.append(card)

    labels = [f"Over {n} days" for n in THRESHOLDS]
    series = [{"name": "Pieces older than", "values": [c["value"] for c in cards]}]
    if has_sales:
        series.append({"name": "Designs with no sale for", "values": [c["no_sale"]["value"] for c in cards]})
    out = {"has_sales": bool(has_sales), "cards": cards, "totals": {"pcs": qty, "value": value, "designs": int(len(x))},
           "compare": {"categories": labels, "series": series}, "bands": [], "never": None, "heat": None,
           "dated_from": {"returns": float(_num(x, "rsr").sum()), "adjustments": float(_num(x, "radj").sum())}}

    if has_sales:
        names = [b[0] for b in BANDS]
        band = pd.Series("Unknown", index=x.index, dtype=object)
        for name, lo, hi in BANDS:
            band[(idle >= lo) & (idle <= hi)] = name
        if (band == "Unknown").any():
            names.append("Unknown")
        out["bands"] = [{"label": b, "designs": int((band == b).sum()), "pcs": float(x.loc[band == b, "qty"].sum()),
                         "value": float(x.loc[band == b, "value"].sum())} for b in names]
        out["never"] = {"designs": int(never.sum()), "pcs": float(x.loc[never, "qty"].sum()),
                        "value": float(x.loc[never, "value"].sum()), "value_pct": _share(x.loc[never, "value"].sum(), value)}
        order = list(x.groupby("type")["value"].sum().sort_values(ascending=False).index)
        out["heat"] = {"rows": order, "columns": names,
                       "values": [[float(x.loc[(x["type"] == t) & (band == b), "qty"].sum()) for b in names] for t in order]}

    # product-level list: one row per design, longest waiting first
    # the figures come first; the long description goes last so it cannot push them off screen
    t = pd.DataFrame({"Design": x["d"]})
    if has_sales:
        t["Days without sale"] = idle
        t["Last sale"] = _date(x, "ls")
    t["Pcs"] = x["qty"]
    t["Value"] = x["value"]
    t["Oldest piece (days)"] = (as_on - _date(x, "oi")).dt.days
    if has_sales:
        t["Sold in 90 days"] = _num(x, "s90")
        t["Sold on record"] = _num(x, "sa")
    for n in THRESHOLDS:
        t[f"Pcs over {n}d"] = older_q[n]
    t["Series"] = x["type"]
    t["Description"] = x["n"]
    t = t.sort_values(["Days without sale" if has_sales else "Oldest piece (days)", "Value", "Design"],
                      ascending=[False, False, True], na_position="last")
    out["table"] = table(t, {"Value": "inr", "Last sale": "date"}, sort=False)
    out["insights"] = _insights(out)
    return out


def _insights(u: dict) -> list[str]:
    c = {card["days"]: card for card in u["cards"]}
    lines = [f"{c[90]['pcs']:,.0f} pcs ({c[90]['pcs_pct']:.0f}%) have been in stock for more than 90 days; "
             f"{c[365]['pcs']:,.0f} pcs for more than a year."]
    if u["has_sales"]:
        n = c[90]["no_sale"]
        lines.append(f"{n['designs']:,} designs have not sold for over 90 days while their stock waited: "
                     f"{n['pcs']:,.0f} pcs, {_inr(n['value'])} at cost ({n['value_pct']:.0f}% of stock value).")
        never = u["never"]
        if never["designs"]:
            lines.append(f"{never['designs']:,} designs in stock have no sale on record at all: {never['pcs']:,.0f} pcs, "
                         f"{_inr(never['value'])} ({never['value_pct']:.0f}% of value). Some may simply be new.")
    return lines
