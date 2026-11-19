"""FLO Future dashboard: what each designer promised for the month, and how far it got.

Source: the monthly "FLO_Future <Mon YYYY>" Google Sheet. Tabs read (by name, case and spacing ignored):

  Samples             one row per promised sample collection: Designer | Team | Collection / Sample | Vendor |
                      Season | Qty Promised | Completed | Pending | Status | Due Date | Overdue | Promised To |
                      Contact | Remark
  Outsource Projects  same idea for work given to outside sampling houses: Designer | Project / Collection |
                      Outsource Vendor | Season | Qty Promised | Completed | Pending | Status | Due Date | ... | Remark
  Visits & Meetings   either the original block layout ("Causative Milestone" blocks with Sr / Promised Action /
                      By Whom / To Whom / By When-Date / Complete 'X' / STATUS) or a flat table
                      (Activity | Type | Frequency | Owner | Promised To | Due Date | Done | Remark)

Columns are found by their header text, not by position, so moving or adding a column in the sheet is safe.
Pending, overdue and "due soon" are worked out here from Qty, Completed, Status and Due Date (the sheet's own
Overdue / Designer Summary columns are not trusted, because a copied tab can break their formulas).
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from ..core import MONTH_NAME_BY_NUM, MONTHNO_TO_LABEL, FY_MONTH_LABELS, clean_text, norm_key, num, parse_dates, \
    safe_div_pct, today_ist
from ..tables import kpi, notice, table, with_total

# ------------------------------------------------------------------------------------------------ vocabulary
# Statuses in pipeline order (the sheet's dropdown lists, both tabs). Anything else is kept as typed.
STATUSES = ["Not Updated", "Not Started", "CAD In Queue", "CAD In Process", "Fabric Sourcing", "Sampling Ordered",
            "PP Sample In Process", "Outsource Process", "In-House Process", "In Progress", "Corrections", "Complete"]
_STATUS_BY_KEY = {norm_key(s): s for s in STATUSES}
_STATUS_BY_KEY.update({"COMPLETED": "Complete", "DONE": "Complete", "CADINPROCESS": "CAD In Process",
                       "CADINQUEUE": "CAD In Queue", "INHOUSE": "In-House Process", "NOTSTART": "Not Started",
                       "NOTUPDATE": "Not Updated", "CORRECTION": "Corrections", "INPROCESS": "In Progress"})

# Four stages a status rolls up into (used for the split bar and the chatbot).
STAGES = ["Complete", "In work", "Not started", "Not updated"]
STAGE_OF = {"Complete": "Complete", "Not Started": "Not started", "Not Updated": "Not updated"}

RATE_DONE = {"good": 75, "mid": 40}            # Done %: green >= 75, amber >= 40
SOON_DAYS = 7                                   # "due soon" window
KEEP_UPPER = {"FLO", "RV", "BSK", "AI", "PP", "CAD", "K2P", "KPD", "K/P/D", "OG", "ND", "II", "III"}

SAMPLE_TAB_NAMES = ["Samples", "Sample", "Samples Promised"]
OUTSOURCE_TAB_NAMES = ["Outsource Projects", "Outsource", "Outsourced Projects"]
VISIT_TAB_NAMES = ["Visits & Meetings", "Visits and Meetings", "Visits", "Meetings"]

VISIT_TYPES = [(r"MARKET", "Market Visit"), (r"EXHIBITION|STORE/EXHI", "Store / Exhibition Visit"),
               (r"SURAT", "Surat Visit"), (r"FACTORY", "Factory / Store Visit"), (r"MEETING", "Meeting")]


def canon_status(v) -> str:
    t = re.sub(r"\s+", " ", str(v or "")).strip()
    if not t:
        return "Not Updated"
    k = norm_key(t)
    if k in _STATUS_BY_KEY:
        return _STATUS_BY_KEY[k]
    for key, val in _STATUS_BY_KEY.items():         # "CAD IN-PROCESS", "IN-HOUSE  PROCESS", "Not updated yet"
        if len(key) >= 6 and (k.startswith(key) or key.startswith(k)):
            return val
    return t.title() if t.isupper() else t


def stage_of(status: str) -> str:
    return STAGE_OF.get(status, "In work")


def nice(s: str) -> str:
    """'FLO JURY + FLO FUTURE MEETING' -> 'FLO Jury + FLO Future Meeting'; mixed-case text is left alone."""
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    if not s or not s.isupper():
        return s
    return re.sub(r"[A-Z0-9][A-Z0-9']*",
                  lambda m: m.group(0) if m.group(0) in KEEP_UPPER else m.group(0).capitalize(), s)


def milestone_name(s: str) -> str:
    """'WE HAVE DONE MARKET VISIT FOR ACCESSORIES ONCE IN A MONTH' -> 'Market visit for accessories'."""
    t = re.sub(r"\s+", " ", str(s or "")).strip()
    t = re.sub(r"(?i)^we have (done )?", "", t)
    t = re.sub(r"(?i)\s*\b(once|twice) in a month\b.*$|\s*\bschedule\b\s*$", "", t).strip()
    if not t:
        return nice(s)
    small = {"for", "a", "an", "in", "of", "and", "or", "to", "the", "on", "at"}
    words = re.split(r"(\W+)", nice(t.upper()))
    return "".join(w.lower() if i and w.lower() in small else w for i, w in enumerate(words))


# ------------------------------------------------------------------------------------------------ parsing
_FIELD_RULES = [  # (field, regex on the normalised header) - first match wins, in this order
    ("overdue", r"^OVERDUE"), ("to", r"PROMISEDTO|TOWHOM"), ("owner", r"BYWHOM|^OWNER"),
    ("qty", r"^QTY|^QUANTITY"), ("completed", r"^COMPLETED$|^COMPLETEDQTY|^DONEQTY"),
    ("done_mark", r"^COMPLETE.*MARK|^DONE$"),
    ("pending", r"^PENDING"), ("status", r"^STATUS"), ("due", r"DUEDATE|BYWHEN|^DATE$|^DUE$"),
    ("designer", r"^DESIGNER"), ("team", r"^TEAM"), ("vendor", r"VENDOR|^CLIENT$"), ("season", r"^SEASON"),
    ("contact", r"^CONTACT|PHONE|MOBILE"), ("remark", r"^REMARK"), ("key", r"^KEY"),
    ("frequency", r"^FREQUENCY"), ("type", r"^TYPE$"),
    ("item", r"COLLECTION|SAMPLE|PROJECT|ACTION|ACTIVITY"), ("sr", r"^SR$|^SNO$|^SRNO$"),
]


def col_map(header) -> dict:
    out = {}
    for i, h in enumerate(header):
        k = norm_key(h)
        if not k:
            continue
        for fld, pat in _FIELD_RULES:
            if re.search(pat, k):
                out.setdefault(fld, i)
                break
    return out


def _header_row(values, need=("designer", "qty"), scan=12):
    for i, row in enumerate(values[:scan]):
        m = col_map(row)
        if all(n in m for n in need):
            return i, m
    return None, {}


def _frame(values, start, width):
    rows = values[start:]
    return pd.DataFrame([list(r) + [""] * (width - len(r)) for r in rows], index=range(start + 1, start + 1 + len(rows)))


def parse_promises(values, kind: str):
    """Samples / Outsource Projects tab -> one row per promised item. Returns (DataFrame, warnings)."""
    cols = ["kind", "designer", "team", "item", "vendor", "season", "qty", "completed", "pending", "qty_missing",
            "status", "stage", "due", "promised_to", "remark"]

    def empty():
        e = pd.DataFrame({c: pd.Series(dtype=object) for c in cols})
        e[["qty", "completed", "pending"]] = e[["qty", "completed", "pending"]].astype(float)
        e["qty_missing"] = e["qty_missing"].astype(bool)
        e["due"] = pd.to_datetime(e["due"])
        return e
    if not values:
        return empty(), []
    hr, cm = _header_row(values)
    if hr is None:
        return empty(), [f"The {kind} tab has no header row with Designer and Qty columns."]
    width = max([len(r) for r in values] + [max(cm.values()) + 1])
    df = _frame(values, hr + 1, width)

    def col(fld, default=""):
        return df[cm[fld]] if fld in cm else pd.Series(default, index=df.index)

    d = pd.DataFrame(index=df.index)
    d.index.name = "sheet_row"
    d["kind"] = kind
    d["designer"] = clean_text(col("designer")).map(lambda s: s.title() if s.isupper() or s.islower() else s)
    d["team"] = clean_text(col("team")).map(lambda s: re.sub(r"(?i)^team[\s\-]*", "Team ", s).strip() if s else s)
    d["item"] = clean_text(col("item")).map(nice)
    d["vendor"] = clean_text(col("vendor")).map(nice)
    d["season"] = clean_text(col("season")).map(lambda s: s.title() if s.isupper() else s)
    qty_raw = clean_text(col("qty"))
    d["qty"] = num(col("qty", 0))
    d["completed"] = num(col("completed", 0))
    d["qty_missing"] = qty_raw.eq("")
    d["status"] = col("status").map(canon_status)
    # A collection marked Complete with no completed qty typed in: the promise is done, count it as done.
    done_no_qty = d["status"].eq("Complete") & (d["completed"] == 0) & (d["qty"] > 0)
    d.loc[done_no_qty, "completed"] = d.loc[done_no_qty, "qty"]
    d["pending"] = (d["qty"] - d["completed"]).clip(lower=0)
    d.loc[d["status"].eq("Complete"), "pending"] = 0.0
    d["stage"] = d["status"].map(stage_of)
    d["due"] = parse_dates(col("due"))
    d["promised_to"] = clean_text(col("to")).map(lambda s: s.title() if s.isupper() else s)
    d["remark"] = clean_text(col("remark"))

    blank = d["designer"].eq("") & d["item"].eq("")
    junk = d["designer"].str.upper().isin(["TOTAL", "GRAND TOTAL", "DESIGNER"]) | d["item"].str.upper().eq("TOTAL")
    d = d[~blank & ~junk].copy()
    d.loc[d["designer"].eq(""), "designer"] = "(Not assigned)"
    return d[cols], []


def _visit_type(text: str) -> str:
    t = str(text).upper()
    for pat, name in VISIT_TYPES:
        if re.search(pat, t):
            return name
    return "Other"


def _visit_frequency(text: str) -> str:
    t = norm_key(text)
    if "SATURDAY" in t:
        return "Every Saturday"
    if "TWICE" in t:
        return "Twice a month"
    if "ONCE" in t or "MONTHLY" in t:
        return "Once a month"
    return nice(text) if text and "SEASON" not in t else ""


def _is_done(mark, status) -> bool:
    m = str(mark).strip().upper()
    return m in {"X", "✓", "YES", "Y", "TRUE", "DONE", "1"} or mark is True or \
        bool(re.search(r"\b(DONE|COMPLETE)", str(status).upper()))


def parse_visits(values):
    """Visits & Meetings tab, block layout or flat table -> (planned rows, milestones with nothing planned)."""
    rows, unplanned = [], []
    if not values:
        return pd.DataFrame(columns=["activity", "type", "frequency", "owner", "promised_to", "date", "done",
                                     "status_raw", "remark"]), unplanned
    hr, cm = _header_row(values, need=("item", "done_mark"))
    flat = hr is not None and any(norm_key(c) == "ACTIVITY" for c in values[hr])
    if flat:
        for r in values[hr + 1:]:
            r = list(r) + [""] * 12

            def g(f):
                return r[cm[f]] if f in cm else ""
            act = str(g("item")).strip()
            if not act:
                continue
            rows.append({"activity": nice(act), "type": nice(g("type")) or _visit_type(act),
                         "frequency": _visit_frequency(g("frequency")), "owner": nice(g("owner")),
                         "promised_to": nice(g("to")), "date": g("due"), "done": _is_done(g("done_mark"), g("status")),
                         "status_raw": str(g("status")).strip(), "remark": str(g("remark")).strip()})
    else:
        milestone, m, filled = None, {}, 0
        freq_head = ""

        def close():
            if milestone and not filled:
                unplanned.append({"activity": milestone_name(milestone), "type": _visit_type(milestone),
                                  "frequency": _visit_frequency(milestone)})
        for r in values:
            r = list(r) + [""] * 12
            first = norm_key(r[0])
            if first.startswith("CAUSATIVE") or first == "MILESTONE":
                close()
                milestone, m, filled, freq_head = str(r[1]).strip(), {}, 0, ""
                continue
            if first in {"SR", "SRNO", "SNO"} and milestone is not None:
                m = col_map(r)
                fi = 2 if len(r) > 2 else None
                freq_head = str(r[fi]).strip() if fi is not None and "SEASON" not in norm_key(r[fi]) and \
                    norm_key(r[fi]) not in {"", "QTY"} else ""
                continue
            if not m or milestone is None:
                continue
            act = str(r[m["item"]]).strip() if "item" in m else ""
            if not act:
                continue
            filled += 1

            def g(f):
                return r[m[f]] if f in m else ""
            freq = _visit_frequency(r[2]) or _visit_frequency(freq_head) or _visit_frequency(milestone)
            rows.append({"activity": nice(act), "type": _visit_type(milestone + " " + act), "frequency": freq,
                         "owner": nice(g("owner")), "promised_to": nice(g("to")), "date": g("due"),
                         "done": _is_done(g("done_mark"), g("status")), "status_raw": str(g("status")).strip(),
                         "remark": str(g("remark")).strip(), "milestone": milestone_name(milestone)})
        close()
    v = pd.DataFrame(rows, columns=["activity", "type", "frequency", "owner", "promised_to", "date", "done",
                                    "status_raw", "remark"])
    v["date"] = parse_dates(v["date"]) if len(v) else pd.Series(dtype="datetime64[ns]")
    return v, unplanned


def parse_flo_future(grids: dict) -> dict:
    """grids: {"samples": values, "outsource": values, "visits": values} (a missing tab -> [])."""
    s, w1 = parse_promises(grids.get("samples") or [], "Sample")
    o, w2 = parse_promises(grids.get("outsource") or [], "Outsource")
    # Outsource rows have no Team column: take it from the designer's sample rows.
    teams = s[s["team"] != ""].groupby("designer")["team"].first().to_dict()
    for d in (s, o):
        miss = d["team"].eq("")
        d.loc[miss, "team"] = d.loc[miss, "designer"].map(teams).fillna("")
        d.loc[d["team"].eq(""), "team"] = "(No team)"
    v, unplanned = parse_visits(grids.get("visits") or [])
    return {"samples": s, "outsource": o, "visits": v, "unplanned": unplanned, "warnings": w1 + w2,
            "has": {k: bool(grids.get(k)) for k in ("samples", "outsource", "visits")}}


# ------------------------------------------------------------------------------------------------ dashboard
def _period(d: pd.DataFrame) -> str:
    due = d["due"].dropna()
    if due.empty:
        return ""
    m = due.dt.to_period("M").mode().iloc[0]
    return f"{MONTH_NAME_BY_NUM[m.month]} {m.year}"


def _month_label(ts):
    return MONTHNO_TO_LABEL.get(ts.month) if pd.notna(ts) else None


def _with_timing(d: pd.DataFrame, today: pd.Timestamp) -> pd.DataFrame:
    d = d.copy()
    d["due"] = pd.to_datetime(d["due"], errors="coerce")
    open_ = d["pending"] > 0
    d["days_left"] = (d["due"] - today).dt.days
    d["overdue"] = open_ & d["days_left"].lt(0)
    d["due_soon"] = open_ & d["days_left"].between(0, SOON_DAYS)
    d["no_date"] = open_ & d["due"].isna()
    d["month"] = d["due"].map(_month_label).fillna("(No date)")
    return d


def when_text(days_left, pending, status) -> str:
    if status == "Complete" or pending <= 0:
        return "Done"
    if days_left is None or pd.isna(days_left):
        return "No due date"
    n = int(days_left)
    if n < 0:
        return f"{-n} day{'s' if n != -1 else ''} late"
    if n == 0:
        return "Due today"
    if n == 1:
        return "Due tomorrow"
    return f"In {n} days"


def _filter(d, f, skip=()):
    x = d
    for fld in ("team", "designer", "vendor", "status", "season", "month"):
        if f.get(fld) and fld not in skip and fld in x.columns:
            x = x[x[fld].isin(f[fld])]
    return x


def _totals(x):
    qty, done, pend = float(x["qty"].sum()), float(x["completed"].sum()), float(x["pending"].sum())
    return {"items": int(len(x)), "qty": qty, "completed": done, "pending": pend,
            "done_pct": safe_div_pct(min(done, qty) if qty else done, qty),
            "overdue": int(x["overdue"].sum()), "overdue_pcs": float(x.loc[x["overdue"], "pending"].sum()),
            "due_soon": int(x["due_soon"].sum()), "due_soon_pcs": float(x.loc[x["due_soon"], "pending"].sum()),
            "not_updated": int(x["status"].eq("Not Updated").sum()), "no_date": int(x["no_date"].sum())}


def _group(x, by, label, extra=None):
    if x.empty:
        return pd.DataFrame(columns=[label])
    g = x.groupby(by, sort=False)
    t = pd.DataFrame({
        "Items": g.size(),
        "Promised (Pcs)": g["qty"].sum(),
        "Completed (Pcs)": g["completed"].sum(),
        "Pending (Pcs)": g["pending"].sum(),
        "Overdue": g["overdue"].sum().astype(int),
    })
    t["Done %"] = np.where(t["Promised (Pcs)"] > 0, t["Completed (Pcs)"] / t["Promised (Pcs)"].replace(0, np.nan) * 100,
                           0.0)
    if extra:
        for k, fn in extra.items():
            t[k] = fn(g)
    t.index.name = label
    return t.reset_index()


def _designer_table(xs, xo):
    t = _group(xs, "designer", "Designer", {"Not Updated": lambda g: g["status"].apply(
        lambda s: int(s.eq("Not Updated").sum()))})
    if t.empty and xo.empty:
        return t
    teams = pd.concat([xs[["designer", "team"]], xo[["designer", "team"]]]).groupby("designer")["team"].first()
    if not xo.empty:
        go = xo.groupby("designer")
        o = pd.DataFrame({"Outsource (Pcs)": go["qty"].sum(), "Outsource Pending (Pcs)": go["pending"].sum()})
        o.index.name = "Designer"
        t = t.set_index("Designer").join(o, how="outer").reset_index() if not t.empty else o.reset_index()
    for c in ("Items", "Promised (Pcs)", "Completed (Pcs)", "Pending (Pcs)", "Overdue", "Not Updated",
              "Outsource (Pcs)", "Outsource Pending (Pcs)", "Done %"):
        if c not in t.columns:
            t[c] = 0
        t[c] = t[c].fillna(0)
    for c in ("Items", "Overdue", "Not Updated"):
        t[c] = t[c].astype(int)
    t.insert(1, "Team", t["Designer"].map(teams).fillna(""))
    t = t[["Designer", "Team", "Items", "Promised (Pcs)", "Completed (Pcs)", "Pending (Pcs)", "Done %", "Overdue",
           "Not Updated", "Outsource (Pcs)", "Outsource Pending (Pcs)"]]
    return t.sort_values(["Promised (Pcs)", "Designer"], ascending=[False, True])


def _items_table(x, first="Collection / Sample", vendor_label="Vendor"):
    if x.empty:
        return pd.DataFrame()
    x = x.assign(_open=(x["pending"] > 0).astype(int),
                 _dl=x["days_left"].fillna(10_000)).sort_values(["_open", "_dl", "designer"],
                                                                 ascending=[False, True, True])
    out = pd.DataFrame({
        first: x["item"].replace("", "(No name)"),
        "Designer": x["designer"],
        "Team": x["team"],
        vendor_label: x["vendor"],
        "Season": x["season"],
        "Promised (Pcs)": x["qty"],
        "Completed (Pcs)": x["completed"],
        "Pending (Pcs)": x["pending"],
        "Status": x["status"],
        "Due Date": x["due"],
        "When": [when_text(dl, p, s) for dl, p, s in zip(x["days_left"], x["pending"], x["status"])],
        "Promised To": x["promised_to"],
        "Remark": x["remark"],
    })
    return out.reset_index(drop=True)


def _attention(x):
    """Promises that need someone to act, worst first."""
    out = []
    for _, r in x[x["pending"] > 0].iterrows():
        dl = r["days_left"]
        if r["overdue"]:
            level, reason = "error", f"{int(-dl)} day{'s' if dl != -1 else ''} past the promised date"
        elif r["due_soon"] and dl <= 3:
            level, reason = "warning", when_text(dl, r["pending"], r["status"]) + \
                (" and status not updated" if r["status"] == "Not Updated" else "")
        elif r["status"] == "Not Updated" and (r["due_soon"] or pd.isna(r["due"])):
            level, reason = "warning", "Status not updated" + ("" if pd.notna(r["due"]) else ", no due date")
        elif pd.isna(r["due"]):
            level, reason = "info", "No due date"
        else:
            continue
        out.append({"level": level, "reason": reason, "item": r["item"] or "(No name)", "designer": r["designer"],
                    "team": r["team"], "vendor": r["vendor"], "kind": r["kind"], "status": r["status"],
                    "pending": float(r["pending"]), "qty": float(r["qty"]),
                    "due": r["due"].strftime("%d/%m/%Y") if pd.notna(r["due"]) else None,
                    "days_left": None if pd.isna(dl) else int(dl)})
    rank = {"error": 0, "warning": 1, "info": 2}
    out.sort(key=lambda a: (rank[a["level"]], a["days_left"] if a["days_left"] is not None else 10_000, a["designer"]))
    return out


def _visits(v, unplanned, today):
    if v.empty and not unplanned:
        return pd.DataFrame(), {"planned": 0, "done": 0, "missed": 0, "upcoming": 0, "unplanned": 0}
    status = []
    for _, r in v.iterrows():
        raw = r["status_raw"].upper()
        if r["done"]:
            status.append("Done")
        elif "RESCHEDUL" in raw:
            status.append("Rescheduled")
        elif "CANCEL" in raw:
            status.append("Cancelled")
        elif pd.isna(r["date"]):
            status.append("No date")
        elif r["date"] < today:
            status.append("Not marked done")
        else:
            status.append("Upcoming")
    v = v.assign(status=status)
    t = pd.DataFrame({"Activity": v["activity"], "Type": v["type"], "Frequency": v["frequency"],
                      "Owner": v["owner"], "Promised To": v["promised_to"], "Date": v["date"], "Status": v["status"],
                      "Remark": v["remark"]})
    if unplanned:
        t = pd.concat([t, pd.DataFrame([{"Activity": u["activity"], "Type": u["type"], "Frequency": u["frequency"],
                                         "Owner": "", "Promised To": "", "Date": pd.NaT, "Status": "Not planned",
                                         "Remark": "Nothing filled in on the sheet yet"} for u in unplanned])],
                      ignore_index=True)
    order = {"Not marked done": 0, "Upcoming": 1, "No date": 2, "Not planned": 3, "Rescheduled": 4, "Done": 5,
             "Cancelled": 6}
    t = t.assign(_o=t["Status"].map(order).fillna(9), _d=t["Date"]).sort_values(["_o", "_d"]).drop(
        columns=["_o", "_d"]).reset_index(drop=True)
    stats = {"planned": int(len(v)), "done": int((v["status"] == "Done").sum()),
             "missed": int((v["status"] == "Not marked done").sum()),
             "upcoming": int((v["status"] == "Upcoming").sum()), "unplanned": len(unplanned)}
    return t, stats


def _checks(s, o):
    """Things in the sheet that look wrong or are missing, so the team can fix them at the source."""
    out = []
    both = _both(s, o)
    missing_qty = both[both["qty_missing"] & both["status"].ne("Complete")]
    if len(missing_qty):
        names = ", ".join(f"{r.item} ({r.designer})" for r in missing_qty.itertuples())
        out.append(notice(f"Qty Promised is blank for {len(missing_qty)} item(s): {names}. They count as 0 pcs "
                          "promised until the qty is filled in.", "warning"))
    if not s.empty:
        dup = s.assign(k=s["item"].map(norm_key)).groupby("k")["designer"].nunique()
        dup = dup[(dup > 1) & (dup.index != "")]
        for k in dup.index:
            rows = s[s["item"].map(norm_key) == k]
            out.append(notice(f"“{rows['item'].iloc[0]}” is listed under {', '.join(rows['designer'].unique())} – "
                              f"it is counted for each of them ({fmt_pcs(rows['qty'].sum())} pcs in total). "
                              "Decide one owner or split the qty.", "warning"))
    open_ = both[both["pending"] > 0]
    nd = open_[open_["due"].isna()]
    if len(nd):
        out.append(notice(f"{len(nd)} open item(s) have no due date ({fmt_pcs(nd['pending'].sum())} pcs), so they "
                          "can never show as overdue: " + ", ".join(sorted(nd["designer"].unique())) + ".", "info"))
    nu = open_[open_["status"] == "Not Updated"]
    if len(nu):
        out.append(notice(f"{len(nu)} open item(s) still say “Not Updated” – ask "
                          + ", ".join(sorted(nu["designer"].unique())) + " to set a status.", "info"))
    odd = both[(both["completed"] > 0) & both["status"].isin(["Not Started", "Not Updated"])]
    if len(odd):
        out.append(notice(f"{len(odd)} item(s) have completed pcs but a status of Not Started / Not Updated.", "info"))
    nv = both[both["vendor"].eq("") & (both["pending"] > 0)]
    if len(nv):
        out.append(notice(f"{len(nv)} open item(s) have no vendor: "
                          + ", ".join(f"{r.item} ({r.designer})" for r in nv.itertuples()) + ".", "info"))
    return out


def _both(s, o):
    """Samples and outsource rows together (an empty tab is skipped so column types stay as they are)."""
    parts = [x for x in (s, o) if not x.empty]
    return pd.concat(parts) if len(parts) > 1 else (parts[0] if parts else s)


def fmt_pcs(v) -> str:
    return f"{float(v):,.0f}"


def _options(s, o):
    both = _both(s, o)
    months = [m for m in FY_MONTH_LABELS if m in set(both["due"].map(_month_label).dropna())]
    present = set(both["status"])
    return {
        "team": sorted(t for t in both["team"].unique() if t and not t.startswith("(")),
        "designer": sorted(both["designer"].unique(), key=str.upper),
        "vendor": sorted((v for v in both["vendor"].unique() if v), key=str.upper),
        "status": [st for st in STATUSES if st in present] + sorted(present - set(STATUSES)),
        "season": sorted(v for v in both["season"].unique() if v),
        "month": months,
    }


DONE_FMT = {"Done %": "pct"}
DONE_RATES = {"Done %": RATE_DONE}


def flo_future_dashboard(parsed, f, today: pd.Timestamp | None = None):
    today = pd.Timestamp(today if today is not None else today_ist()).normalize()
    s_all, o_all = parsed["samples"], parsed["outsource"]
    options = _options(s_all, o_all) if not (s_all.empty and o_all.empty) else {
        "team": [], "designer": [], "vendor": [], "status": STATUSES, "season": [], "month": []}
    notices = [notice(w, "warning") for w in parsed.get("warnings", [])]
    if s_all.empty and o_all.empty:
        notices.append(notice("No promised samples found. The FLO Future sheet needs a 'Samples' tab with Designer, "
                              "Qty Promised, Completed, Status and Due Date columns.", "warning"))
        return {"empty": True, "notices": notices, "options": options, "period": ""}

    s = _with_timing(s_all, today)
    o = _with_timing(o_all, today)
    xs, xo = _filter(s, f), _filter(o, f)
    st, ot = _totals(xs), _totals(xo)
    vis_tbl, vs = _visits(parsed["visits"], parsed.get("unplanned", []), today)

    des = _designer_table(_filter(s, f, skip=("designer",)), _filter(o, f, skip=("designer",)))
    real = des[des["Promised (Pcs)"] > 0] if not des.empty else des
    best = real.sort_values(["Done %", "Completed (Pcs)"], ascending=False).iloc[0] if len(real) and \
        real["Completed (Pcs)"].max() > 0 else None
    team_tbl = _group(_filter(s, f, skip=("team",)), "team", "Team", {"Designers": lambda g: g["designer"].nunique()})
    if not team_tbl.empty:
        team_tbl = team_tbl[["Team", "Designers", "Items", "Promised (Pcs)", "Completed (Pcs)", "Pending (Pcs)",
                             "Done %", "Overdue"]].sort_values("Team")
    ven_tbl = _group(_filter(s, f, skip=("vendor",)), "vendor", "Vendor")
    ven_tbl = ven_tbl[ven_tbl["Vendor"] != ""] if not ven_tbl.empty else ven_tbl
    oven_tbl = _group(_filter(o, f, skip=("vendor",)), "vendor", "Vendor")

    # status pipeline (pcs still pending, and items, per status) in pipeline order
    by_status = xs.groupby("status").agg(items=("item", "size"), qty=("qty", "sum"), pending=("pending", "sum"))
    order = [x for x in STATUSES if x in by_status.index] + sorted(set(by_status.index) - set(STATUSES))
    by_status = by_status.reindex(order)
    status_tbl = pd.DataFrame({"Status": by_status.index, "Stage": [stage_of(x) for x in by_status.index],
                               "Items": by_status["items"].astype(int).values,
                               "Promised (Pcs)": by_status["qty"].values,
                               "Pending (Pcs)": by_status["pending"].values})
    # completed pcs, then the pcs still pending split by how far along their item is
    stage_share = []
    for stg in STAGES:
        v = st["completed"] if stg == "Complete" else float(xs.loc[xs["stage"] == stg, "pending"].sum())
        if v > 0:
            stage_share.append({"label": stg, "value": v})

    # pending pcs by due date (past = overdue, next = still in time)
    open_s = xs[xs["pending"] > 0]
    dated = open_s.dropna(subset=["due"])
    days = sorted(dated["due"].unique())
    timeline = {"categories": [pd.Timestamp(d).strftime("%d %b") for d in days],
                "series": [
                    {"name": "Overdue", "values": [float(dated.loc[(dated["due"] == d) & dated["overdue"], "pending"]
                                                         .sum()) for d in days]},
                    {"name": "Pending", "values": [float(dated.loc[(dated["due"] == d) & ~dated["overdue"],
                                                                   "pending"].sum()) for d in days]}],
                "today_index": next((i for i, d in enumerate(days) if pd.Timestamp(d) >= today), len(days)),
                "no_date": float(open_s.loc[open_s["due"].isna(), "pending"].sum())}

    chart_des = des[(des["Promised (Pcs)"] > 0)] if not des.empty else des
    pace = None
    period = _period(s_all if not s_all.empty else o_all)
    if not s_all["due"].dropna().empty:
        # where the month should be by today if work is spread evenly up to each item's due date
        due_by_today = float(xs.loc[xs["due"].notna() & (xs["due"] < today), "qty"].sum())
        pace = {"due_by_today": due_by_today, "completed": st["completed"]}

    lede_bits = {"done_pct": st["done_pct"], "completed": st["completed"], "qty": st["qty"], "overdue": st["overdue"],
                 "due_soon": st["due_soon"], "not_updated": st["not_updated"]}

    kpis = [
        kpi("Promised samples", st["qty"], "pcs", id="promised", hint=f"{st['items']} collections promised"),
        kpi("Completed samples", st["completed"], "pcs", id="completed", tone="good"),
        kpi("Pending samples", st["pending"], "pcs", id="pending"),
        kpi("Completion rate", st["done_pct"], "", "pct", id="done_pct", hint="Completed ÷ promised pcs"),
        kpi("Overdue promises", st["overdue"], "items", id="overdue", tone="alert",
            hint=f"{fmt_pcs(st['overdue_pcs'])} pcs past the promised date, not complete"),
        kpi("Due soon", st["due_soon"], "items", id="due_soon",
            hint=f"Open items due in the next {SOON_DAYS} days ({fmt_pcs(st['due_soon_pcs'])} pcs)"),
        kpi("Status not updated", st["not_updated"], "items", id="not_updated", tone="alert",
            hint="Status column still says Not Updated"),
        kpi("Top performer", best["Designer"] if best is not None else "—", "", "text", id="top",
            hint=f"{best['Done %']:.0f}% of {fmt_pcs(best['Promised (Pcs)'])} pcs done" if best is not None else None),
        kpi("Outsource promised", ot["qty"], "pcs", id="out_promised", hint=f"{ot['items']} outsource projects"),
        kpi("Outsource pending", ot["pending"], "pcs", id="out_pending",
            hint=f"{ot['overdue']} overdue" if ot["overdue"] else "None overdue"),
        kpi("Visits & meetings done", vs["done"], "", id="visits_done",
            hint=f"of {vs['planned']} planned" + (f"; {vs['missed']} past date not marked done" if vs["missed"]
                                                  else "")),
        kpi("Activities not planned", vs["unplanned"], "", id="unplanned",
            hint="Monthly visit blocks left empty on the sheet"),
    ]

    sample_items = _items_table(xs)
    out_items = _items_table(xo, first="Project / Collection", vendor_label="Outsource Vendor")
    return {
        "period": period,
        "today": today.strftime("%d/%m/%Y"),
        "options": options,
        "notices": notices,
        "checks": _checks(s_all, o_all),
        "kpis": kpis,
        "summary": {**lede_bits, "pending": st["pending"], "items": st["items"], "outsource": ot, "visits": vs},
        "pace": pace,
        "attention": _attention(_both(xs, xo)),
        "tables": {
            "designers": table(with_total(des, "Designer", pct=("Done %", "Completed (Pcs)", "Promised (Pcs)")),
                               DONE_FMT, key_col="Promised (Pcs)", rates=DONE_RATES,
                               note="Every designer is listed so they can be compared; the designer filter is not "
                                    "applied here."),
            "teams": table(with_total(team_tbl, "Team", pct=("Done %", "Completed (Pcs)", "Promised (Pcs)")),
                           DONE_FMT, key_col="Promised (Pcs)", sort=False, rates=DONE_RATES),
            "vendors": table(with_total(ven_tbl, "Vendor", pct=("Done %", "Completed (Pcs)", "Promised (Pcs)")),
                             DONE_FMT, key_col="Promised (Pcs)", rates=DONE_RATES),
            "outsource_vendors": table(with_total(oven_tbl, "Vendor", pct=("Done %", "Completed (Pcs)",
                                                                           "Promised (Pcs)")),
                                       DONE_FMT, key_col="Promised (Pcs)", rates=DONE_RATES),
            "status": table(status_tbl, key_col="Pending (Pcs)", sort=False),
            "items": table(sample_items, {"Due Date": "date"}, key_col=None, sort=False),
            "outsource": table(out_items, {"Due Date": "date"}, key_col=None, sort=False),
            "visits": table(vis_tbl, {"Date": "date"}, key_col=None, sort=False),
        },
        "charts": {
            "designers": {"categories": list(chart_des["Designer"]) if len(chart_des) else [],
                          "series": [{"name": n, "values": [float(v) for v in chart_des[c]] if len(chart_des) else []}
                                     for n, c in (("Completed", "Completed (Pcs)"), ("Pending", "Pending (Pcs)"))]},
            "stage_share": stage_share,
            "status": [{"label": r["Status"], "value": float(r["Pending (Pcs)"])} for _, r in status_tbl.iterrows()
                       if r["Status"] != "Complete" and r["Pending (Pcs)"] > 0],
            "timeline": timeline,
        },
    }


def overview_alert(parsed, today: pd.Timestamp | None = None) -> dict | None:
    """One alert card for the Overview page."""
    if not parsed or (parsed["samples"].empty and parsed["outsource"].empty):
        return None
    today = pd.Timestamp(today if today is not None else today_ist()).normalize()
    s = _with_timing(_both(parsed["samples"], parsed["outsource"]), today)
    t = _totals(s)
    period = _period(parsed["samples"]) or "this month"
    head = f"{t['done_pct']:.0f}% of {fmt_pcs(t['qty'])} promised pcs done for {period}"
    if t["overdue"]:
        late = s[s["overdue"]].sort_values("days_left")
        w = late.iloc[0]
        return {"kind": "error" if t["overdue"] >= 3 else "warning", "area": "promises",
                "title": f"{t['overdue']} promised item{'s' if t['overdue'] != 1 else ''} overdue",
                "text": f"{head}. {fmt_pcs(t['overdue_pcs'])} pcs are past the promised date; most late: "
                        f"{w['item']} ({w['designer']}, {int(-w['days_left'])} days). "
                        f"{t['due_soon']} more due in the next 7 days."}
    return {"kind": "success" if t["not_updated"] == 0 else "info", "area": "promises",
            "title": f"{t['done_pct']:.0f}% of promises done",
            "text": f"{head}. Nothing is overdue; {t['due_soon']} item(s) due in the next 7 days"
                    + (f", {t['not_updated']} still 'Not Updated'." if t["not_updated"] else ".")}
