"""FW ORDER'S table of the Master Sheet's DASHBOARD tab (Month / Order pcs / Dispatched / Pending / Overall dispatched).

The table sits in the middle of a busy tab (other tables are beside it), so it is found by its title cell "FW ORDER'S"
and its header row, never by fixed cell addresses. Shown on the Clients Order Status page.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

import pandas as pd

from ..core import FY_START_YEAR, norm_key
from ..tables import notice, table

TAB = "DASHBOARD"
COLUMNS = {"month": "MONTH", "order": "ORDERPCS", "dispatched": "DISPATCHEDPCS", "pending": "PENDINGPCS",
           "overall": "OVERALLDISPATCHEDPCS"}
LABELS = {"month": "Month", "order": "Order pcs", "dispatched": "Dispatched pcs", "pending": "Pending pcs",
          "overall": "Overall dispatched pcs"}


def _short(m: str) -> str:
    """Jan-2026 -> Jan-26 (the chart axis uses the same short month as the other charts)."""
    return re.sub(r"^([A-Za-z]{3})[A-Za-z]*-(?:20)?(\d{2})$", r"\g<1>-\g<2>", m.strip())


def _num(v) -> float:
    s = str(v).replace(",", "").replace("₹", "").strip()
    try:
        return float(s)
    except ValueError:
        return 0.0


def _month_text(v) -> str:
    """A MONTH cell as "Apr-2026". The sheet holds real dates, which the API returns as serial numbers (46138), so
    those are turned back into the month they stand for; text cells ("Apr-2026") are kept as they are."""
    if isinstance(v, (int, float)) and not isinstance(v, bool) and 20000 < v < 80000:
        return (datetime(1899, 12, 30) + timedelta(days=float(v))).strftime("%b-%Y")
    s = str(v).strip()
    if re.fullmatch(r"\d{5}(\.0+)?", s) and 20000 < float(s) < 80000:
        return _month_text(float(s))
    return s


def parse_fw_orders(grid):
    """Raw grid -> {"rows": [{month, order, dispatched, pending, overall}], "sheet_total": {...} | None}."""
    title = header = None
    for r, row in enumerate(grid or []):
        for c, v in enumerate(row):
            if title is None and "FWORDER" in norm_key(v):
                title = (r, c)
        if title is not None and r >= title[0]:
            keys = [norm_key(v) for v in row]
            if "MONTH" in keys and any(k.startswith("ORDER") for k in keys) and "DISPATCHEDPCS" in keys:
                header = (r, keys)
                break
    if header is None:
        return {"rows": [], "sheet_total": None}
    hr, keys = header
    # Other tables sit on the same rows (their own MONTH / ORDER QTY headers come first), so every column is looked up
    # from the title's column onwards.
    c0 = title[1]
    first = lambda pred: next((i for i, k in enumerate(keys) if i >= c0 and pred(k)), None)
    at = {name: first(lambda k, w=want: k == w) for name, want in COLUMNS.items()}
    at = {n: i for n, i in at.items() if i is not None}
    if "order" not in at:
        at["order"] = first(lambda k: k.startswith("ORDER"))
    rows, total = [], None
    for row in grid[hr + 1:]:
        cell = lambda n: row[at[n]] if n in at and at[n] is not None and at[n] < len(row) else ""
        month = _month_text(cell("month"))
        vals = {n: _num(cell(n)) for n in ("order", "dispatched", "pending", "overall")}
        if norm_key(month).startswith("TOTAL"):
            total = vals                # the sheet's own TOTAL line ("TOTAL" or no month) ends the table
            break
        if not month:
            if any(vals.values()) and total is None:
                total = vals            # the sheet's own TOTAL line has no month; it ends the table
                break
            if not any(vals.values()):
                break
            continue
        rows.append({"month": month, **vals})
    return {"rows": rows, "sheet_total": total}


def _from_april(month: str) -> bool:
    """Only months from April of the financial year on are shown (the sheet also lists Jan-Mar of the year before)."""
    d = pd.to_datetime(str(month).strip(), format="%b-%Y", errors="coerce")
    if pd.isna(d):
        d = pd.to_datetime(str(month).strip(), format="%b-%y", errors="coerce")
    return True if pd.isna(d) else d >= pd.Timestamp(FY_START_YEAR, 4, 1)


def fw_orders_dashboard(parsed):
    all_rows = parsed["rows"]
    rows = [r for r in all_rows if _from_april(r["month"])]
    if not rows:
        return None
    df = pd.DataFrame(rows).rename(columns=LABELS)
    sums = {c: float(df[c].sum()) for c in list(LABELS.values())[1:]}
    # the sheet's total line covers every month it lists, so it is compared with the sum of all of them
    all_sums = {LABELS[k]: float(sum(r[k] for r in all_rows)) for k in LABELS if k != "month"}
    total = {"Month": "TOTAL", **sums}
    full = pd.concat([df, pd.DataFrame([total])], ignore_index=True)
    checks = []
    st = parsed.get("sheet_total")
    if st:
        for key, label in LABELS.items():
            if key != "month" and abs(st[key] - all_sums[label]) > 0.5:
                checks.append(notice(f"FW ORDER'S: {label} adds up to {all_sums[label]:,.0f} but the sheet's total "
                                      f"line says {st[key]:,.0f}.", "warning"))
    done = sums["Dispatched pcs"] + sums["Pending pcs"]
    return {
        "table": table(full, key_col="Order pcs", sort=False, title="FW ORDER'S"),
        "chart": {"categories": [_short(r["month"]) for r in rows],
                  "series": [{"name": "Order pcs", "values": [r["order"] for r in rows]},
                             {"name": "Dispatched pcs", "values": [r["dispatched"] for r in rows]},
                             {"name": "Pending pcs", "values": [r["pending"] for r in rows]}]},
        "overall": {"categories": [_short(r["month"]) for r in rows], "values": [r["overall"] for r in rows]},
        "totals": {"order": sums["Order pcs"], "dispatched": sums["Dispatched pcs"], "pending": sums["Pending pcs"],
                   "overall": sums["Overall dispatched pcs"],
                   "dispatched_pct": round(sums["Dispatched pcs"] / done * 100, 1) if done else 0.0},
        "checks": checks,
    }
