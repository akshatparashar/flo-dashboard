"""Vendor Rate dashboard: what each fabric vendor charges, and who is cheapest for each kind of fabric.

Source: the "FABRIC PO 11" Google Sheet.
  Rate_Data       the tidy rate list the sheet's own "Vendor Rate Dashboard" tab is built from. Columns are found by
                  header text: Vendor | S. No. | Fabric (Original) | Fabric Category | 44" Width Rate |
                  60" Width Rate | 36" Width Rate | Per Pc / Special Rate. (The tab also holds helper blocks to the
                  right - metrics, filter lists - which are ignored.)
  NEW RATE SHEET  the hand-filled rate cards, one block per vendor ("RV" above "S. NO. | FABRIC | 44 WIDTH | 60 WIDTH
                  | 36 WIDTH"). Used only as a cross-check: a fabric or rate added there but not yet in Rate_Data is
                  listed under *Sheet checks*. If Rate_Data is missing, the rate cards are used instead.

Rules (same as the sheet's own Vendor Rate Dashboard, checked against its Vendor Benchmark Summary):
  * a rate of 0 or a blank cell is "no rate" and is left out of averages, minimums and maximums;
  * a rate typed as text ("120/125") is shown as typed but left out of the numbers;
  * averages are plain means of the rates that exist.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from ..core import norm_key
from ..tables import kpi, notice, table, with_total

WIDTHS = [("r44", '44"'), ("r60", '60"'), ("r36", '36"'), ("pc", "Per Pc / Special")]
RATE_COLS = [w for w, _ in WIDTHS]
RATE_TAB_NAMES = ["Rate_Data", "Rate Data"]
RATE_TAB_REGEX = r"rate\s*_?\s*data"
CARD_TAB_NAMES = ["NEW RATE SHEET", "Rate Sheet"]
CARD_TAB_REGEX = r"rate\s*sheet"

# Fabric category from the fabric name, used only when the sheet gives none (first match wins; same groups as the
# sheet's own Fabric Category column).
CATEGORY_RULES = [
    (r"HAND\s*WORK", "Hand Work / Dupatta"), (r"RUSS?I?ON?\s*SILK|RUSSIAN", "Russian Silk"),
    (r"CHANDERI", "Mul Chanderi"), (r"CREPE", "Crepe"), (r"MUSLI", "Muslin"), (r"ORG[AE]NZA", "Organza"),
    (r"CHINON", "Chinon"), (r"LINEN|LILEN", "Linen"), (r"SILK", "Silk"), (r"COTTON", "Cotton"),
]


def category_of(fabric: str) -> str:
    t = str(fabric).upper()
    for pat, cat in CATEGORY_RULES:
        if re.search(pat, t):
            return cat
    return "Other"


def category_in_text(text: str) -> str | None:
    """The fabric category a question names ("musline", "russian silk", "chanderi"), or None."""
    t = str(text).upper()
    for pat, cat in CATEGORY_RULES:
        if re.search(pat, t):
            return cat
    return None


def rate_value(v):
    """Cell -> (number or NaN, text shown). 0 / blank -> (NaN, ""). '₹1,250' -> 1250. '120/125' -> (NaN, '120/125')."""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return np.nan, ""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return (float(v), "") if v > 0 else (np.nan, "")
    t = str(v).replace("₹", "").replace(",", "").replace("\xa0", " ").strip()
    if not t:
        return np.nan, ""
    if re.fullmatch(r"\d+(\.\d+)?", t):
        f = float(t)
        return (f, "") if f > 0 else (np.nan, "")
    return np.nan, str(v).strip()


def _zero(v) -> bool:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return v == 0
    return str(v).replace("₹", "").strip() in ("0", "0.0")


def _clean(s) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


# ------------------------------------------------------------------------------------------------ Rate_Data
_RD_FIELDS = [  # field -> normalised header must start with one of these (first match wins)
    ("vendor", ("VENDOR",)), ("sno", ("SNO", "SRNO")), ("fabric", ("FABRICORIGINAL", "FABRIC")),
    ("category", ("FABRICCATEGORY", "CATEGORY")), ("r44", ("44",)), ("r60", ("60",)), ("r36", ("36",)),
    ("pc", ("PERPC", "SPECIAL", "PERPIECE")),
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
            # the tidy table is the first run of headers; helper blocks further right repeat "Vendor"
            first = min(cmap.values())
            return r, {f: i for f, i in cmap.items() if i - first < 12}
    return None, {}


def parse_rate_data(values):
    """Rate_Data tab -> one row per vendor fabric offering, plus problems found."""
    hr, cm = _rd_header(values)
    if hr is None or "vendor" not in cm or "fabric" not in cm:
        return pd.DataFrame(), False
    rows = []
    for i, raw in enumerate(values[hr + 1:], start=hr + 2):
        row = list(raw) + [""] * 30

        def g(f):
            return row[cm[f]] if f in cm else ""
        vendor, fabric = _clean(g("vendor")).upper(), _clean(g("fabric"))
        if not vendor or not fabric or norm_key(vendor) in ("VENDOR", "TOTAL"):
            continue
        rec = {"sheet_row": i, "vendor": vendor, "sno": _clean(g("sno")), "fabric": fabric,
               "category": _clean(g("category")) or category_of(fabric)}
        for f in RATE_COLS:
            rec[f], rec[f + "_text"] = rate_value(g(f))
            rec[f + "_zero"] = _zero(g(f))
        rows.append(rec)
    return pd.DataFrame(rows), True


# ------------------------------------------------------------------------------------------------ rate cards
_SNO = {"SNO", "SRNO", "SNUMBER", "SERIALNO"}


def _card_field(header) -> str | None:
    k = norm_key(header)
    if not k:
        return None
    if k.startswith("FABRIC") or k in ("ITEM", "QUALITY"):
        return "fabric"
    if "PC" in k or "PIECE" in k or "SPECIAL" in k:
        return "pc"
    for w in ("44", "60", "36"):
        if k.startswith(w):
            return "r" + w
    return None


def parse_rate_cards(values):
    """NEW RATE SHEET: vendor blocks laid out side by side and one under another -> one row per offering."""
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
            vendor = ""
            for up in (r - 1, r - 2):
                if up >= 0:
                    vendor = next((str(x).strip() for x in grid[up][c:j] if str(x).strip()), "")
                    if vendor:
                        break
            for k in range(r + 1, len(grid)):
                line = grid[k]
                sno, fabric = str(line[c]).strip(), _clean(line[cols["fabric"]])
                if norm_key(sno) in _SNO or (not fabric and not re.fullmatch(r"\d+(\.0)?", sno)):
                    break
                if not fabric:
                    continue
                rates = [line[i] for f, i in cols.items() if f != "fabric"] + ([line[extra]] if extra else [])
                nums = sorted(x for x in (rate_value(v)[0] for v in rates) if not np.isnan(x))
                texts = sorted(t for t in (rate_value(v)[1] for v in rates) if t)
                out.append({"vendor": vendor.upper(), "fabric": fabric, "nums": nums, "texts": texts})
    return out


def cards_to_frame(cards):
    """Rate cards as the main table (only when Rate_Data is missing): rates go to the block's own columns."""
    rows = []
    for i, cd in enumerate(cards, start=1):
        rec = {"sheet_row": i, "vendor": cd["vendor"], "sno": "", "fabric": cd["fabric"],
               "category": category_of(cd["fabric"])}
        for f in RATE_COLS:
            rec[f], rec[f + "_text"], rec[f + "_zero"] = np.nan, "", False
        for f, n in zip(("r44", "r60", "r36"), cd["nums"]):
            rec[f] = n
        if cd["texts"]:
            rec["pc_text"] = cd["texts"][0]
        rows.append(rec)
    return pd.DataFrame(rows)


