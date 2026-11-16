"""Table helpers: TOTAL rows, row ordering and conversion of DataFrames to JSON for the frontend.

add_total / with_total / order_rows are ported unchanged from the legacy app.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

TOTAL_LABELS = {"TOTAL", "GRAND TOTAL", "ALL FABRICATORS"}
RATE_APPROVAL = {"good": 50, "mid": 25}     # Approval % / RCVD % / On-Time %: green >= 50, amber >= 25
RATE_TARGET = {"good": 100, "mid": 75}      # target achievement: green >= 100, amber >= 75


def add_total(df, label_col, label="TOTAL"):
    tot = {c: (df[c].sum() if pd.api.types.is_numeric_dtype(df[c]) else "") for c in df.columns}
    tot[label_col] = label
    return pd.concat([df, pd.DataFrame([tot])], ignore_index=True)


def with_total(df, label_col, pct=None, label="TOTAL"):
    """Appends a TOTAL row. pct=(pct_col, numerator_col, denominator_col) is recomputed, never summed."""
    if df.empty:
        return df
    skip = {label_col} | ({pct[0]} if pct else set())
    row = {label_col: label}
    for c in df.columns:
        if c not in skip and pd.api.types.is_numeric_dtype(df[c]):
            row[c] = df[c].sum()
    if pct:
        den = row.get(pct[2], 0)
        row[pct[0]] = (row.get(pct[1], 0) / den * 100) if den else 0.0
    return pd.concat([df, pd.DataFrame([row])], ignore_index=True)


def is_pinned(label) -> bool:
    t = str(label).strip().upper()
    return t in TOTAL_LABELS or t.startswith("ALL OVER")


def order_rows(df, key_col=None, sort=True, sort_abs=False):
    """Rows sorted by the important column (high -> low); TOTAL / ALL OVER rows stay at the bottom.
    sort=False keeps the existing (month / timeline) order."""
    if df is None or df.empty or not key_col or key_col not in df.columns or not sort:
        return df
    pinned = df.iloc[:, 0].map(is_pinned)
    body, tail = df[~pinned], df[pinned]
    vals = pd.to_numeric(body[key_col], errors="coerce")
    if sort_abs:
        vals = vals.abs()
    order = vals.fillna(-np.inf).sort_values(ascending=False, kind="mergesort").index
    return pd.concat([body.loc[order], tail], ignore_index=True)


def _cell(v):
    if v is None:
        return None
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    if isinstance(v, (int, np.integer)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        f = float(v)
        return None if math.isnan(f) or math.isinf(f) else f
    if isinstance(v, (np.bool_, bool)):
        return bool(v)
    if isinstance(v, pd.Timestamp):
        return None if pd.isna(v) else v.strftime("%d/%m/%Y")
    if v is pd.NaT:
        return None
    return str(v)


def table(df, fmt=None, key_col=None, sort=True, sort_abs=False, rates=None, title=None, note=None):
    """DataFrame -> {"columns": [...], "rows": [[...]], "meta": [...]} in display order.

    fmt   : {column: "text" | "int" | "dec" | "pct" | "inr" | "date"}; numeric columns default to "int".
    rates : {column: {"good": x, "mid": y}} - cells coloured green / amber / red like the sheet.
    meta  : per row {"kind": "total" | "ref" | None, "muted": bool} (muted = row has no data).
    """
    fmt = dict(fmt or {})
    rates = dict(rates or {})
    if df is None or df.empty:
        return {"title": title, "note": note, "columns": [], "rows": [], "meta": [], "key_col": None,
                "sorted": False}
    if key_col not in df.columns:
        key_col = None
    df = order_rows(df, key_col, sort, sort_abs)
    cols = list(df.columns)
    numeric = {c: pd.api.types.is_numeric_dtype(df[c]) for c in cols}
    columns = []
    for i, c in enumerate(cols):
        f = fmt.get(c) or ("int" if numeric[c] and i > 0 else "text")
        col = {"key": c, "label": c, "format": f}
        if c in rates:
            col["rate"] = rates[c]
        columns.append(col)
    pct_cols = {c for c in cols if fmt.get(c) == "pct"}
    value_cols = [c for c in cols[1:] if numeric[c] and c not in pct_cols]
    rows, meta = [], []
    for _, r in df.iterrows():
        first = str(r.iloc[0]).strip().upper()
        kind = "total" if first in TOTAL_LABELS else ("ref" if first.startswith("ALL OVER") else None)
        has_data = any(float(r[c] or 0) != 0 for c in value_cols if pd.notna(r[c])) if value_cols else True
        rows.append([_cell(r[c]) for c in cols])
        meta.append({"kind": kind, "muted": not has_data})
    return {"title": title, "note": note, "columns": columns, "rows": rows, "meta": meta, "key_col": key_col,
            "sorted": bool(key_col and sort)}


def records(df, cols=None):
    """DataFrame -> list of plain dicts (for chart series)."""
    if df is None or df.empty:
        return []
    cols = cols or list(df.columns)
    return [{c: _cell(row[c]) for c in cols} for _, row in df.iterrows()]


def kpi(label, value, unit="", fmt="int", hint=None, tone=None, id=None):
    """One headline figure. value is numeric (or text when fmt == "text")."""
    out = {"id": id or label.lower().replace(" ", "_"), "label": label, "value": _cell(value) if fmt != "text" else value,
           "unit": unit, "format": fmt}
    if hint:
        out["hint"] = hint
    if tone:
        out["tone"] = tone
    return out


def notice(text, kind="info"):
    return {"kind": kind, "text": text}
