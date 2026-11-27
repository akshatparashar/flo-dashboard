"""Other words for the same thing ("inventory" = stock, "supplier" = vendor, "unfinished" = open ...), and opposites
("undelivered" = pending, "failed samples" = rejected, "fast selling" against "unsold").

``normalise`` rewrites only those words into the dashboard's own, before the question is read. Which word is right often
depends on the subject ("delivered" pcs are received pcs, but a delivered task is not a thing), so most rules carry a
condition. It never adds or changes a figure, a name or a month.
"""
from __future__ import annotations

import re

TASKS = r"\b(tasks?|kaam|delegation)\b"
SAMPLE = r"\bsamples?\b"
PRODUCTION = r"\bproduction\b"
# "maal" is usually the stock, but not when it is arriving or being issued
MOVING_MAAL = r"\b(aaya|aaye|aayi|aya|aye|received|incoming|bheja|bheje|issue\w*|fabric|kapda|fabricators?|karigar|po)\b"
NOT_SOLD = r"\b(nahi|nahin|nhi|na|not|never|bina|kab)\b"
CODE = r"\b(?:\d{2}|[a-z]\d{2})\s*-\s*\d{3,}"
STOCKISH = r"\b(stock|inventory|maal|godown|warehouse)\b"

# (pattern, replacement, only if the question has this, unless it has this); applied in order
RULES: list[tuple[str, str, str | None, str | None]] = [
    # judgement words and sizes
    (r"\b(?:sabse )?(?:kharab|bekaar|bekar|ghatiya|bura|buri)\b", "worst",
     r"\b(vendors?|suppliers?|fabricators?|karigars?|designers?|clients?)\b", None),
    (r"\b(?:kharab|bekaar|bekar)\b", "rejected", SAMPLE, None),
    (r"^\s*(?:show |batao )?(?:the )?(?:fabricator|karigar)s?(?: ka| ke)? stock(?: batao| dikhao| kitna hai)?\s*[?.!]*$",
     "fabricators page summary", None, None),
    (r"\b(?:sabse )?(?:accha|achha|acha|badhiya|behtar|behtareen)\b(?= (?:\w+ )?(?:vendor|supplier|fabricator|karigar))",
     "best", None, None),
    (r"\bsabse (?:bada|badi|bade)\b", "top", None, None),
    (r"\bsabse (?:chhota|chota|chhoti|choti|chhote|chote)\b", "lowest", None, None),
    # money and trade
    (r"\bearnings?\b", "revenue", None, None),
    (r"\bsuppliers\b", "vendors", None, None),
    (r"\bsupplier\b", "vendor", None, None),
    (r"\b(?:bhav|bhaav|daam)\b", "rate", None, None),
    (r"\b(?:costliest|priciest)\b", "most expensive", None, None),
    # samples
    (r"\b(?:accepted|passed|cleared|pass hue)\b", "approved", SAMPLE, None),
    (r"\b(?:failed|declined|refused|fail hue)\b", "rejected", SAMPLE, None),
    # tasks: open and done
    (r"\b(?:unfinished|incomplete|not (?:yet )?(?:completed?|done|finished)|adhur[aei]|baki wale)\b", "open", TASKS, None),
    (r"\b(?:closed|finished|nipta\w*|khatam)\b", "completed", TASKS, None),
    # production: what is left and what has come
    (r"\b(?:incomplete|unfinished|remaining|undone|not (?:yet )?(?:completed?|made|done))\b", "pending", PRODUCTION,
     r"\b(fabricators?|karigar)\b"),
    (r"\b(?:completed|finished|delivered)\b", "received", PRODUCTION, r"\b(rate|on.?time|%|percent\w*)\b"),
    (r"\b(?:undelivered|unreceived|not (?:yet )?(?:received|delivered)|yet to (?:be )?(?:received|come|arrive))\b",
     "pending", None, TASKS),
    (r"\bdelivered\b(?= (?:pcs|pieces|qty|quantity|fabric|mtr))", "received", None, TASKS),
    (r"^.*\b(?:sabse (?:zyada|jyada) overdue (?:kiska|kiske|kiski)|(?:who|whose) (?:has )?(?:the )?most overdue)\b.*$",
     "which fabricator has the most overdue pcs", None,
     r"\b(designers?|fabricators?|vendors?|tasks?|po|pos|samples?|promis\w*|flo future)\b"),
    # production and designers
    (r"\blate (?:pcs|pieces|qty)\b", "overdue pcs", None, r"\b(po|pos|fabric|tasks?)\b"),
    (r"^\s*designers? ranking\s*[?.!]*$", "top 10 designers", None, None),
    (r"\bkaam\b", "orders", r"\bdesigners?\b", r"\b(tasks?|delegation|sir|mam)\b"),   # a designer's work is orders
    (r"^.*\bpending\b.*\bfabricators? ke paas\b.*$", "fabricator wise pending", None,
     r"\b(sabse|most|least|kis|kaun)\b"),
    (r"^\s*top (?:ka |ke |category )?(?=(?:pending|received)\b)", "tops ", None, None),
    # tasks left
    (r"\b(?:remaining|left)\b", "open", TASKS, r"\b(fabricators?|production)\b"),
    # selling, and its opposite
    (r"\b(?:slowest[- ]?selling|least[- ]?selling|worst[- ]?selling|sabse kam bik\w+)\b", "longest unsold", None, None),
    (r"\b(?:fast(?:est)?[- ]?(?:moving|selling)|best[- ]?sell(?:ing|ers?)|top[- ]?sell(?:ing|ers?)|"
     r"sabse (?:zyada|jyada) bik\w+|most sold)\b", "fast selling", None, None),
    (r"\b(?:non[- ]?moving|not moving|slow[- ]?moving|stagnant|stuck|non[- ]?selling|not selling)\b", "unsold", None,
     r"\b(po|pos|tasks?|samples?|production)\b"),
    (r"\b(?:kitna|kitne|kitni) (?:maal |pcs |pieces )?(?:bika|bike|biki|bik gaya|bik gaye)\b", "sale pcs kitne", None,
     f"{NOT_SOLD}|{CODE}|{STOCKISH}"),
    (r"\bhow (?:much|many)(?: pcs| pieces)?(?: (?:have|did) we)? s(?:old|ell)\b", "how many sale pcs", None,
     f"{NOT_SOLD}|{CODE}|{STOCKISH}"),
    # stock
    (r"\bsold stock\b", "fast selling stock", None, NOT_SOLD),
    (r"\binventory\b", "stock", None, None),
    (r"\bmaal\b", "stock", r"\b(maal)\b.*\b(kitna|pada|padha|purana|purane|naya|value|godown|warehouse|bika|nahi)\b|"
                            r"\b(kitna|purana|purane|naya|naye|godown|warehouse|unsold)\b.*\bmaal\b", MOVING_MAAL),
    (r"\b(?:in (?:the )?)?(?:godown|warehouse)(?: (?:me|mein|ka|ki|wala))?\b(?=.*\bstock\b)", "", None, None),
    (r"(?<=stock )(?:in (?:the )?)?(?:godown|warehouse)(?: (?:me|mein))?\b", "", None, None),
    (r"\b(?:godown|warehouse)\b", "stock", None, r"\bstock\b"),
    (r"\b(?:newest|latest|new|recent|naya|nayi|naye)[- ]stock\b", "fresh stock", None, None),
    (r"\b(?:total|poora|pura|entire|overall|all) stock\b", "closing stock", None, r"\b(fabricators?|karigar|page|summary)\b"),
]
_RULES = [(re.compile(p, re.I), r, re.compile(i, re.I) if i else None, re.compile(u, re.I) if u else None)
          for p, r, i, u in RULES]


def normalise(question: str) -> str:
    """The question with other words for dashboard things replaced by the dashboard's own words."""
    text = question
    for pattern, new, only, unless in _RULES:
        # conditions read the text as it stands now, so an earlier rewrite ("inventory" -> "stock") counts
        if (only and not only.search(text)) or (unless and unless.search(text)):
            continue
        text = pattern.sub(new, text)
    return text if text == question else re.sub(r"\s+", " ", text).strip()