# ------------------------------------------------------------------------------------------------ parse
def parse_vendor_rate(grids: dict) -> dict:
    """grids: {"rates": Rate_Data values, "cards": NEW RATE SHEET values} (a missing tab -> [])."""
    d, ok = parse_rate_data(grids.get("rates") or [])
    cards = parse_rate_cards(grids.get("cards") or [])
    source = "Rate_Data"
    if d.empty and cards:
        d, source = cards_to_frame(cards), "NEW RATE SHEET"
    if not d.empty:
        d["vendor_order"] = d["vendor"].map({v: i for i, v in enumerate(dict.fromkeys(d["vendor"]))})
    return {"d": d, "cards": cards, "source": source, "rate_data_found": ok}


# ------------------------------------------------------------------------------------------------ calculations
def _mean(s):
    s = s.dropna()
    return float(s.mean()) if len(s) else np.nan


def _min(s):
    s = s.dropna()
    return float(s.min()) if len(s) else np.nan


def _max(s):
    s = s.dropna()
    return float(s.max()) if len(s) else np.nan


def vendor_benchmark(x):
    """The sheet's Vendor Benchmark Summary (+ 36" and per-piece columns)."""
    rows = []
    for v, g in x.sort_values(["vendor_order", "sheet_row"]).groupby("vendor", sort=False):
        rows.append({"Vendor": v, "Items": int(len(g)), 'Avg 44" Rate': _mean(g["r44"]),
                     'Avg 60" Rate': _mean(g["r60"]), 'Min 60" Rate': _min(g["r60"]),
                     'Max 60" Rate': _max(g["r60"]), 'Avg 36" Rate': _mean(g["r36"]),
                     "Per Pc Items": int(g["pc"].notna().sum() + (g["pc_text"] != "").sum())})
    return pd.DataFrame(rows)


