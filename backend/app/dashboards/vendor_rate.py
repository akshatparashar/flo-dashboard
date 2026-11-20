"""Vendor Rate dashboard (FABRIC PO 11).

Ported from the Vendor Rate tab of the Streamlit dashboard (github.com/design355/sample-production-dashboard, kept as
legacy/streamlit_app.py; tests/test_parity_vendor_rate.py runs both on the same rates and compares every number).
The old app kept its rates in code; here they are read from the sheet:

  Rate_Data       the tidy rate list (Vendor | S. No. | Fabric (Original) | Fabric Category | 44" | 60" | 36" |
                  Per Pc / Special). Columns are found by header text. The sheet's own Fabric Category column is not
                  used: categories come from the fabric name with the old app's rules (vr_category).
  NEW RATE SHEET  the hand-filled rate cards ("RV" above "S. NO. | FABRIC | 44 WIDTH | 60 WIDTH"). Two jobs: a vendor
                  whose card says "44/36 WIDTH" has its 44" column read as the 44/36" rate (as the old app did), and
                  fabrics / rates on a card that differ from Rate_Data are listed under Sheet checks.

Rules (same as the old app):
  * a rate of 0 means "pending", blank means "not offered"; neither counts in any average, minimum or maximum;
  * a per-piece rate is never mixed with per-metre rates; "120/125" = per piece 120, upper end 125;
  * averages cover the 44" and 60" columns only; Min / Max cover every per-metre column.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from ..core import norm_key
from ..tables import kpi, notice, table

VR_METER_COLS = ['36"', '44"', '60"', '44/36"']          # per-metre rates (by width)
VR_PC_COL = "Per Pc"                                      # per-piece rate (never mixed with per-metre averages)
VR_PC_MAX = "Per Pc Max"                                  # upper end when a piece rate is a range (120/125)
VR_PRICE_COLS = VR_METER_COLS + [VR_PC_COL]
WIDTH_OPTIONS = ['Has 44"', 'Has 60"', 'Has 36"', "Per Piece only"]
RATE_TAB_NAMES = ["Rate_Data", "Rate Data"]
RATE_TAB_REGEX = r"rate\s*_?\s*data"
CARD_TAB_NAMES = ["NEW RATE SHEET", "Rate Sheet"]
CARD_TAB_REGEX = r"rate\s*sheet"
INR = "inr_full"


def vr_category(fabric, has_pc=False):
    """Clean fabric group for filters (spelling variations -> one category). Same rules as the old app."""
    t = str(fabric).upper()
    if has_pc or re.search(r"HAND\s*WORK|TOP\s*/\s*DUP|\bP(ER|R)\s*PC\b", t):
        return "Hand Work / Dupatta"
    for pattern, name in (
        (r"RUSSI", "Russian Silk"), (r"CHANDERI", "Mul Chanderi"), (r"CHINON", "Chinon"),
        (r"ORGENZA|ORGANZA", "Organza"), (r"MUSLIN", "Muslin"), (r"CREPE", "Crepe"),
        (r"LILEN|LINEN", "Linen"), (r"SANTOON", "Santoon"), (r"SILK", "Silk"), (r"COTTON", "Cotton"),
    ):
        if re.search(pattern, t):
            return name
    return "Other"


def category_in_text(text: str) -> str | None:
    """The fabric category a question names ("musline", "russian silk", "chanderi"), or None."""
    t = str(text).upper()
    if re.search(r"HAND\s*WORK|DUPATTA|\bPER\s*PC\b", t):
        return "Hand Work / Dupatta"
    for pattern, name in (
        (r"RUSS?I", "Russian Silk"), (r"CHANDERI", "Mul Chanderi"), (r"CHINON", "Chinon"),
        (r"ORGENZA|ORGANZA", "Organza"), (r"MUSLI", "Muslin"), (r"CREPE", "Crepe"),
        (r"LILEN|LINEN", "Linen"), (r"SANTOON", "Santoon"), (r"SILK", "Silk"), (r"COTTON", "Cotton"),
    ):
        if re.search(pattern, t):
            return name
    return None


def _vr_num(v):
    """Cell -> (value or None, upper value or None). Handles 120, '₹1,200', 'N/A', '120/125'."""
    if v is None:
        return None, None
    if isinstance(v, (int, float, np.integer, np.floating)) and not isinstance(v, bool):
        return (None, None) if pd.isna(v) else (float(v), None)
    s = str(v).replace("₹", "").replace(",", "").strip()
    nums = re.findall(r"\d+(?:\.\d+)?", s)
    if not nums:
        return None, None
    return float(nums[0]), (float(nums[1]) if len(nums) > 1 else None)


def vr_build(records):
    """records -> tidy DataFrame (0 / blank rates are kept out of every average and min / max)."""
    out = []
    for r in records:
        vendor, fabric = str(r.get("Vendor", "")).strip(), str(r.get("Fabric", "")).strip()
        if not vendor or not fabric:
            continue
        vals, pending = {}, []
        for c in VR_PRICE_COLS:
            v, _hi = _vr_num(r.get(c))
            if v == 0:
                pending.append(c)
                v = None
            vals[c] = v
        pc_max = _vr_num(r.get(VR_PC_MAX))[0] or _vr_num(r.get(VR_PC_COL))[1]
        if all(v is None for v in vals.values()) and not pending:
            pending = ["ALL"]                      # every rate blank
        status = "OK"
        if pending:
            status = "Pending / N/A" + ("" if pending == ["ALL"] else f" ({', '.join(pending)})")
        note = ""
        if vals[VR_PC_COL] and pc_max and pc_max != vals[VR_PC_COL]:
            note = f"Range ₹{vals[VR_PC_COL]:,.0f}–{pc_max:,.0f} per pc"
        row = {"Vendor": vendor, "Fabric": fabric,
               "Category": vr_category(fabric, has_pc=vals[VR_PC_COL] is not None)}
        row.update({c: (np.nan if vals[c] is None else vals[c]) for c in VR_PRICE_COLS})
        row.update({VR_PC_MAX: (np.nan if not pc_max else pc_max), "Pending Cells": len(pending),
                    "Status": status, "Note": note})
        out.append(row)
    cols = ["Vendor", "Fabric", "Category"] + VR_PRICE_COLS + [VR_PC_MAX, "Pending Cells", "Status", "Note"]
    return pd.DataFrame(out, columns=cols)


def vr_filter(d, vendor, cat, width, query):
    """vendor / cat: list of names (empty = all); width: one of WIDTH_OPTIONS or ""; query: free text."""
    x = d
    if vendor:
        x = x[x["Vendor"].isin(vendor)]
    if cat:
        x = x[x["Category"].isin(cat)]
    if width == 'Has 44"':
        x = x[x['44"'].notna() | x['44/36"'].notna()]
    elif width == 'Has 60"':
        x = x[x['60"'].notna()]
    elif width == 'Has 36"':
        x = x[x['36"'].notna() | x['44/36"'].notna()]
    elif width == "Per Piece only":
        x = x[x[VR_PC_COL].notna() & ~x[VR_METER_COLS].notna().any(axis=1)]
    tokens = [t for t in re.split(r"\s+", str(query or "").lower().strip()) if t]
    if tokens:
        hay = (x["Vendor"] + " " + x["Fabric"] + " " + x["Category"]).str.lower()
        for t in tokens:
            x = x[hay.loc[x.index].str.contains(re.escape(t))]
    return x


def vr_lowest(x, col):
    """(rate, vendor, fabric) of the lowest rate in a column, or None."""
    s = x[col].dropna()
    if s.empty:
        return None
    i = s.idxmin()
    return float(s[i]), x.loc[i, "Vendor"], x.loc[i, "Fabric"]


def vr_benchmark(x):
    rows = []
    for vendor, g in x.groupby("Vendor", sort=False):
        meter = g[VR_METER_COLS].stack()
        rows.append({
            "Vendor": vendor,
            "Total Items": len(g),
            'Avg 44" Rate': g['44"'].mean(),
            'Avg 60" Rate': g['60"'].mean(),
            "Min Rate": meter.min() if not meter.empty else np.nan,
            "Max Rate": meter.max() if not meter.empty else np.nan,
            "Per Pc Items": int(g[VR_PC_COL].notna().sum()),
            "Pending": int(g["Pending Cells"].sum()),
        })
    return pd.DataFrame(rows)


def vr_compare(c, widths):
    """Per vendor: cheapest fabric + rate for every width, plus Best Price badge."""
    rows = []
    for vendor, g in c.groupby("Vendor", sort=False):
        row = {"Vendor": vendor}
        for w in widths:
            s = g[w].dropna()
            if s.empty:
                row[f"{w} Rate"], row[f"{w} Fabric"] = np.nan, ""
            else:
                i = s.idxmin()
                row[f"{w} Rate"], row[f"{w} Fabric"] = s[i], g.loc[i, "Fabric"]
        rows.append(row)
    cmp = pd.DataFrame(rows)
    best = {w: cmp[f"{w} Rate"].min() for w in widths}
    cmp["Best Price"] = [
        " ".join(f"★ {w}" for w in widths if pd.notna(r[f"{w} Rate"]) and r[f"{w} Rate"] == best[w])
        for _, r in cmp.iterrows()
    ]
    cmp = cmp.sort_values(f"{widths[0]} Rate", na_position="last", kind="mergesort").reset_index(drop=True)
    order = ["Vendor"] + [c for w in widths for c in (f"{w} Rate", f"{w} Fabric")] + ["Best Price"]
    return cmp[order], best


# ------------------------------------------------------------------------------------------------ Rate_Data
_RD_FIELDS = [  # field -> normalised header must start with one of these (first match wins)
    ("vendor", ("VENDOR",)), ("sno", ("SNO", "SRNO")), ("fabric", ("FABRICORIGINAL", "FABRIC")),
    ("category", ("FABRICCATEGORY", "CATEGORY")), ('44"', ("44",)), ('60"', ("60",)), ('36"', ("36",)),
    (VR_PC_COL, ("PERPC", "SPECIAL", "PERPIECE")),
]


def _rd_header(values):
    for r, row in enumerate(values[:10]):
        keys = [norm_key(c) for c in row]
        if "VENDOR" in keys and any(k.startswith("FABRIC") for k in keys):
            cmap = {}
            for field, starts in _RD_FIELDS:
                for i, k in enumerate(keys):
                    if i in cmap.values() or not k:
                        continue
                    if any(k.startswith(s) for s in starts) and not (field == "fabric" and "CATEGORY" in k):
                        cmap[field] = i
                        break
            first = min(cmap.values())
            return r, {f: i for f, i in cmap.items() if i - first < 12}      # helper blocks further right ignored
    return None, {}


def parse_rate_data(values):
    """Rate_Data tab -> list of records (Vendor, Fabric, one key per price column) in sheet order."""
    hr, cm = _rd_header(values)
    if hr is None or "vendor" not in cm or "fabric" not in cm:
        return [], False
    recs = []
    for raw in values[hr + 1:]:
        row = list(raw) + [""] * 30
        vendor = re.sub(r"\s+", " ", str(row[cm["vendor"]] or "")).strip().upper()
        fabric = re.sub(r"\s+", " ", str(row[cm["fabric"]] or "")).strip()
        if not vendor or not fabric or norm_key(vendor) in ("VENDOR", "TOTAL"):
            continue
        rec = {"Vendor": vendor, "Fabric": fabric}
        for c in ('36"', '44"', '60"', VR_PC_COL):
            rec[c] = row[cm[c]] if c in cm else None
        recs.append({k: (None if v in ("", None) else v) for k, v in rec.items()})
    return recs, True


# ------------------------------------------------------------------------------------------------ rate cards
_SNO = {"SNO", "SRNO", "SNUMBER", "SERIALNO"}


def _card_field(header) -> str | None:
    k = norm_key(header)
    if not k:
        return None
    if k.startswith("FABRIC") or k in ("ITEM", "QUALITY"):
        return "fabric"
    if k.startswith("4436") or k.startswith("3644"):
        return '44/36"'
    if "PC" in k or "PIECE" in k or "SPECIAL" in k:
        return VR_PC_COL
    for w in ("44", "60", "36"):
        if k.startswith(w):
            return w + '"'
    return None


def parse_rate_cards(values):
    """NEW RATE SHEET: vendor blocks laid out side by side and one under another -> one entry per offering."""
    grid = [list(r) for r in values]
    width = max((len(r) for r in grid), default=0)
    grid = [r + [""] * (width - len(r)) for r in grid]
    out = []
    for r, row in enumerate(grid):
        for c, v in enumerate(row):
            if norm_key(v) not in _SNO:
                continue
            cols, j = {}, c + 1
            while j < width and norm_key(row[j]) not in _SNO:
                f = _card_field(row[j])
                if f is None:
                    break
                cols.setdefault(f, j)
                j += 1
            if "fabric" not in cols:
                continue
            extra = j if j < width and not str(row[j]).strip() else None     # unlabelled column after the headers
            col_idx = [c] + list(range(c + 1, j))                            # the block's own columns, as headed
            heads = [str(row[i]).strip() for i in col_idx]
            vendor = ""
            for up in (r - 1, r - 2):
                if up >= 0:
                    vendor = next((str(x).strip() for x in grid[up][c:j] if str(x).strip()), "")
                    if vendor:
                        break
            for k in range(r + 1, len(grid)):
                line = grid[k]
                sno, fabric = str(line[c]).strip(), re.sub(r"\s+", " ", str(line[cols["fabric"]] or "")).strip()
                if norm_key(sno) in _SNO or (not fabric and not re.fullmatch(r"\d+(\.0)?", sno)):
                    break
                if not fabric:
                    continue
                rates = [line[i] for f, i in cols.items() if f != "fabric"] + ([line[extra]] if extra else [])
                nums = sorted(x for x in (_vr_num(v)[0] for v in rates) if x)
                out.append({"vendor": vendor.upper(), "fabric": fabric, "nums": nums,
                            "wide4436": '44/36"' in cols, "head": heads,
                            "cells": [None if str(line[i]).strip() == "" else line[i] for i in col_idx]})
    return out


# ------------------------------------------------------------------------------------------------ parse
def parse_vendor_rate(grids: dict) -> dict:
    """grids: {"rates": Rate_Data values, "cards": NEW RATE SHEET values} (a missing tab -> [])."""
    recs, ok = parse_rate_data(grids.get("rates") or [])
    cards = parse_rate_cards(grids.get("cards") or [])
    source = "Rate_Data"
    if not recs and cards:                       # no Rate_Data: the rate cards are the table
        source = "NEW RATE SHEET"
        recs = []
        for cd in cards:
            rec = {"Vendor": cd["vendor"], "Fabric": cd["fabric"]}
            for c, n in zip(('44/36"' if cd["wide4436"] else '44"', '60"', '36"'), cd["nums"]):
                rec[c] = n
            recs.append(rec)
    wide = {cd["vendor"] for cd in cards if cd["wide4436"]}      # vendors whose card says "44/36 WIDTH"
    for rec in recs:
        if rec["Vendor"] in wide and rec.get('44"') not in (None, "") and not rec.get('44/36"'):
            rec['44/36"'], rec['44"'] = rec['44"'], None
    return {"d": vr_build(recs), "cards": cards, "source": source, "rate_data_found": ok}


# ------------------------------------------------------------------------------------------------ payloads
def _num(v):
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else float(v)


def _tbl(df, fmt=None, key_col=None):
    return table(df, fmt, key_col=key_col, sort=False)


RATE_FMT = {c: INR for c in VR_PRICE_COLS}
BENCH_FMT = {'Avg 44" Rate': INR, 'Avg 60" Rate': INR, "Min Rate": INR, "Max Rate": INR}


def compare_payload(d, cat):
    """The 'Compare fabric category' section for one category (always across every vendor)."""
    c = d[d["Category"] == cat]
    mw = [w for w in VR_METER_COLS if c[w].notna().any()]
    out = {"category": cat, "widths": mw, "vendors": int(c["Vendor"].nunique()), "tiles": [], "chart": None,
           "table": None, "pieces": None}
    if mw:
        cmp, best = vr_compare(c, mw)
        for w in mw:
            i = c[w].idxmin()
            out["tiles"].append({"width": w, "rate": float(best[w]), "vendor": c.loc[i, "Vendor"],
                                 "fabric": c.loc[i, "Fabric"]})
        out["chart"] = {"vendors": list(cmp["Vendor"]),
                        "series": [{"name": w, "values": [_num(r[f"{w} Rate"]) for _, r in cmp.iterrows()],
                                    "best": [bool(pd.notna(r[f"{w} Rate"]) and r[f"{w} Rate"] == best[w])
                                             for _, r in cmp.iterrows()]} for w in mw]}
        out["table"] = _tbl(cmp, {f"{w} Rate": INR for w in mw})
    pc = c[c[VR_PC_COL].notna()].sort_values(VR_PC_COL)
    if not pc.empty:
        t = pc[["Vendor", "Fabric", VR_PC_COL]].rename(columns={VR_PC_COL: "Rate / Pc"}).reset_index(drop=True)
        t["Range"] = list(pc["Note"])
        t["Best Price"] = ["★ Best Price" if v == t["Rate / Pc"].min() else "" for v in t["Rate / Pc"]]
        out["pieces"] = _tbl(t, {"Rate / Pc": INR})
    return out


def vendor_cards(x):
    """One table per vendor (like the blocks of the NEW RATE SHEET), in sheet order."""
    cards = []
    for vendor, g in x.groupby("Vendor", sort=False):
        t = g[["Fabric", "Category"] + VR_PRICE_COLS + ["Status", "Note"]].reset_index(drop=True)
        t = t.drop(columns=[c for c in ('36"', '44/36"') if t[c].isna().all()])
        if t["Note"].eq("").all():
            t = t.drop(columns="Note")
        cards.append({"vendor": vendor, "items": int(len(g)), "pending": int(g["Pending Cells"].sum()),
                      "table": _tbl(t, {c: INR for c in VR_PRICE_COLS})})
    return cards


def sheet_tables(cards, vendors):
    """The NEW RATE SHEET as laid out in the sheet: one table per vendor block, with that block's own columns."""
    blocks: dict = {}
    for cd in cards:
        if vendors and cd["vendor"] not in vendors:
            continue
        b = blocks.setdefault((cd["vendor"], tuple(cd["head"])), [])
        b.append(cd["cells"])
    out = []
    for (vendor, head), rows in blocks.items():
        cols = [h or f"Column {i + 1}" for i, h in enumerate(head)]
        df = pd.DataFrame([[None if v is None else (str(v).strip() if isinstance(v, str) else v) for v in r]
                           for r in rows], columns=cols)
        fmt = {c: INR for c in cols[2:]}
        out.append({"vendor": vendor, "items": len(rows), "table": _tbl(df, fmt)})
    return out


