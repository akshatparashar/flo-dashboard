"""Calculation requests hidden in a question: growth, difference, sum, average, share and plain arithmetic.

This module only reads the *words* (English and Hinglish) and does safe arithmetic. Finding the figures is done by
engine.py, so every number still comes from the dashboard.
"""
from __future__ import annotations

import ast
import operator
import re
from dataclasses import dataclass

from .text import norm

PCT = r"(?:%|percent(?:age)?|pct|prtishat|pratishat|fisadi|fisdi)"
MULT = {"k": 1e3, "thousand": 1e3, "lakh": 1e5, "lakhs": 1e5, "lac": 1e5, "lacs": 1e5, "cr": 1e7, "crore": 1e7,
        "crores": 1e7, "m": 1e6, "million": 1e6}
NUM = r"(\d[\d,]*(?:\.\d+)?)\s*(k|thousand|lakhs?|lacs?|crores?|cr|million|m)?(?![a-z])"


@dataclass
class Spec:
    kind: str                      # arithmetic | n_of | share | metric_op | growth | diff | sum | average
    expr: str = ""                 # arithmetic: the expression to evaluate
    disp: str = ""                 # arithmetic: the expression as shown to the person
    a: str = ""                    # metric phrase (left side / numerator)
    b: str = ""                    # metric phrase (right side / denominator)
    n: float | None = None         # a number written in the question
    op: str = ""                   # metric_op: / * + - pct+ pct-


def to_number(text: str, suffix: str | None = None) -> float:
    return float(text.replace(",", "")) * MULT.get((suffix or "").lower(), 1)


def num(v: float) -> str:
    """A plain number for the chat: 1,234.5 (at most 2 decimals, no trailing zeros)."""
    if abs(v - round(v)) < 1e-9:
        return f"{round(v):,}"
    return f"{v:,.2f}".rstrip("0").rstrip(".")


# ------------------------------------------------------------------------------------------------ arithmetic
_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Pow: operator.pow, ast.Mod: operator.mod, ast.FloorDiv: operator.floordiv}


def evaluate(expr: str) -> float:
    """Evaluates numbers with + - * / ** % and brackets, and nothing else."""
    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool):
            return n.value
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
            v = ev(n.operand)
            return -v if isinstance(n.op, ast.USub) else v
        if isinstance(n, ast.BinOp) and type(n.op) in _BIN:
            a, b = ev(n.left), ev(n.right)
            if isinstance(n.op, ast.Pow) and (abs(b) > 100 or abs(a) > 1e6):
                raise ValueError("too big")
            return _BIN[type(n.op)](a, b)
        raise ValueError("unsupported")
    return ev(ast.parse(expr, mode="eval"))


_FILLER = re.compile(r"\b(what|whats|what's|is|are|the|calculate|calc|compute|tell|me|please|kitna|kitne|kitni|hai|"
                     r"hota|hoti|batao|bataiye|bata|equals?|answer|result|value|will|be|do|karo|kar|do)\b")
_WORD_OPS = [
    (r"\bdivided by\b|\bdivide by\b|\bdivided\b", " / "),
    (r"\bmultiplied by\b|\bmultiply by\b|\btimes\b|\bgunaa?\b", " * "),
    (r"\bplus\b", " + "),
    (r"\bminus\b|\bsubtract\b", " - "),
    (r"\bto the power of\b|\bpower\b", " ** "),
]
_N_OF_NUMBERS = re.compile(rf"^(?:what(?:'s| is)? )?(\d[\d,]*(?:\.\d+)?)\s*{PCT}\s*of\s*(\d[\d,]*(?:\.\d+)?)\s*\??$")


def _arithmetic(t: str) -> Spec | None:
    m = _N_OF_NUMBERS.match(t)
    if m:
        a, b = m.group(1).replace(",", ""), m.group(2).replace(",", "")
        return Spec("arithmetic", expr=f"({a}/100)*{b}", disp=f"{num(float(a))}% of {num(float(b))}")
    s = t.replace("×", "*").replace("÷", "/").replace("^", "**").replace("=", " ").replace("?", " ")
    for pat, sym in _WORD_OPS:
        s = re.sub(pat, sym, s)
    s = re.sub(r"(?<=\d)\s*x\s*(?=\d)", " * ", s)
    s = _FILLER.sub(" ", s)
    s = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    if not s or re.search(r"[a-z%₹]", s):
        return None
    if not re.search(r"\d\s*(\*\*|[+\-*/])\s*\(?\s*-?\d|\)\s*(\*\*|[+\-*/])", s):
        return None
    disp = s.replace("**", "^").replace("*", "×").replace("/", "÷")
    return Spec("arithmetic", expr=s, disp=re.sub(r"\s*([×÷^+\-])\s*", r" \1 ", disp))


