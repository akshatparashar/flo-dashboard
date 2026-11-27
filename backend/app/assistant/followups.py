"""Short follow-ups ("uska received?", "April me?", "kiske hain?") rebuilt into full questions.

The engine answers full questions well; a follow-up fails when it is read on its own. So after every answer we note
what it was about (``annotate``: topic, the name that came out on top, the figure asked for, months), and before the
next question is read we rebuild it from those notes (``resolve``). Both only deal in words: every figure still comes
from the engine and the dashboard. ``resolve`` returns None unless the message is clearly one of these follow-ups, so
ordinary questions go through unchanged.
"""
from __future__ import annotations

import re

MAX_WORDS = 8
PRONOUN = re.compile(r"\b(uska|uske|uski|usko|usme|iska|iske|iski|isme|unka|unke|unki|unme|his|her|their|its)\b", re.I)
LEAD = re.compile(r"^\s*(?:(?:aur|and|ab|acha|accha|ok|okay|phir|fir|also|what about|how about)\b[\s,]*)+", re.I)
FILLER = {"aur", "and", "ab", "me", "mein", "ka", "ke", "ki", "ko", "in", "for", "of", "the", "what", "about", "how",
          "hai", "hain", "tha", "kitna", "kitne", "kitni", "batao", "bataiye", "dikhao", "month", "mahine", "wale",
          "wala", "to", "bhi", "please", "kya", "se"}
COMPARE_BOTH = re.compile(r"\b(dono|compare both|compare them|kiska zyada|kiske zyada|kaun zyada|kon zyada|kiska kam|"
                          r"which (?:one )?is (?:higher|more|lower|less))\b", re.I)
TOP_Q = re.compile(r"\b(sabse (?:zyada|jyada|kam)|most|highest|least|lowest)\b", re.I)
CHEAP = re.compile(r"\b(sasta|sasti|sabse sast\w*|cheap\w*|lowest rate|sabse kam)\b", re.I)
IOS_METRICS = [(r"\bnet sale\b", "net sale"), (r"\bsale amount\b", "sale amount"), (r"\bincoming\b", "incoming pcs"),
               (r"\bsale (?:pcs|pieces)\b", "sale pcs")]
FW_METRICS = [(r"\bdispatch\w*\b", "dispatched"), (r"\bpending\b", "pending"), (r"\border\w*\b", "order")]
PAGE_WORDS = {"production": "production", "fabricators": "fabricator", "po": "fabric po"}
PEOPLE_DIMS = ("fabricator", "vendor", "designer", "client")


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+(?:-[0-9]{2})?", text.lower())


def _month_words(months) -> set[str]:
    out = set()
    for m in months:
        name, _, yy = m.partition("-")
        out |= {name.lower(), name[:3].lower(), yy, m.lower()}
    return out


def _rest(text: str, months) -> list[str]:
    """The words left once fillers and month names are taken out."""
    gone = FILLER | _month_words(months)
    return [w for w in _words(text) if w not in gone]


def _strip(text: str) -> str:
    return re.sub(r"\s+", " ", LEAD.sub("", PRONOUN.sub(" ", text))).strip(" ?.!,")


def _history_names(history) -> list[str]:
    """Designers talked about earlier, latest first."""
    seen: list[str] = []
    for c in reversed(history or []):
        if not isinstance(c, dict):
            continue
        for e in c.get("entities") or []:
            if e.get("type") == "designer" and e.get("value") not in seen:
                seen.append(e.get("value"))
    return seen


# ------------------------------------------------------------------------------------------------ resolve
def resolve(question: str, ctx: dict | None, history: list[dict], months: list[str], entities: list) -> str | None:
    """The full question a short follow-up stands for, or None. ``months`` / ``entities`` are those named in it."""
    try:
        return _resolve(question, ctx, history, months, entities)
    except (AttributeError, TypeError, KeyError, ValueError):       # a context from the browser can be anything
        return None


