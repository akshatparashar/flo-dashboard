"""Number formatting, the same rules as the frontend (frontend/src/lib/format.ts), so the chat shows a figure the
same way the page does."""
from __future__ import annotations

import math
import re


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def fmt_int(v: float) -> str:
    return f"{round(v):,}"          # Python rounds half to even, like the frontend's roundHalfEven


def inr(v: float) -> str:
    n = round(abs(v))
    s = str(n)
    if len(s) > 3:
        head = re.sub(r"\B(?=(\d{2})+(?!\d))", ",", s[:-3])
        s = f"{head},{s[-3:]}"
    return f"{'-' if v < 0 and n else ''}₹{s}"


def inr_short(v: float) -> str:
    a, sign = abs(v), "-" if v < 0 else ""
    if a >= 1e7:
        return f"{sign}₹{a / 1e7:,.2f} Cr"
    if a >= 1e5:
        return f"{sign}₹{a / 1e5:,.2f} L"
    return f"{sign}₹{round(a):,}"


UNIT_WORDS = {"pcs": "pcs", "mtr": "mtr", "days": "days", "pos": "POs", "po": "POs"}


def pretty(label: str) -> str:
    return re.sub(r"\bRCVD\b", "Received", label)


def unit_of(label: str) -> tuple[str, str]:
    """'Total Volume (Pcs)' -> ('Total Volume', 'pcs'); 'Order Qty' -> ('Order Qty', 'pcs')."""
    label = pretty(label)
    m = re.match(r"^(.*?)\s*\(([^)]*)\)\s*$", label)
    if not m:
        if re.search(r"\b(qty|pcs)\b", label, re.I):
            return label, "pcs"
        return label, ""
    unit = m.group(2).strip()
    return m.group(1).strip(), UNIT_WORDS.get(unit.lower(), "" if "₹" in unit else unit)


def value(v, fmt: str | None, unit: str = "") -> str:
    """A KPI value or table cell as text, with its unit."""
    if v is None or v == "":
        return "—"
    if not _num(v):
        return str(v)
    fmt = fmt or "int"
    if fmt == "pct":
        return f"{v:,.1f}%"
    if fmt == "inr":
        return inr_short(v)
    if fmt == "inr_full":
        return inr(v)
    if fmt == "dec":
        s = f"{v:,.2f}"
    elif fmt == "dec1":
        s = f"{v:,.1f}"
    else:
        s = fmt_int(v)
    return f"{s} {unit}".strip() if unit else s


def diff(a, b, fmt: str | None, unit: str = "") -> str:
    d = abs(a - b)
    if fmt == "pct":
        return f"{d:,.1f} points"
    return value(d, fmt, unit)


def months(ms: list[str]) -> str:
    if not ms:
        return ""
    return " and ".join(ms) if len(ms) <= 2 else ", ".join(ms[:-1]) + f" and {ms[-1]}"