# ------------------------------------------------------------------------------------------------ share / percent of
_N_OF = re.compile(rf"(\d+(?:\.\d+)?)\s*{PCT}\s*(?:of|ka|ki|ke)\s+(?P<b>.+)")
_Q = r"(?:(?:kitna|kitne|kya)\s+)?"
_SHARE = [
    re.compile(rf"what\s+{PCT}\s+of\s+(?P<b>.+?)\s+(?:is|are)\s+(?P<a>.+)"),
    re.compile(rf"(?P<a>.+?)\s+(?:is|are)\s+what\s+{PCT}\s+of\s+(?P<b>.+)"),
    re.compile(rf"(?P<a>.+?)\s+as\s+(?:a\s+)?{PCT}\s+of\s+(?P<b>.+)"),
    re.compile(rf"(?P<a>.+?)\s+out of\s+(?P<b>.+?)\s+(?:in|as)\s*(?:a\s+)?{PCT}"),
    re.compile(rf"(?P<a>.+?)\s+(?:(?:ka|ki|ke)\s+)?{_Q}{PCT}\s+{_Q}(?:hai\s+)?(?P<b>.+?)\s+(?:me|mein|of|se)$"),
]


def _share(t: str) -> Spec | None:
    m = _N_OF.search(t)
    if m:
        return Spec("n_of", n=float(m.group(1)), b=m.group("b").strip())
    for rx in _SHARE:
        m = rx.search(t)
        if m and m.group("a").strip() and m.group("b").strip():
            return Spec("share", a=m.group("a").strip(), b=m.group("b").strip())
    return None


# ------------------------------------------------------------------------------------------------ metric (+ - * /) number
_METRIC_OPS = [
    ("/", re.compile(rf"^(?P<a>.+?)\s+(?:divided by|divide by|/|÷)\s*{NUM}")),
    ("/", re.compile(rf"^(?P<a>.+?)\s+ko\s+{NUM}\s+se\s+(?:divide|bhaag|bhag|baant)")),
    ("*", re.compile(rf"^(?P<a>.+?)\s+(?:times|multiplied by|multiply by|\*|×)\s*{NUM}")),
    ("*", re.compile(rf"^(?P<a>.+?)\s+ko\s+{NUM}\s+se\s+(?:multiply|guna|gunaa|gun)")),
    ("pct+", re.compile(rf"^(?P<a>.+?)\s+(?:plus|\+|increase(?:d)? by|up by|more by|badhao|badha kar)\s+(\d+(?:\.\d+)?)\s*{PCT}")),
    ("pct-", re.compile(rf"^(?P<a>.+?)\s+(?:minus|-|decrease(?:d)? by|down by|less by|ghatao|ghata kar)\s+(\d+(?:\.\d+)?)\s*{PCT}")),
    ("+", re.compile(rf"^(?P<a>.+?)\s+(?:plus|\+)\s*{NUM}")),
    ("-", re.compile(rf"^(?P<a>.+?)\s+(?:minus|-)\s*{NUM}")),
]
_DOUBLE = re.compile(r"\b(?:double|twice|dugna|dugni)\s+(?:of\s+|the\s+)?(?P<a>.+)")
_HALF = re.compile(r"\b(?:half of|half|aadha|adha)\s+(?:of\s+|the\s+)?(?P<a>.+)")


def _metric_op(t: str) -> Spec | None:
    for op, rx in _METRIC_OPS:
        m = rx.search(t)
        if m:
            g = m.groups()
            n = to_number(g[-2], g[-1]) if op in ("/", "*", "+", "-") else float(g[-1] if g[-1] else g[-2])
            if op in ("pct+", "pct-"):
                n = float(g[-1])
            return Spec("metric_op", a=m.group("a").strip(), n=n, op=op)
    m = _DOUBLE.search(t)
    if m:
        return Spec("metric_op", a=m.group("a").strip(), n=2, op="*")
    m = _HALF.search(t)
    if m:
        return Spec("metric_op", a=m.group("a").strip(), n=2, op="/")
    return None


