"""Sample Summary dashboard (mirrors the "SAMPLE DASHBOARD" Apps Script).

Source tab columns: B = Vendor | F = Qty | H = Process Date | L = Status | N = Designer. Row 1 = header.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from ..core import (FY_MONTH_LABELS, MONTHNO_TO_LABEL, clean_text, col_to_idx, is_number_text, num, safe_div_pct)
from ..tables import RATE_APPROVAL, kpi, notice, table, with_total

SAMPLE_STATUSES = ["Approved", "Rejected", "On Hold", "In Process", "Other"]
SAMPLE_COLS = {"vendor": "B", "qty": "F", "date": "H", "status": "L", "designer": "N"}
MON3 = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]


def _month_from_text(t):
    t = re.sub(r"[ .,\-]+", "/", str(t).strip().lower())
    for pat in (r"^\d{1,2}/(\d{1,2})/\d{2,4}$",      # dd/mm/yyyy
                r"^(\d{1,2})/\d{4}$",                  # mm/yyyy
                r"^\d{4}/(\d{1,2})/\d{1,2}$"):         # yyyy/mm/dd
        m = re.match(pat, t)
        if m:
            return int(m.group(1))
    m = re.search(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)", t)   # "Apr-26", "April 2026"
    return MON3.index(m.group(1)) + 1 if m else 0


def month_numbers(s):
    """Process-date column -> month number 1..12 (0 = blank / unreadable). Same rules as the sheet script."""
    s = pd.Series(s).fillna("")
    out = pd.Series(0, index=s.index, dtype="int64")
    numeric = pd.to_numeric(s, errors="coerce")
    isnum = numeric.notna() & numeric.between(1, 100000)
    if isnum.any():
        dts = pd.to_datetime(numeric[isnum].astype(float), unit="D", origin="1899-12-30", errors="coerce")
        out.loc[isnum] = dts.dt.month.fillna(0).astype("int64").to_numpy()
    txt = (~isnum) & numeric.isna() & s.astype(str).str.strip().ne("")
    if txt.any():
        out.loc[txt] = s[txt].map(_month_from_text).astype("int64").to_numpy()
    return out.where(out.between(1, 12), 0)


def classify_status(s):
    t = clean_text(s).str.upper()
    vals = np.select(
        [t.eq(""), t.str.contains("REJECT"), t.str.contains("APPROV"), t.str.contains("HOLD"), t.str.contains("PROCESS")],
        ["Other", "Rejected", "Approved", "On Hold", "In Process"], default="Other")
    return pd.Series(vals, index=t.index)


def canon_series(raw, skip_words):
    """Case-insensitive name cleanup: 'abc' / 'ABC ' -> one spelling. Blank -> (BLANK), numbers/headers -> (OTHER)."""
    skip = {w.upper() for w in skip_words}
    mapping = {}
    for v in raw:
        if v and not is_number_text(v) and v.upper() not in skip:
            mapping.setdefault(v.upper(), v)
    return raw.map(lambda v: mapping.get(v.upper(), "(BLANK)" if v == "" else "(OTHER)"))


def build_samples(values):
    if len(values) < 2:
        return pd.DataFrame(), []
    header = list(values[0])
    rows = values[1:]
    width = max([len(r) for r in rows] + [col_to_idx("N") + 1])
    df = pd.DataFrame([list(r) + [""] * (width - len(r)) for r in rows], index=range(2, 2 + len(rows)))

    def col(key):
        return df[col_to_idx(SAMPLE_COLS[key])]

    d = pd.DataFrame(index=df.index)
    d.index.name = "sheet_row"
    d["qty"] = num(col("qty"))
    vendor_raw, designer_raw = clean_text(col("vendor")), clean_text(col("designer"))
    status_raw = clean_text(col("status"))
    d["vendor"] = canon_series(vendor_raw, ("VENDOR NAME", "VENDOR"))
    d["designer"] = canon_series(designer_raw, ("DESIGNER NAME", "DESIGNER"))
    d["month_no"] = month_numbers(col("date"))
    d["month"] = d["month_no"].map(MONTHNO_TO_LABEL).fillna("(NO DATE)")
    d["status"] = classify_status(col("status"))
    d["qty_raw"] = col("qty").astype(str).str.strip()
    d["date_raw"] = col("date").astype(str).str.strip()
    d["status_raw"] = status_raw
    keep = (vendor_raw != "") | (designer_raw != "") | (status_raw != "") | (d["qty"] != 0)
    return d[keep], header


def header_warning(header):
    hints = {"vendor": "vendor", "qty": "qty|quant|sample", "date": "date", "status": "status", "designer": "designer"}
    hits = 0
    for k, pat in hints.items():
        i = col_to_idx(SAMPLE_COLS[k])
        if i < len(header) and re.search(pat, str(header[i]), re.I):
            hits += 1
    return hits < 2


def sample_filter(d, f, skip=()):
    x = d
    for field in ("month", "designer", "status", "vendor"):
        if f.get(field) and field not in skip:
            x = x[x[field].isin(f[field])]
    return x


def status_table(x, group_col, index_values):
    if x.empty:
        p = pd.DataFrame(0.0, index=index_values, columns=SAMPLE_STATUSES)
    else:
        p = (x.groupby([group_col, "status"])["qty"].sum().unstack(fill_value=0)
             .reindex(index=index_values, columns=SAMPLE_STATUSES, fill_value=0).astype(float))
    p["Total"] = p[SAMPLE_STATUSES].sum(axis=1)
    p["Approval %"] = np.where(p["Total"] > 0, p["Approved"] / p["Total"].replace(0, np.nan) * 100, 0.0)
    return p


def sample_monthly(x):
    p = status_table(x, "month", FY_MONTH_LABELS + ["(NO DATE)"])
    if p.loc["(NO DATE)", "Total"] == 0:
        p = p.drop(index="(NO DATE)")
    p.index.name = "Month"
    return p.reset_index()


def sample_entity_table(x, group_col, names, label):
    p = status_table(x, group_col, list(names) + ["(BLANK)", "(OTHER)"])
    p = p[(p["Total"] != 0) | ~p.index.isin(["(BLANK)", "(OTHER)"])]
    p = p.sort_values("Total", ascending=False)
    p.index.name = label
    return p.reset_index()


def sample_totals(x):
    by = x.groupby("status")["qty"].sum()
    tot = float(x["qty"].sum())
    app, rej, hld, prc, oth = (float(by.get(s, 0.0)) for s in SAMPLE_STATUSES)
    return {"total": tot, "approved": app, "rejected": rej, "on_hold": hld, "in_process": prc, "other": oth,
            "approval_pct": safe_div_pct(app, tot), "rejection_pct": safe_div_pct(rej, tot)}


def _entity_chart(tbl, label):
    t = tbl[tbl["Total"] > 0].head(20)
    return {"categories": list(t[label]),
            "series": [{"name": s, "values": [float(v) for v in t[s]]} for s in SAMPLE_STATUSES]}


PCT = {"Approval %": "pct"}
RATES = {"Approval %": RATE_APPROVAL}


def parse_samples(values):
    d, header = build_samples(values)
    return {"d": d, "header": header}


def samples_dashboard(parsed, f):
    d, header = parsed["d"], parsed["header"]
    notices = []
    if d.empty:
        return {"empty": True, "notices": [notice(
            "No sample data found. Expected: row 1 = header, data from row 2 "
            "(Vendor = B, Qty = F, Process Date = H, Status = L, Designer = N).", "warning")],
            "options": {"month": FY_MONTH_LABELS, "designer": [], "status": SAMPLE_STATUSES, "vendor": []}}
    if header_warning(header):
        notices.append(notice("The sample sheet header does not match the expected columns (B Vendor, F Qty, "
                              "H Date, L Status, N Designer). Numbers may be wrong.", "warning"))

    designer_names = [n for n in d["designer"].unique() if not n.startswith("(")]
    vendor_names = [n for n in d["vendor"].unique() if not n.startswith("(")]

    x = sample_filter(d, f)
    x_nd = sample_filter(d, f, skip=("designer",))     # designer comparison ignores the designer filter
    x_nv = sample_filter(d, f, skip=("vendor",))       # vendor comparison ignores the vendor filter
    s = sample_totals(x)

    des_tbl = sample_entity_table(x_nd, "designer", designer_names, "Designer")
    real = des_tbl[~des_tbl["Designer"].str.startswith("(")]
    if not real.empty and real["Approved"].max() > 0:
        top = real.loc[real["Approved"].idxmax()]
        top_name, top_val = top["Designer"], float(top["Approved"])
    else:
        top_name, top_val = None, 0.0

    mt = sample_monthly(x)
    nd = float(mt.loc[mt["Month"] == "(NO DATE)", "Total"].sum())
    if nd > 0:
        notices.append(notice(f"{nd:,.0f} samples have a blank or unreadable process date. See the "
                              "'(NO DATE)' row in the monthly table.", "warning"))

    ven_tbl = sample_entity_table(x_nv, "vendor", vendor_names, "Vendor")
    return {
        "options": {"month": FY_MONTH_LABELS, "designer": sorted(designer_names, key=str.upper),
                    "status": SAMPLE_STATUSES, "vendor": sorted(vendor_names, key=str.upper)},
        "notices": notices,
        "kpis": [
            kpi("Total samples", s["total"], "pcs", id="total"),
            kpi("Approved", s["approved"], "pcs", id="approved", tone="good"),
            kpi("Rejected", s["rejected"], "pcs", id="rejected", tone="alert"),
            kpi("On hold", s["on_hold"], "pcs", id="on_hold"),
            kpi("In process", s["in_process"], "pcs", id="in_process"),
            kpi("Approval rate", s["approval_pct"], "", "pct", id="approval_pct"),
            kpi("Top performer", top_name or "—", "", "text", id="top",
                hint=f"{top_val:,.0f} pcs approved" if top_name else None),
            kpi("Rejection rate", s["rejection_pct"], "", "pct", id="rejection_pct"),
            kpi("Open pipeline", s["on_hold"] + s["in_process"], "pcs", id="open", hint="On hold + in process"),
            kpi("Other / blank status", s["other"], "pcs", id="other"),
        ],
        "tables": {
            "monthly": table(with_total(mt, "Month", pct=("Approval %", "Approved", "Total")), PCT,
                             key_col="Total", sort=False, rates=RATES),
            "designers": table(with_total(des_tbl, "Designer", pct=("Approval %", "Approved", "Total")), PCT,
                               key_col="Total", rates=RATES,
                               note="The designer filter is not applied here so every designer can be compared."),
            "vendors": table(with_total(ven_tbl, "Vendor", pct=("Approval %", "Approved", "Total")), PCT,
                             key_col="Total", rates=RATES,
                             note="The vendor filter is not applied here so every vendor can be compared."),
        },
        "charts": {
            "monthly_status": {"categories": list(mt["Month"]),
                               "series": [{"name": st_, "values": [float(v) for v in mt[st_]]}
                                          for st_ in SAMPLE_STATUSES]},
            "monthly_trend": {"categories": list(mt["Month"]),
                              "series": [{"name": n, "values": [float(v) for v in mt[n]]}
                                         for n in ("Total", "Approved", "Rejected")]},
            "status_share": [{"label": st_, "value": v} for st_, v in
                             zip(SAMPLE_STATUSES, [s["approved"], s["rejected"], s["on_hold"], s["in_process"],
                                                   s["other"]]) if v > 0],
            "designers": _entity_chart(des_tbl, "Designer"),
            "vendors": _entity_chart(ven_tbl, "Vendor"),
        },
        "summary": s,
    }
