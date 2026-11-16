"""Parsing and formatting helpers shared by every dashboard.

These are ported line for line from the original Streamlit app (legacy/streamlit_app.py) so the numbers stay
identical. tests/test_parity.py runs both versions on the same sheet grids and compares the results.
"""
from __future__ import annotations

import re
import warnings
from datetime import datetime, timezone

import numpy as np
import pandas as pd

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None

APP_TZ = "Asia/Kolkata"

# Financial year shown on the dashboards (April 2026 - March 2027)
FY_START_YEAR = 2026
MONTHS = ["April", "May", "June", "July", "August", "September",
          "October", "November", "December", "January", "February", "March"]
MONTH_NUM = {m[:3].lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], start=1)}
MONTH_NAME_BY_NUM = {v: k for k, v in {
    "January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6, "July": 7,
    "August": 8, "September": 9, "October": 10, "November": 11, "December": 12}.items()}
FY_MONTH_LABELS = [
    f"{m}-{(FY_START_YEAR if i < 9 else FY_START_YEAR + 1) % 100:02d}" for i, m in enumerate(MONTHS)
]
FY_MONTH_NOS = [4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2, 3]
MONTHNO_TO_LABEL = dict(zip(FY_MONTH_NOS, FY_MONTH_LABELS))
FY_MONTH_SHORT = [m[:3] for m in MONTHS]
FY_LABEL = f"FY {FY_START_YEAR}-{(FY_START_YEAR + 1) % 100:02d}"

CATEGORIES_LIST = ["CO-ORD SET", "KURTA PANT", "TOP", "KURTA PANT DUPATTA", "DRESS", "KAFTAN", "KURTA"]
KNOWN_DESIGNERS = ["ANAMIKA", "AYUSHI", "CHARU", "DEEPIKA", "JYOTI", "KEERTI",
                   "KRISHNA", "MANSI", "MUSKAN", "REKHA"]


def col_to_idx(letter: str) -> int:
    n = 0
    for c in letter.upper():
        n = n * 26 + ord(c) - 64
    return n - 1


def idx_to_col(i: int) -> str:
    s, i = "", i + 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def norm_key(x) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(x).upper())


def num(s):
    """Convert a Series (numbers or text like '1,234', '(50)', '12%', '5 Days') to float; blanks -> 0."""
    if not isinstance(s, pd.Series):
        s = pd.Series(s)
    out = pd.to_numeric(s, errors="coerce").astype(float)
    need = out.isna() & s.notna()
    if need.any():
        text = s[need].astype(str).str.replace("\xa0", "", regex=False).str.strip()
        neg = text.str.match(r"^\(.*\)$") | text.str.startswith("−")
        cleaned = text.str.replace(r"[^0-9.\-]", "", regex=True)
        cleaned = cleaned.where(cleaned.str.count(r"\.") <= 1, "")
        val = pd.to_numeric(cleaned, errors="coerce")
        val = val.where(~neg, -val.abs())
        out.loc[need] = val
    return out.fillna(0).astype(float)


def clean_delay_days(s):
    parsed = num(s)
    # Blank-date formulas (e.g. TODAY()-blank) produce huge numbers -> treat as 0
    return parsed.mask(parsed.abs() > 1000, 0)


def clean_text(s):
    t = s.astype("string").fillna("")
    t = t.str.replace("\xa0", " ", regex=False).str.replace(r"\s+", " ", regex=True).str.strip()
    t = t.mask(t.str.lower().isin(["nan", "none", "<na>", "#n/a", "#ref!", "#value!"]), "")
    return t.astype(str)


def _parse_one_date(v):
    for dayfirst in (True, False):
        try:
            d = pd.to_datetime(v, dayfirst=dayfirst, errors="coerce")
        except Exception:
            d = pd.NaT
        if pd.notna(d):
            return d
    return pd.NaT