# ------------------------------------------------------------------------------------------------ growth / difference / sum / average
GROWTH = re.compile(r"\b(growth|grew|grow|growing|grown|increase[ds]?|decrease[ds]?|decline[ds]?|dropp?(?:ed)?|fell|"
                    r"improve[ds]?|improvement|badh\w*|barh\w*|vridhi|vruddhi|gir\w*|ghat\w*|girawat|loss|nuksa?an)\b")
DIRECTION = re.compile(r"\b(more|less|higher|lower|zyada|jyada|kam|upar|neeche|change|difference|fark|up|down)\b")
DIFF = re.compile(r"\b(difference|differences|diff|fark|farak|antar|gap|kitna\s+(?:zyada|jyada|kam|adhik)|"
                  r"how much\s+(?:more|less|higher|lower|extra)|more than|less than)\b")
SUM = re.compile(r"\b(milake|mila ke|mila kar|milakar|jod ke|jodke|jod kar|jodkar|add|adding|plus|sum|combined|"
                 r"together|altogether|collectively|dono ka|dono ki)\b")
AVG = re.compile(r"\b(average|avg|mean|ausat|aushat)\b")
PCT_WORD = re.compile(PCT)


def detect(text: str) -> Spec | None:
    """What kind of calculation (if any) the question asks for."""
    t = norm(text)
    spec = _arithmetic(t) or _share(t) or _metric_op(t)
    if spec:
        return spec
    if GROWTH.search(t) or (PCT_WORD.search(t) and DIRECTION.search(t)):
        return Spec("growth")
    if DIFF.search(t):
        return Spec("diff")
    if SUM.search(t):
        return Spec("sum")
    if AVG.search(t):
        return Spec("average")
    return None


# ------------------------------------------------------------------------------------------------ numbers the person gives
_MONTH_WORD = re.compile(r"^(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*$", re.I)
_GIVEN_DROP = {"if", "agar", "suppose", "assume", "let", "lets", "say", "maan", "lo", "has", "have", "had", "is", "are",
               "was", "were", "ke", "ka", "ki", "ko", "hain", "hai", "tha", "the", "and", "aur", "with", "orders", "order",
               "pcs", "pieces", "designs", "design", "but", "while", "then", "of", "in", "for", "me", "mein", "what",
               "how", "much", "many", "kitna", "kitne", "kitni", "a", "an", "to", "total", "repeat", "new", "sale",
               "sales", "revenue", "rs", "inr", "units", "qty", "quantity", "got", "did", "does", "do", "made", "kiye",
               "kiya", "se", "vs", "versus", "compared", "compare", "it", "its", "this", "that", "month", "mahine",
               "average", "avg", "mean", "ausat", "sum", "rate", "percent", "percentage", "value", "values", "numbers"}
_UNIT_AFTER = re.compile(r"\s*(orders?|designs?|pcs|pieces|qty|units|mtr|cr|crore|lakh|lakhs|l)\b", re.I)
_CHANGE_W = re.compile(r"\b(increase\w*|decrease\w*|growth|grew|change|changed|badh\w*|ghat\w*|decline\w*|drop\w*|"
                       r"girawat|gir\w*)\b", re.I)
_MORE_W = re.compile(r"\b(difference|diff|fark|farak|antar|gap|more|less|zyada|jyada|kam|higher|lower|compare|"
                     r"comparison)\b", re.I)
_SUM_W = re.compile(r"\b(total|sum|milake|mila ke|jod\w*|combined|together|altogether)\b", re.I)
_AVG_W = re.compile(r"\b(average|avg|mean|ausat)\b", re.I)