def _best(g, col):
    """(lowest rate, vendors offering it) for one width."""
    s = g.dropna(subset=[col])
    if s.empty:
        return np.nan, ""
    low = s[col].min()
    return float(low), ", ".join(dict.fromkeys(s.loc[s[col] == low, "vendor"]))


def category_compare(x):
    """One row per fabric category: who is cheapest at 60" and 44", and how wide the price range is."""
    rows = []
    for cat, g in x.groupby("category", sort=True):
        b60, v60 = _best(g, "r60")
        b44, v44 = _best(g, "r44")
        mx = _max(g["r60"])
        rows.append({"Fabric Category": cat, "Vendors": int(g["vendor"].nunique()), "Offerings": int(len(g)),
                     'Best 60" Rate': b60, 'Best 60" Vendor': v60, 'Avg 60" Rate': _mean(g["r60"]),
                     'Max 60" Rate': mx, "Spread %": (mx - b60) / b60 * 100 if b60 and not np.isnan(b60) else np.nan,
                     'Best 44" Rate': b44, 'Best 44" Vendor': v44, 'Avg 44" Rate': _mean(g["r44"])})
    t = pd.DataFrame(rows)
    return t.sort_values(["Offerings", "Fabric Category"], ascending=[False, True]) if len(t) else t


def rate_list(x):
    """Every offering, in sheet order, with how far its 60" rate is above the cheapest 60" in its category."""
    if x.empty:
        return pd.DataFrame()
    x = x.sort_values(["vendor_order", "sheet_row"])
    best60 = x.groupby("category")["r60"].min()
    best44 = x.groupby("category")["r44"].min()

    def shown(f):
        return [r[f + "_text"] if r[f + "_text"] else (None if np.isnan(r[f]) else r[f]) for _, r in x.iterrows()]

    above60 = np.where(x["r60"].notna(), (x["r60"] / x["category"].map(best60) - 1) * 100, np.nan)
    above44 = np.where(x["r44"].notna(), (x["r44"] / x["category"].map(best44) - 1) * 100, np.nan)
    return pd.DataFrame({
        "Fabric": x["fabric"].values, "Vendor": x["vendor"].values, "Fabric Category": x["category"].values,
        '44" Rate': shown("r44"), '60" Rate': shown("r60"), '36" Rate': shown("r36"),
        "Per Pc / Special": shown("pc"),
        'vs Best 60" %': above60, 'vs Best 44" %': above44,
    })


def matrix(x, col):
    """Category x vendor average rate (0 = vendor does not quote that category at this width)."""
    vendors = list(dict.fromkeys(x.sort_values("vendor_order")["vendor"]))
    cats = sorted(x["category"].unique())
    p = x.pivot_table(index="category", columns="vendor", values=col, aggfunc="mean").reindex(index=cats,
                                                                                              columns=vendors)
    keep_r = p.notna().any(axis=1)
    keep_c = p.notna().any(axis=0)
    p = p.loc[keep_r, keep_c]
    return {"rows": list(p.index), "columns": list(p.columns),
            "values": [[0.0 if np.isnan(v) else round(float(v), 2) for v in r] for r in p.to_numpy()]}