def _resolve(question: str, ctx: dict | None, history: list[dict], months: list[str], entities: list) -> str | None:
    if not isinstance(ctx, dict) or not ctx.get("topic") or len(question.split()) > MAX_WORDS:
        return None
    topic, top, asked = ctx["topic"], ctx.get("top") or {}, ctx.get("asked") or ""
    q = question.strip()
    low = q.lower()
    pronoun = bool(PRONOUN.search(low))
    rest = _rest(_strip(q), months)
    month = " and ".join(months)
    people = [e for e in entities if e.type in PEOPLE_DIMS]

    if topic == "flo" and COMPARE_BOTH.search(low) and not people:
        names = _history_names(history)
        if len(names) >= 2:
            return f"compare {names[1]} and {names[0]} flo future pending"
        return None
    if topic == "flo" and ctx.get("overdue") and re.search(r"\b(kiske|kiska|kiski|kaunse|konse|who|whose|which ones?|"
                                                          r"list|naam)\b", low) and len(rest) <= 3:
        return "flo future ke kaunse samples overdue hai"

    if topic == "fw":
        metric = next((m for pat, m in FW_METRICS if re.search(pat, low)), "")
        known = {"dispatched", "dispatch", "pending", "order", "orders", "pcs"}
        if (months or metric) and all(w in known for w in rest):
            when = month or " and ".join(ctx.get("months") or [])
            return " ".join(x for x in ("fw orders", metric or ctx.get("ask_metric") or "", when) if x)
        return None

    if topic == "deliveries":
        if months and all(w in {"pcs", "aane", "pending", "delivery", "deliveries"} for w in rest):
            return f"expected deliveries {month}"
        return None

    if topic == "target":
        if re.search(r"\b(ab tak|kitna hua|kitna ho gaya|ho chuka|achieved|kitna aaya)\b", low) and not re.search(
                r"\b(bacha|baaki|baki|remaining|revenue)\b", low) and not people:
            return f"target achieved in {month}" if months else "target achieved kitna hai"
        if months and not rest:
            return f"target achieved in {month}"
        return None

    if topic == "ios":
        metric = next((m for pat, m in IOS_METRICS if re.search(pat, low)), None)
        known = {"net", "sale", "sales", "amount", "incoming", "pcs", "pieces"}
        if months and not rest and ctx.get("ask_metric"):
            return f"{ctx['ask_metric']} in {month}"
        if metric and not months and ctx.get("months") and all(w in known for w in rest) and LEAD.search(low):
            return f"{metric} in {' and '.join(ctx['months'])}"     # "aur incoming?" keeps the month in hand
        return None

    if topic == "delegation":
        persons = ctx.get("persons") or []
        who = persons[0] if len(persons) == 1 else ""        # with two in hand, the list names who holds each task
        if re.search(r"\b(kitne din|how long|since when|kab se)\b", low) and not people:
            return " ".join(x for x in ("daily delegation", who, "open tasks kitne din se") if x)
        if len(people) == 1 and not rest[1:] and people[0].display.lower() in low:
            return f"daily delegation {people[0].display.title()} tasks"
        return None

    if topic == "rates":
        fabric = next((e.display for e in entities if e.type == "fabric"), None)
        known = {"width", "inch", "44", "60", "36", "rate", "rates", "vendor", "wala", "kaun"}
        width = re.search(r"\b(44|60|36)\b", low)
        current = ctx.get("fabric")
        if fabric and ctx.get("cheap") and all(w in known or w in _words(fabric) for w in rest):
            return f"{fabric} ka sabse sasta vendor"
        if not fabric and current:
            if width and not pronoun and ctx.get("cheap") and all(w in known for w in rest):
                return f"{current} {width.group(1)} width ka sabse sasta vendor"
            if pronoun and top.get("name") and "vendor" not in low:
                size = f"{width.group(1)} width " if width else ""
                return f"{top['name']} ka {current} {size}rate"
            if pronoun and "vendor" in low:
                return f"{current} ka sabse sasta vendor"
        return None

    if topic == "po":
        if TOP_Q.search(low) and re.search(r"\bvendors?\b|\bkis\b", low) and not re.search(
                r"\b(po|fabric|metre|meter|mtr|pending|order\w*|received|rate)\b", low) and ctx.get("overdue"):
            return f"kis vendor ke {'sabse kam' if re.search(r'kam|least|lowest', low) else 'sabse zyada'} overdue PO"
        if months and not rest and asked:
            return f"{asked} in {month}"

    # "category wise pending" -> "sabse zyada?": the same breakdown, its leader
    if topic == "production" and ctx.get("dim") in ("category", "month", "fabricator") and TOP_Q.search(low) and \
            all(w in {"sabse", "zyada", "jyada", "kam", "most", "highest", "least", "lowest", "which", "one"}
                for w in rest) and not months:
        order = "least" if re.search(r"\b(kam|least|lowest)\b", low) else "most"
        return f"which {ctx['dim']} has {order} {ctx.get('figure') or 'pending'} in production"

    # "sabse zyada kiske paas?" - rank the figure already in hand
    if topic in ("fabricators", "production") and TOP_Q.search(low) and not people and re.search(
            r"\b(kiske|kiska|kis|kaun|who|whose|which)\b", low):
        words = [w for w in rest if w not in {"sabse", "zyada", "jyada", "kam", "most", "highest", "least", "lowest",
                                              "kiske", "kiska", "kis", "kaun", "paas", "who", "whose", "which", "has"}]
        figure = ctx.get("figure")
        if not words and figure:
            order = "sabse kam" if re.search(r"\b(kam|least|lowest)\b", low) else "sabse zyada"
            return f"{PAGE_WORDS[topic]} me {order} {figure} kiske paas hai"

    if topic == "fabricators" and months and re.search(r"\bincoming\b", low) and not re.search(r"\b(in ?out|sale)\b", low):
        return f"fabricator monthly incoming in {month}"

    # "uska received?" - the name that came out on top, with the page it came from
    if pronoun and top.get("name") and topic in PAGE_WORDS and not people:
        body = _strip(q)
        if body and len(rest) <= 4:
            return f"{top['name']} {PAGE_WORDS[topic]} {body}"
    return None