def given_numbers(text: str) -> list[tuple[str, float, str]] | None:
    """Figures the person typed in ("Deepika has 120 orders and Keerti has 90") -> [(label, value, unit)], or None.
    Month labels ("October-26"), years and "top 5" are not figures."""
    clean = re.sub(r"\b([A-Za-z]+)-\d{2}\b", r"\1", text)
    clean = re.sub(r"\b20\d\d\s*-\s*\d\d\b|\bfy\s*20\d\d\b|\b20\d\d\b", " ", clean, flags=re.I)
    out, prev = [], 0
    ft = re.search(r"\bfrom\s+₹?\d[\d,.]*\s*\w*\s+to\s+₹?\d", clean, re.I)      # "from 100,000 to 150,000"
    for m in re.finditer(r"₹?\s*(\d[\d,]*(?:\.\d+)?)\s*(cr|crore|lakhs?|lacs?|k|%)?(?![\w])", clean, re.I):
        before = clean[max(0, m.start() - 8):m.start()].lower()
        if re.search(r"\b(top|bottom|last|first|pehle)\s*$", before):
            prev = m.end()
            continue
        suffix = (m.group(2) or "").lower()
        value = to_number(m.group(1), None if suffix == "%" else suffix)
        words = [w for w in re.findall(r"[A-Za-z']+", clean[prev:m.start()]) if w.lower().strip("'s") not in _GIVEN_DROP
                 and w.lower() not in _GIVEN_DROP]
        words = [re.sub(r"'s$", "", w) for w in words]
        label = words[-1] if words and _MONTH_WORD.match(words[-1]) else " ".join(words[-2:])
        after = re.match(r"\s*(?:orders?|designs?|pcs|pieces|lakhs?|cr|crore|%)?\s*(?:for|of|in|ka|ke|ki)\s+([A-Z][A-Za-z]+|"
                         r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*)", clean[m.end():], re.I)
        if after:
            label = after.group(1)               # "57.4% for Keerti", "40 lakh in September": the name comes after
        unit_m = _UNIT_AFTER.match(clean[m.end():])
        unit = "%" if suffix == "%" else (unit_m.group(1).lower() if unit_m and unit_m.group(1).lower() not in
                                          ("cr", "crore", "lakh", "lakhs", "l") else "")
        if ft and len(out) < 2 and ft.start() <= m.start() <= ft.end() + 20:
            label = "Before" if not out else "After"
        out.append((label.title() if label else f"Value {len(out) + 1}", value, unit))
        prev = m.end()
    return out if len(out) >= 2 else None


def given_calc(text: str) -> str | None:
    """Works a calculation out from the person's own figures. None when the message isn't one."""
    t = norm(text)
    if _arithmetic(t) or _N_OF_NUMBERS.match(t):
        return None                              # "54338 minus 50580" is plain arithmetic, handled elsewhere
    vals = given_numbers(text)
    if not vals:
        return None
    pct = bool(PCT_WORD.search(t)) or "%" in text
    change, more, total, avg = _CHANGE_W.search(text), _MORE_W.search(text), _SUM_W.search(text), _AVG_W.search(text)
    if not (pct or change or more or total or avg):
        return None
    unit = next((u for _, _, u in vals if u and u != "%"), "")
    show = lambda v: f"{num(v)} {unit}".strip()
    names = ", ".join(f"{lab} {show(v)}" for lab, v, _ in vals)
    lines = [f"Using the numbers you gave: {names}."]
    if avg and not (change or more):
        a = sum(v for _, v, _ in vals) / len(vals)
        lines.append(f"Average: **{show(a)}** ({' + '.join(num(v) for _, v, _ in vals)} = {num(sum(v for _, v, _ in vals))}; "
                     f"÷ {len(vals)} = {num(a)}).")
    elif total and not (change or more or pct):
        s = sum(v for _, v, _ in vals)
        lines.append(f"Total: **{show(s)}** ({' + '.join(num(v) for _, v, _ in vals)}).")
    elif len(vals) == 2 and change:
        (la, a, _), (lb, b, _) = vals
        d = b - a
        word = "increase" if d > 0 else "decrease" if d < 0 else "no change"
        lines.append(f"Change from {la} to {lb}: **{'+' if d > 0 else '−' if d < 0 else ''}{show(abs(d))}** ({num(b)} − {num(a)}).")
        if a:
            lines.append(f"Percentage {word}: **{abs(d) / abs(a) * 100:.2f}%** ({num(abs(d))} ÷ {num(abs(a))} × 100).")
        else:
            lines.append(f"{la} is 0, so a percentage change can't be worked out.")
    elif len(vals) == 2:
        (la, a, _), (lb, b, _) = vals
        if a == b:
            lines.append(f"Both are the same ({show(a)}), so there is no difference.")
        else:
            (hl, h), (ll, lo) = ((la, a), (lb, b)) if a > b else ((lb, b), (la, a))
            lines.append(f"Difference: **{show(h - lo)}** ({num(h)} − {num(lo)}); {hl} is higher.")
            if lo:
                lines.append(f"{hl} is **{(h - lo) / lo * 100:.2f}% more** than {ll} ({num(h - lo)} ÷ {num(lo)} × 100).")
            if h:
                lines.append(f"{ll} is **{(h - lo) / h * 100:.2f}% less** than {hl} ({num(h - lo)} ÷ {num(h)} × 100).")
            if unit == "%" or all(u == "%" for _, _, u in vals):
                lines.append(f"As percentages, the gap is **{h - lo:.2f} percentage points**.")
    else:
        return None
    return "\n".join(lines)
