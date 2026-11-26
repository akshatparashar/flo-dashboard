"""Question planning for FLO Assistant: splitting one message into its separate questions, and turning short
follow-ups ("compare both", "give me the total", "designer-wise") into full questions using the conversation so far.

Only words are handled here. Which page and which figure answer each question is still decided by engine.py, from
the dashboard's own labels, so nothing in this file knows any business numbers or names.
"""
from __future__ import annotations

import re

# "... and how much is pending" / "... aur kitna completed" - an "and" that starts a new question
_QWORDS = (r"how|what|which|who|whose|when|kitna|kitne|kitni|kya|kaun|kon|show|tell|give|list|batao|dikhao|is|are|"
           r"the|her|his|its|their|uska|uski|uske|unka|unki|iska|total|pending|completed|complete|repeat|new|average")
_AND_Q = re.compile(rf"\s+(?:and|aur|also|plus|as well as|&|then)\s+(?=(?:{_QWORDS})\b)", re.I)
# any "and": a clause that turns out not to be a question is joined back by the engine
_AND_ANY = re.compile(r"\s+(?:and|aur|also|plus|as well as|&|then)\s+(?![\d₹])", re.I)
# ", " between words (not inside numbers like 1,234)
_COMMA = re.compile(r"(?<!\d),\s*|,\s+")
_HARD = re.compile(r"[?;\n]+|(?<=[a-z%)\]])\.\s+", re.I)
_LEAD = re.compile(r"^\s*(?:and|aur|also|plus|then|&|,|so|ok|okay)\b[\s,]*", re.I)
# a clause that states figures ("October is 32 and November is 5") is context for the next question, not a question
STATEMENT = re.compile(r"\b(?:is|are|was|were|tha|the|thi|hai|hain|=)\s+[₹]?\d", re.I)

BOTH = re.compile(r"\b(compare (?:both|them|the two|these|those|those two|dono)|both|dono(?:no)?|"
                  r"which (?:one )?(?:is |was |has )?(?:higher|more|bigger|greater|lower|less|smaller|better|worse)|"
                  r"kaun zyada|kon zyada|kiska zyada|kiske zyada|kaun kam|kiska kam)\b", re.I)
COMPARE_WITH = re.compile(r"\b(compare (?:it |this |that )?with|compare to|vs\.?|versus|ke saath compare|se compare)\b",
                          re.I)
TOTAL_ONLY = re.compile(r"^\s*(?:give me |show me |show |tell me |what is |what's |whats )?(?:the )?"
                        r"(?:total|overall|grand total|sum|kul|sab milake|sab mila ke|total kitna)"
                        r"(?: (?:of all|for all|of everyone|kitna hai|batao|please))?\s*[?.!]*\s*$", re.I)
WISE = re.compile(r"\b(designer|team|vendor|client|fabricator|category|month)[- ]?wise\b|"
                  r"\b(?:har|each|every|all) (designer|team|vendor|client|fabricator|category|month)s?\b", re.I)
GLOBAL = re.compile(r"\b(total|overall|all|everyone|company|flo|sab|sabhi|kul|entire|whole)\b", re.I)


def split_questions(text: str) -> list[tuple[str, str]]:
    """Cuts a message into clauses: [(joiner, clause)], where joiner is what stood before the clause (", " or
    " and "). The engine joins back clauses that are not questions on their own using that joiner."""
    parts: list[tuple[str, str]] = []
    text = re.sub(r"\bvisits?\s*(?:and|&|aur)\s*(meetings?)\b", r"visits \1", text, flags=re.I)
    for chunk in _HARD.split(text):
        first_c = True
        for piece in _COMMA.split(chunk):
            first_a = True
            for bit in _AND_ANY.split(piece):
                sep = "\n" if first_c and first_a else (", " if first_a else " and ")
                parts.append((sep, bit))
                first_a = False
            first_c = False
    out = []
    for sep, p in parts:
        p = _LEAD.sub("", p or "").strip(" ,.")
        if p:
            out.append((sep, p))
    return out


def metric_of(ctx: dict) -> str:
    """The figure an earlier answer was about, as words a question can use."""
    o = ctx.get("orders") if isinstance(ctx, dict) else None
    if o:
        kind = {"NEW": "new ", "REPEAT": "repeat "}.get(o.get("kind") or "", "")
        return f"{kind}{o.get('noun') or 'orders'}"
    return str(ctx.get("metric") or "")


def names_of(ctx: dict) -> list[str]:
    return [str(e.get("value")) for e in (ctx.get("entities") or []) if e.get("type") not in ("month", "po")]


# "pichhle month se compare karo" / "pichhle month ke comparison mein ..." / "previous month's change"
PREV_MONTH = re.compile(r"\b(?:pichh?le?|pichla|previous|prior|last|purane)\s+(?:month|mahine|mahina)\b", re.I)
PREV_COMPARISON = re.compile(r"\b(?:comparison|compare\w*|change|growth|difference|increase|decrease)\b.*", re.I)


def previous_window(ctx_months: list[str], text: str, fy: list[str]) -> list[str] | None:
    """Months for a "previous month" follow-up, worked out from the months the conversation is comparing.

    * "pichhle month ke comparison mein kitna increase hua?" after comparing October -> November: the comparison
      one step back, i.e. September -> October.
    * "pichhle month se compare karo" after one month (or when the comparison is phrased "with last month"): that
      month against the month before it.
    Returns None when the text has no such phrase or the conversation has no month to count back from.
    """
    if not PREV_MONTH.search(text):
        return None
    seen = sorted({m for m in ctx_months if m in fy}, key=fy.index)
    if not seen:
        return None
    first, last = fy.index(seen[0]), fy.index(seen[-1])
    own = re.search(r"(?:month|mahine|mahina)(?:'?s)?\s+(?:ke\s+|ka\s+|ki\s+)?(?:comparison|change|growth|difference)|"
                    r"(?:ke|ka|ki)\s+(?:comparison|change|growth|difference)|comparison\s+(?:mein|me)|"
                    r"(?:comparison|change|growth)\s+of\s+(?:the\s+)?(?:previous|last)", text, re.I)
    if len(seen) >= 2 and own:
        if first == 0:
            return None
        return [fy[first - 1], fy[first]]
    if last == 0:
        return None
    return [fy[last - 1], fy[last]]


# "this year", "FY 2026-27", "year to date", "all months": the whole financial year so far, whatever months were
# talked about before (a narrower period has to be named in the question itself).
WHOLE_YEAR = re.compile(r"\b(this year'?s?|current year|this fy|fy\s*20\d\d(?:\s*-\s*\d\d)?|20\d\d\s*-\s*\d\d|"
                        r"financial year|year to date|ytd|all months|all available months|whole year|full year|"
                        r"entire year|year so far|poore saal|poora saal|is saal|saal bhar|since april)\b", re.I)
YEAR_WORDS = {"year", "date", "fy", "ytd", "financial", "2026-27", "current", "whole", "entire", "full", "saal", "poora",
              "poore", "bhar", "is", "this", "all", "available", "months"}