def checks(d, cards, source):
    out = []
    if d.empty:
        return out
    zero = d[d["Status"].str.contains(r"\(", regex=True)]
    if len(zero):
        out.append(notice("Rate typed as 0 (pending, left out of averages): " + "; ".join(
            f"{r.Fabric} ({r.Vendor}) {r.Status.split('(', 1)[1].rstrip(')')}" for r in zero.itertuples()) + ".",
            "warning"))
    none = d[d["Status"] == "Pending / N/A"]
    if len(none):
        out.append(notice(f"{len(none)} fabric(s) have no rate at all: " + ", ".join(
            f"{r.Fabric} ({r.Vendor})" for r in none.itertuples()) + ".", "info"))
    dup = d.assign(k=d["Vendor"] + "|" + d["Fabric"].map(norm_key)).duplicated("k", keep=False)
    if dup.any():
        out.append(notice("Listed twice for the same vendor: " + ", ".join(
            sorted({f"{r.Fabric} ({r.Vendor})" for r in d[dup].itertuples()})) + ".", "warning"))
    if source == "Rate_Data" and cards:
        have = {(r["Vendor"], norm_key(r["Fabric"])): sorted(r[c] for c in VR_PRICE_COLS if not np.isnan(r[c]))
                for _, r in d.iterrows()}
        missing, changed = [], []
        for cd in cards:
            key = (cd["vendor"], norm_key(cd["fabric"]))
            if key not in have:
                missing.append(f"{cd['fabric']} ({cd['vendor']})")
            elif cd["nums"] and have[key] and cd["nums"] != have[key]:
                changed.append(f"{cd['fabric']} ({cd['vendor']}): rate card " + "/".join(f"{n:g}" for n in cd["nums"])
                               + ", Rate_Data " + "/".join(f"{n:g}" for n in have[key]))
        if missing:
            out.append(notice(f"{len(missing)} fabric(s) are on the NEW RATE SHEET but not in Rate_Data yet: "
                              + ", ".join(missing[:12]) + ("…" if len(missing) > 12 else "") + ".", "warning"))
        if changed:
            out.append(notice(f"{len(changed)} rate(s) differ between the NEW RATE SHEET and Rate_Data: "
                              + "; ".join(changed[:8]) + ("…" if len(changed) > 8 else "") + ".", "warning"))
    return out