# ------------------------------------------------------------------------------------------------ annotate
def _first_named(answer: str, vocab, dim: str) -> str | None:
    """The first name of that kind in the answer (a ranking names its leader first)."""
    upper = answer.upper()
    best = None
    for (kind, _), ent in vocab.entities.items():
        if kind != dim:
            continue
        m = re.search(rf"(?<![A-Z0-9]){re.escape(ent.display.upper())}(?![A-Z0-9])", upper)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), ent.display)
    return best[1] if best else None


def annotate(ctx: dict, asked: str, answer: str, previous: dict | None, vocab, months: list[str],
             entities: list) -> dict:
    """The working context of an answer, plus the notes ``resolve`` needs. Returns a new dict."""
    ctx = dict(ctx)
    if isinstance(previous, dict) and not isinstance(previous.get("top"), (dict, type(None))):
        previous = {k: v for k, v in previous.items() if k != "top"}
    previous = previous if isinstance(previous, dict) else {}
    low = asked.lower()
    page = ctx.get("page")
    head = answer[:160]
    if page == "stock-ageing":
        topic = "stock"
    elif "FW ORDER'S" in head:
        topic = "fw"
    elif "Expected deliveries" in head:
        topic = "deliveries"
    elif page == "target":
        topic = "target"
    elif page == "in-out-sale":
        topic = "ios"
    elif page == "vendor-rate":
        topic = "rates"
    elif page == "daily-delegation":
        topic = "delegation"
    elif page == "flo-future":
        topic = "flo"
    elif page == "fabricator" or "Fabricators page" in head:
        topic = "fabricators"
    elif page == "fabric-po" or re.search(r"\bpos?\b", low) and page in ("overview", "fabric-po"):
        topic = "po"
    elif page == "production":
        topic = "production"
    else:
        return ctx
    same = previous.get("topic") == topic
    ctx["topic"], ctx["asked"] = topic, asked
    if not ctx.get("months"):
        ctx["months"] = list(months) or (previous.get("months") or [] if same else [])

    # the name in hand: one the question named, else the leader of a ranking, else the one from just before
    dim = ctx.get("dim") if ctx.get("dim") in PEOPLE_DIMS else \
        {"fabricators": "fabricator", "production": "fabricator", "po": "vendor", "rates": "vendor"}.get(topic)
    named = next((e for e in entities if e.type in PEOPLE_DIMS), None)
    leader = None
    if named is not None:
        leader = {"dim": named.type, "name": named.display}
    elif dim and (ctx.get("intent") in ("rank", "rates") or re.search(r"sabse|highest|lowest|cheapest", head, re.I)
                  or TOP_Q.search(low) or CHEAP.search(low)):
        name = _first_named(answer, vocab, dim)
        leader = {"dim": dim, "name": name} if name else None
    top = leader or (previous.get("top") if same else None)
    if top:
        ctx["top"] = top

    if topic == "ios":
        ctx["ask_metric"] = next((m for pat, m in IOS_METRICS if re.search(pat, low)), None) or \
            (previous.get("ask_metric") if same else None) or str(ctx.get("metric") or "").lower()
    elif topic == "fw":
        ctx["ask_metric"] = next((m for pat, m in FW_METRICS if re.search(pat, low.replace("fw orders", ""))), "") or ""
    elif topic == "rates":
        fabric = next((e.get("value") for e in ctx.get("entities") or [] if e.get("type") == "fabric"), None)
        ctx["fabric"] = fabric or (previous.get("fabric") if same else None)
        ctx["cheap"] = bool(CHEAP.search(low))
    elif topic == "po":
        ctx["overdue"] = "overdue" in low or "overdue" in str(ctx.get("metric", "")).lower() or \
            bool(same and previous.get("overdue"))
        ctx["asked"] = re.sub(r"\s+in\s+[A-Z][a-z]+-\d{2}$", "", asked)
    elif topic == "flo":
        ctx["overdue"] = "overdue" in low or "overdue" in str(ctx.get("metric", "")).lower()
    elif topic == "delegation":
        ctx["persons"] = (ctx.get("deleg") or {}).get("person") or []
    if topic in ("fabricators", "production"):
        metric = str(ctx.get("metric") or "").lower()
        ctx["figure"] = next((w for k, w in (("remaining", "remaining"), ("rcvd", "received"), ("received", "received"),
                                             ("pending", "pending"), ("incoming", "monthly incoming"),
                                             ("under production", "under production")) if k in metric), None) or \
            (previous.get("figure") if same else None)
    return ctx