def checks(d, cards, source):
    out = []
    if d.empty:
        return out
    zero = [(r.vendor, r.fabric, lbl) for r in d.itertuples() for f, lbl in WIDTHS if getattr(r, f + "_zero")]
    if zero:
        out.append(notice("Rate typed as 0 (treated as no rate, left out of averages): " + "; ".join(
            f"{f} ({v}) {w}" for v, f, w in zero) + ".", "warning"))
    texts = [(r.vendor, r.fabric, getattr(r, f + "_text")) for r in d.itertuples() for f, _ in WIDTHS
             if getattr(r, f + "_text")]
    if texts:
        out.append(notice("Rate typed as text (shown as typed, left out of averages): " + "; ".join(
            f"{f} ({v}) “{t}”" for v, f, t in texts) + ".", "info"))
    none = d[d[RATE_COLS].isna().all(axis=1) & (d[[f + "_text" for f in RATE_COLS]] == "").all(axis=1)]
    if len(none):
        out.append(notice(f"{len(none)} fabric(s) have no rate at all: " + ", ".join(
            f"{r.fabric} ({r.vendor})" for r in none.itertuples()) + ".", "info"))
    dup = d.assign(k=d["vendor"] + "|" + d["fabric"].map(norm_key)).duplicated("k", keep=False)
    if dup.any():
        out.append(notice("Listed twice for the same vendor: " + ", ".join(
            sorted({f"{r.fabric} ({r.vendor})" for r in d[dup].itertuples()})) + ".", "warning"))
    if source == "Rate_Data" and cards:
        have = {}
        for r in d.itertuples():
            nums = sorted(getattr(r, f) for f in RATE_COLS if not np.isnan(getattr(r, f)))
            have[(r.vendor, norm_key(r.fabric))] = nums
        missing, changed = [], []
        for cd in cards:
            key = (cd["vendor"], norm_key(cd["fabric"]))
            if key not in have:
                missing.append(f"{cd['fabric']} ({cd['vendor']})")
            elif cd["nums"] and have[key] and cd["nums"] != have[key]:
                changed.append(f"{cd['fabric']} ({cd['vendor']}): rate card "
                               + "/".join(f"{n:g}" for n in cd["nums"]) + ", Rate_Data "
                               + "/".join(f"{n:g}" for n in have[key]))
        if missing:
            out.append(notice(f"{len(missing)} fabric(s) are on the NEW RATE SHEET but not in Rate_Data yet: "
                              + ", ".join(missing[:12]) + ("…" if len(missing) > 12 else "") + ".", "warning"))
        if changed:
            out.append(notice(f"{len(changed)} rate(s) differ between the NEW RATE SHEET and Rate_Data: "
                              + "; ".join(changed[:8]) + ("…" if len(changed) > 8 else "") + ".", "warning"))
    return out


def _filter(d, f, skip=()):
    x = d
    for name, col in (("vendor", "vendor"), ("fabric", "category")):
        if f.get(name) and name not in skip:
            x = x[x[col].isin(f[name])]
    return x


INR = "inr_full"
A60, B60, M60 = 'Avg 60" Rate', 'Best 60" Rate', 'Max 60" Rate'
BENCH_FMT = {c: INR for c in ('Avg 44" Rate', 'Avg 60" Rate', 'Min 60" Rate', 'Max 60" Rate', 'Avg 36" Rate')}
CAT_FMT = {'Best 60" Rate': INR, 'Avg 60" Rate': INR, 'Max 60" Rate': INR, 'Best 44" Rate': INR,
           'Avg 44" Rate': INR, "Spread %": "pct", 'Best 60" Vendor': "text", 'Best 44" Vendor': "text"}
LIST_FMT = {'44" Rate': INR, '60" Rate': INR, '36" Rate': INR, "Per Pc / Special": INR,
            'vs Best 60" %': "pct", 'vs Best 44" %': "pct"}