def vendor_rate_dashboard(parsed, f):
    d, cards, source = parsed["d"], parsed["cards"], parsed["source"]
    notices = []
    if not parsed["rate_data_found"]:
        notices.append(notice("The Rate_Data tab was not found" + (", so the rates come straight from the NEW RATE "
                              "SHEET rate cards." if source == "NEW RATE SHEET" else "."), "warning"))
    if d.empty:
        notices.append(notice("No vendor rates found. Expected a 'Rate_Data' tab with Vendor, Fabric (Original) and "
                              "44\" / 60\" / 36\" width rate columns.", "warning"))
        return {"empty": True, "notices": notices, "options": {"vendor": [], "fabric": [], "width": WIDTH_OPTIONS},
                "kpis": []}
    vendors = list(dict.fromkeys(d["Vendor"]))
    cats = sorted(d["Category"].unique())
    x = vr_filter(d, f.get("vendor") or [], f.get("fabric") or [], (f.get("width") or [""])[0],
                  (f.get("q") or [""])[0])
    base = {"source": source, "options": {"vendor": vendors, "fabric": cats, "width": WIDTH_OPTIONS},
            "notices": notices, "checks": checks(d, cards, source)}

    def lowest(col):
        lo = vr_lowest(x, col)
        return kpi(f'Lowest {col} Rate', lo[0] if lo else "—", "", INR if lo else "text",
                   id="lowest44" if col == '44"' else "lowest60", hint=f"{lo[1]} · {lo[2]}" if lo else None)

    kpis = [kpi("Total Vendors", int(x["Vendor"].nunique()), "", id="vendors"),
            kpi("Total Fabric Offerings", int(len(x)), "", id="offerings", hint=f"of {len(d)} on the sheet"),
            lowest('44"'), lowest('60"'),
            kpi("Pending / Missing Rates", int(x["Pending Cells"].sum()), "", id="pending", tone="alert",
                hint="0 or blank rates")]
    default = "Crepe" if "Crepe" in cats else cats[0]
    cols = ["Vendor", "Fabric", "Category"] + VR_PRICE_COLS + ["Status", "Note"]
    return {
        **base,
        "no_match": bool(x.empty),
        "kpis": kpis,
        "compare": {"categories": cats, "default": default, "data": {c: compare_payload(d, c) for c in cats}},
        "tables": {
            "benchmark": _tbl(vr_benchmark(x), BENCH_FMT) if len(x) else table(None),
            "master": _tbl(x[cols].reset_index(drop=True), RATE_FMT) if len(x) else table(None),
        },
        "vendor_cards": vendor_cards(x) if len(x) else [],
        "sheet_tables": sheet_tables(cards, f.get("vendor") or []),
    }