def parse_dates(s):
    """Handles Google Sheets serial numbers (unformatted) and text dates (dd/mm/yyyy first)."""
    s = pd.Series(s)
    out = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    numeric = pd.to_numeric(s, errors="coerce")
    serial = numeric.between(20000, 80000)  # valid sheet serials ~1954..2119
    if serial.any():
        out.loc[serial] = pd.to_datetime(numeric[serial].astype(float), unit="D", origin="1899-12-30")
    text = s.astype(str).str.strip()
    rest = (~serial) & numeric.isna() & text.ne("") & ~text.str.lower().isin(["nan", "none", "<na>"])
    if rest.any():
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            out.loc[rest] = pd.to_datetime(text[rest].apply(_parse_one_date), errors="coerce")
    return out


def month_label(dts):
    lab = pd.Series("(NO DATE)", index=dts.index, dtype=object)
    valid = dts.notna()
    lab[valid] = [f"{MONTH_NAME_BY_NUM[d.month]}-{d.year % 100:02d}" for d in dts[valid]]
    return lab


def month_sort_key(label):
    m = re.match(r"\s*([A-Za-z]+)[\s\-']*(\d{2,4})?", str(label))
    if not m:
        return (9999, 99)
    mon = MONTH_NUM.get(m.group(1)[:3].lower(), 99)
    yr = int(m.group(2)) if m.group(2) else 0
    if 0 < yr < 100:
        yr += 2000
    return (yr if yr else 9998, mon)


def short_month(m) -> str:
    """'April-26' -> 'Apr-26' (other labels unchanged)."""
    mm = re.match(r"([A-Za-z]+)-(\d{2})$", str(m))
    return f"{mm.group(1)[:3]}-{mm.group(2)}" if mm else str(m)


def to_num(v) -> float:
    """Single cell -> float (numbers stay numbers, '1,234' / '(50)' / '12%' are cleaned, junk -> 0)."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    return float(num(pd.Series([v])).iloc[0])


def is_number_text(v) -> bool:
    return bool(re.fullmatch(r"[-+]?(\d[\d,]*\.?\d*|\.\d+)", str(v).strip()))


def safe_div_pct(a, b) -> float:
    return (a / b * 100) if b else 0.0


def fmt(x) -> str:
    return f"{x:,.0f}"


def inr(v) -> str:
    """Full rupee amount with Indian digit grouping: 5020000 -> ₹50,20,000."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return ""
    if not np.isfinite(v):
        return ""
    s = f"{int(round(abs(v))):d}"
    if len(s) > 3:
        s = re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", s[:-3]) + "," + s[-3:]
    return f"{'-' if v < 0 and round(abs(v)) else ''}₹{s}"


def inr_short(v) -> str:
    """Compact amount: ₹50.20 Cr / ₹3.29 L / ₹4,500."""
    v = float(v)
    a, sign = abs(v), ("-" if v < 0 else "")
    if a >= 1e7:
        return f"{sign}₹{a / 1e7:,.2f} Cr"
    if a >= 1e5:
        return f"{sign}₹{a / 1e5:,.2f} L"
    return f"{sign}₹{a:,.0f}"


def now_ist() -> datetime:
    try:
        return datetime.now(ZoneInfo(APP_TZ))
    except Exception:
        return datetime.now(timezone.utc)


def today_ist() -> pd.Timestamp:
    return pd.Timestamp(now_ist().date())


def find_tab(tabs, wanted):
    w = norm_key(wanted)
    for t in tabs:
        if norm_key(t) == w:
            return t
    return None


def pick_default_tab(meta, names, gid=None, name_regex=None):
    """meta = [(title, gid), ...]. Names -> regex -> gid -> first non-dashboard tab."""
    titles = [t for t, _ in meta]
    for n in names:
        t = find_tab(titles, n)
        if t:
            return t
    if name_regex:
        for t in titles:
            if re.search(name_regex, t, re.I):
                return t
    if gid is not None:
        for t, g in meta:
            if str(g) == str(gid):
                return t
    for t in titles:
        if "DASHBOARD" not in t.upper():
            return t
    return titles[0]