def vendor_rate_dashboard(parsed, f):
    d, cards, source = parsed["d"], parsed["cards"], parsed["source"]
    notices = []
    if not parsed["rate_data_found"]:
        notices.append(notice("The Rate_Data tab was not found" + (", so the rates come straight from the NEW RATE "
                              "SHEET rate cards (fabric categories are worked out from the fabric names)."
                              if source == "NEW RATE SHEET" else "."), "warning"))
    if d.empty:
        notices.append(notice("No vendor rates found. Expected a 'Rate_Data' tab with Vendor, Fabric (Original), "
                              "Fabric Category and 44\" / 60\" / 36\" width rate columns.", "warning"))
        return {"empty": True, "notices": notices, "options": {"vendor": [], "fabric": []}, "kpis": []}

    vendors = list(dict.fromkeys(d.sort_values("vendor_order")["vendor"]))
    x = _filter(d, f)
    x_nv = _filter(d, f, skip=("vendor",))           # comparisons: every vendor in the chosen categories
    bench = vendor_benchmark(x_nv)
    cat = category_compare(x_nv)
    real = bench.dropna(subset=['Avg 60" Rate'])
    cheap = real.loc[real['Avg 60" Rate'].idxmin()] if len(real) else None
    spread = cat.dropna(subset=["Spread %"])
    spread = spread[spread["Vendors"] > 1]
    wide = spread.loc[spread["Spread %"].idxmax()] if len(spread) else None
    no_rate = x[x[RATE_COLS].isna().all(axis=1) & (x[[c + "_text" for c in RATE_COLS]] == "").all(axis=1)]

    kpis = [
        kpi("Vendors", int(x["vendor"].nunique()), "", id="vendors"),
        kpi("Fabric offerings", int(len(x)), "", id="offerings", hint=f"{x['category'].nunique()} fabric categories"),
        kpi('Avg 44" rate', _mean(x["r44"]), "", INR, id="avg44",
            hint=f"{int(x['r44'].notna().sum())} rates · ₹ per mtr"),
        kpi('Avg 60" rate', _mean(x["r60"]), "", INR, id="avg60",
            hint=f"{int(x['r60'].notna().sum())} rates · ₹ per mtr"),
        kpi('Lowest avg 60" vendor', cheap["Vendor"] if cheap is not None else "—", "", "text", id="cheapest_vendor",
            hint=f"₹{cheap[A60]:,.0f} avg over its 60-inch rates" if cheap is not None else None),
        kpi("Widest price gap", wide["Fabric Category"] if wide is not None else "—", "", "text", id="widest_gap",
            hint=(f"₹{wide[B60]:,.0f} to ₹{wide[M60]:,.0f} at 60-inch "
                  f"({wide['Spread %']:.0f}% apart)") if wide is not None else None),
        kpi("Fabrics without a rate", int(len(no_rate)), "", id="no_rate", tone="alert",
            hint=", ".join(f"{r.fabric} ({r.vendor})" for r in no_rate.itertuples())[:120] or None),
    ]
    by_cat = x.groupby("category").size().sort_values(ascending=False)
    return {
        "source": source,
        "options": {"vendor": vendors, "fabric": sorted(d["category"].unique())},
        "notices": notices,
        "checks": checks(d, cards, source),
        "kpis": kpis,
        "tables": {
            "categories": table(cat, CAT_FMT, key_col="Offerings", sort=False,
                                note="Every vendor is compared here; the vendor filter is not applied."),
            "vendors": table(bench, BENCH_FMT, key_col=None, sort=False,
                             note="Same as the sheet's Vendor Benchmark Summary. 0 and blank rates are left out."),
            "rates": table(rate_list(x), LIST_FMT, key_col=None, sort=False,
                           note="vs Best % = how much dearer than the cheapest rate for the same fabric category "
                                "and width (0% = cheapest)."),
        },
        "charts": {
            "vendor_avg": [{"label": r["Vendor"], "value": float(r['Avg 60" Rate'])} for _, r in real.iterrows()],
            "matrix60": matrix(x_nv, "r60"),
            "matrix44": matrix(x_nv, "r44"),
            "category_counts": [{"label": k, "value": float(v)} for k, v in by_cat.items()],
        },
    }
