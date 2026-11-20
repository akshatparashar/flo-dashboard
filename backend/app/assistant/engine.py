"""Rule-based question answering over the dashboard.

How a question is answered:
  1. Read the dashboard (every page, unfiltered) to learn its vocabulary: designer, client, vendor, fabricator and
     category names, months, PO numbers, and every KPI and table-column label.
  2. Pull months, names and the answer style ("in one word", "in detail") out of the question; the rest is matched
     against the labels.
  3. Build candidate answers (a KPI with the question's filters applied, a table cell for a named row, a ranking,
     a month-by-month list, a comparison), score them, and phrase the best one.

Nothing here writes anywhere, and all numbers come from the fetch callback, i.e. the dashboard's own endpoints.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Callable

import calendar
from datetime import date

from . import calc, fmt
from .orders import OrderAnalyst
from .pages import (DIMENSION_PLURALS, DIMENSION_WORDS, FEATURES, HELP, HOME_PAGE, OPTION_TYPES, PAGES, PLURALS,
                    QUALITY, ROW_TYPES, TYPE_NAMES)
from .text import (BOTTOM, CONTEXT_WORDS, GENERIC_NAME_WORDS, HOWMANY, MARKERS, MONTH_ALIASES, STOP, TOP, TREND, WORDS,
                   label_tokens, language_of, name_key, norm, raw_tokens, similar, tokens)

Fetch = Callable[[str, dict], dict]

THRESHOLD = 1.0           # below this, the rules are not sure what was asked
SOFT = {"new", "yearly", "annual", "fy", "all", "sheet", "overall", "qty", "mtr", "day"}
SKIP_KEYS = {"meta", "options", "charts", "matrix", "heatmap", "lines", "top_repeat", "gauge", "schedule"}
SPECIAL_ROW = re.compile(r"^\(.*\)$|^(total|grand total)$", re.I)
MAX_QUESTION = 500
PHRASE_INTENTS = {"value", "rank", "trend", "compare", "calc", "record", "count", "list", "explain", "where", "page",
                  "help", "unknown"}
# words that can sit in a question without naming a different figure
HARMLESS = {"more", "less", "much", "many", "extra", "also", "else", "still", "yet", "only",
            "per", "each", "every", "give", "make", "know", "want", "whole", "overall", "entire", "full"}
_DEVANAGARI = re.compile(r"[\u0900-\u097f]")
_SMALLTALK = re.compile(r"\b(how are you|how r u|kaise ho|kaisa hai|kaisi ho|kya haal|what's up|whats up|sup bro)\b")


class DataUnavailable(Exception):
    pass


def _hint(h) -> str:
    h = str(h or "").strip()
    return "" if not h or re.match(r"^(sheet )?col(umn)?s? [A-Z]", h, re.I) else (h if h.endswith(".") else h + ".")


# ------------------------------------------------------------------------------------------------ data access
class Snapshot:
    """The dashboard as the assistant sees it during one question. Each page/filter combination is read once."""

    def __init__(self, fetch: Fetch):
        self._fetch = fetch
        self._cache: dict = {}

    def get(self, page: str, filters: dict | None = None) -> dict:
        filters = {k: list(v) for k, v in (filters or {}).items() if v}
        key = (page, tuple(sorted((k, tuple(v)) for k, v in filters.items())))
        if key not in self._cache:
            try:
                self._cache[key] = self._fetch(page, filters)
            except Exception as e:                       # HTTPException(503) when a sheet can't be read
                self._cache[key] = DataUnavailable(getattr(e, "detail", None) or str(e) or "unavailable")
        val = self._cache[key]
        if isinstance(val, DataUnavailable):
            raise val
        return val


def kpi_list(payload: dict) -> list[dict]:
    out = []

    def walk(o, group):
        if isinstance(o, dict):
            if isinstance(o.get("kpis"), list):
                out.extend({**k, "_group": group} for k in o["kpis"] if isinstance(k, dict) and k.get("label"))
            for k, v in o.items():
                if k not in SKIP_KEYS and k != "kpis" and not (isinstance(v, dict) and "rows" in v):
                    walk(v, k)
    walk(payload, "")
    return out


def table_list(payload: dict) -> list[tuple[str, dict]]:
    out = []

    def walk(o, name):
        if isinstance(o, dict):
            if isinstance(o.get("columns"), list) and isinstance(o.get("rows"), list):
                out.append((name, o))
                return
            for k, v in o.items():
                if k not in SKIP_KEYS:
                    walk(v, k)
    walk(payload, "")
    return out


def row_type(table: dict) -> str | None:
    cols = table.get("columns") or []
    return ROW_TYPES.get(norm(cols[0]["label"])) if cols else None


# ------------------------------------------------------------------------------------------------ vocabulary
@dataclass
class Entity:
    type: str
    display: str
    key: str
    raw: dict = field(default_factory=dict)       # page -> the exact option value on that page

    def ref(self):
        return {"type": self.type, "value": self.display}


class Vocabulary:
    def __init__(self, snap: Snapshot):
        self.entities: dict[tuple[str, str], Entity] = {}
        self.months: list[str] = []
        self.labels: set[str] = set()
        self.errors: dict[str, str] = {}
        for page in PAGES:
            try:
                data = snap.get(page)
            except DataUnavailable as e:
                self.errors[page] = str(e)
                continue
            for param, values in (data.get("options") or {}).items():
                etype = OPTION_TYPES.get(param)
                if not etype:
                    continue
                for v in values:
                    if etype == "month":
                        if v not in self.months and re.match(r"^[A-Za-z]+-\d{2}$", v):
                            self.months.append(v)
                        continue
                    self._add(etype, v, page)
            for name, t in table_list(data):
                if row_type(t) == "po":
                    for r in t["rows"]:
                        if r and r[0]:
                            self._add("po", str(r[0]), page)
            for k in kpi_list(data):
                self.labels.add(k["label"])
            for _, t in table_list(data):
                for c in t["columns"][1:]:
                    self.labels.add(c["label"])
        self.by_key: dict[str, list[Entity]] = {}
        self.by_first: dict[str, list[Entity]] = {}
        for e in self.entities.values():
            self.by_key.setdefault(e.key, []).append(e)
            first = e.key.split(" ")[0]
            if e.type != "po" and len(first) >= 4 and first not in GENERIC_NAME_WORDS:
                self.by_first.setdefault(first, []).append(e)
        self.common = set(STOP) | set(WORDS) | set(MONTH_ALIASES) | {
            w for lab in self.labels for w in raw_tokens(lab)} | {"page", "dashboard", "tab", "detail", "word"} | \
            set(DIMENSION_WORDS) | set(DIMENSION_PLURALS)

    def _add(self, etype, value, page):
        key = name_key(value)
        if not key:
            return
        e = self.entities.setdefault((etype, key), Entity(etype, value, key))
        e.raw.setdefault(page, value)
        if value.isupper() and not e.display.isupper():
            e.display = value

    def of_type(self, etype: str) -> list[Entity]:
        return [e for e in self.entities.values() if e.type == etype and not SPECIAL_ROW.match(e.display)]


# ------------------------------------------------------------------------------------------------ question
@dataclass
class Query:
    text: str
    toks: list[str] = field(default_factory=list)
    entities: list[Entity] = field(default_factory=list)
    months: list[str] = field(default_factory=list)
    dims: list[str] = field(default_factory=list)
    n: int = 1
    style: str = "normal"                      # terse | normal | detail
    pages: list[str] = field(default_factory=list)   # pages named in the question
    intent: str = "value"
    inherited: bool = False

    @property
    def markers(self):
        return {t for t in self.toks if t in MARKERS}

    @property
    def metric_toks(self):
        return {t for t in self.toks if t not in MARKERS and (t not in DIMENSION_WORDS or t == "po")}

    def scope(self, skip_type: str | None = None) -> str:
        parts = []
        names = [e.display for e in self.entities if e.type not in ("month", skip_type)]
        if names:
            parts.append("for " + " and ".join(names))
        parts.append(f"in {fmt.months(self.months)}" if self.months else "")
        return " ".join(p for p in parts if p)


_TERSE = re.compile(r"\b(one word|1 word|single word|only (the )?(number|value|figure)|just (the )?(number|value|"
                    r"figure)|number only|sirf (number|ek word|value)|bas number|ek word|in short|short me|"
                    r"no explanation)\b")
_DETAIL = re.compile(r"\b(in detail|detailed|details|detail me|breakdown|break down|break-up|breakup|full|vistar|"
                     r"vistaar|elaborate|explain in detail|with details)\b")
_EXPLAIN = re.compile(r"\b(what is meant|what does .* mean|meaning of|what is the meaning|matlab|kya hota|define|"
                      r"definition|means what|how is .* calculated|how .* calculated)\b")
_WHERE = re.compile(r"\b(where|kahan|kaha|kidhar|which page|kis page|kaunse page|konse page)\b")
_LIST = re.compile(r"\b(list|names|name all|kaun kaun|kon kon|which are the|show all|all the)\b")
_COMPARE = re.compile(r"\b(vs|versus|compare|comparison|compared|difference|mukabla|between)\b")
_GREET = re.compile(r"^\s*(hi+|hello|hey|namaste|namaskar|hola|good (morning|afternoon|evening)|yo)\b[\s!.?]*$")
_THANKS = re.compile(r"^\s*(thanks|thank you|thx|ty|dhanyavad|shukriya|great|nice|ok|okay|cool)\b[\s!.?a-z]*$")
_HELP = re.compile(r"\b(what can you do|help|how (do|can) i use you|who are you|what do you do|kya kar sakte)\b")
_HOWTO = re.compile(r"\b(how (do|does|can|to|is)|kaise|where is the|can i|is there)\b")
_FOLLOW = re.compile(r"^\s*(and|what about|how about|aur|or|same for|also|uska|unka|iska|for)\b")
_PRONOUN = re.compile(r"\b(her|his|their|its|she|he|they|uska|unka|iska|inka|same)\b")
_PO_NO = re.compile(r"\b(?:fpo\s*/?\s*)?(\d{3,6})\b")
_PLURAL_DIMS = "|".join(DIMENSION_PLURALS)
_EACH = re.compile(rf"\b(?:of|for|by|across|among) (?:all |each |every |the |all the )?(?:{_PLURAL_DIMS})\b|"
                   rf"\b(?:each|every|har|sabhi|sab|all) (?:{_PLURAL_DIMS}|{'|'.join(DIMENSION_WORDS)})\b")
_QUALITY = re.compile(r"\b(best|worst|reliable|unreliable)\b")


def _month_index(word: str) -> int | None:
    return MONTH_ALIASES.get(word)


def parse(question: str, vocab: Vocabulary, today_month: str | None) -> Query:
    q = Query(text=question)
    t = norm(question)
    if _TERSE.search(t):
        q.style = "terse"
    elif _DETAIL.search(t):
        q.style = "detail"
    t = _TERSE.sub(" ", t)
    t = _DETAIL.sub(" ", t)
    # "target kitna bacha / baki hai" asks for the remaining target, not pending pcs
    if re.search(r"\btarget\b", t):
        t = re.sub(r"\b(bacha|bachi|bache|baki|baaki|left)\b", "remaining", t)
    # "kitne PO aaye / bane" counts POs; the Hindi "came / made" must not turn into "received"
    if re.search(r"\bpos?\b|purchase orders?", t):
        t = re.sub(r"\b(aaye|aaya|aayi|aya|aye|bane|bana|banaye|hue|hui|raise|raised|placed)\b", " ", t)

    words = raw_tokens(t)
    used = [False] * len(words)

    # months ------------------------------------------------------------------
    fy = vocab.months
    by_no = {}
    for m in fy:
        no = _month_index(m.split("-")[0].lower())
        if no:
            by_no.setdefault(no, m)
    if today_month and today_month in fy:
        i = fy.index(today_month)
        rel = {("this", "month"): today_month, ("current", "month"): today_month, ("is", "mahine"): today_month,
               ("last", "month"): fy[i - 1] if i else None, ("previous", "month"): fy[i - 1] if i else None,
               ("pichhle", "mahine"): fy[i - 1] if i else None, ("pichle", "mahine"): fy[i - 1] if i else None,
               ("pichla", "mahina"): fy[i - 1] if i else None}
        for j in range(len(words) - 1):
            m = rel.get((words[j], words[j + 1]))
            if m:
                q.months.append(m)
                used[j] = used[j + 1] = True
    found = []
    for j, w in enumerate(words):
        if used[j]:
            continue
        base = w.split("-")[0]
        no = _month_index(base)
        if not no or no not in by_no:
            continue
        if base == "may" and j + 1 < len(words) and words[j + 1] in {"i", "you", "we", "be", "have"}:
            continue
        if base in {"mar", "jan", "dec"} and j > 0 and words[j - 1] in {"to", "will"}:
            pass
        found.append((j, by_no[no]))
        used[j] = True
        if j + 1 < len(words) and re.fullmatch(r"(20)?\d{2}", words[j + 1]):
            used[j + 1] = True
    # "april to june" / "april se june tak"
    if len(found) == 2 and any(words[k] in {"to", "se", "till", "until", "-", "through"}
                               for k in range(found[0][0] + 1, found[1][0])):
        a, b = fy.index(found[0][1]), fy.index(found[1][1])
        q.months.extend(fy[min(a, b): max(a, b) + 1])
    else:
        q.months.extend(m for _, m in found)
    q.months = list(dict.fromkeys(q.months))

    # PO numbers ---------------------------------------------------------------
    po_keys = {e.key: e for e in vocab.entities.values() if e.type == "po"}
    if po_keys:
        for j, w in enumerate(words):
            if used[j]:
                continue
            if w in po_keys:
                q.entities.append(po_keys[w])
                used[j] = True
                continue
            m = _PO_NO.fullmatch(w)
            if m and (j > 0 and words[j - 1] in {"po", "fpo", "pos"} or w.startswith("fpo")):
                hits = [e for k, e in po_keys.items() if re.search(rf"\D{m.group(1)}$", k)]
                if len(hits) == 1:
                    q.entities.append(hits[0])
                    used[j] = True

    # names: longest exact n-gram first, then distinctive first words, then fuzzy ---------
    maxn = max((len(k.split(" ")) for k in vocab.by_key), default=1)
    for n in range(min(maxn, 5), 0, -1):
        for j in range(0, len(words) - n + 1):
            if any(used[j:j + n]):
                continue
            key = name_key(" ".join(words[j:j + n]))
            ents = [e for e in vocab.by_key.get(key, []) if e.type != "po"]
            if key == "top":             # the category "TOP" collides with "top" (= highest); only "tops" names it
                ents = []
            if key == "tops":
                ents = vocab.by_key.get("top", [])
            if ents:
                q.entities.extend(ents[:1] if len({e.type for e in ents}) == 1 else ents)
                for k in range(j, j + n):
                    used[k] = True
    for j, w in enumerate(words):
        if used[j] or w in vocab.common or len(w) < 4:
            continue
        ents = vocab.by_first.get(w)
        if ents and len({(e.type, e.key) for e in ents}) == 1:
            q.entities.append(ents[0])
            used[j] = True
            continue
        best, score = None, 0.0
        for key, ents in vocab.by_key.items():
            if " " in key or ents[0].type == "po" or abs(len(key) - len(w)) > 2 or key[0] != w[0]:
                continue
            s = similar(w, key)
            if s > score:
                best, score = ents[0], s
        if best and score >= 0.84:
            q.entities.append(best)
            used[j] = True
    seen = set()
    q.entities = [e for e in q.entities if not ((e.type, e.key) in seen or seen.add((e.type, e.key)))]

    rest = " ".join(w for j, w in enumerate(words) if not used[j])
    q.toks = tokens(rest)
    q.dims = list(dict.fromkeys(DIMENSION_WORDS[x] for x in q.toks if x in DIMENSION_WORDS))
    m = re.search(r"\b(?:top|bottom|best|worst|highest|lowest)\s*(\d{1,2}|three|five|ten)\b", t) or \
        re.search(r"\b(\d{1,2})\s*(?:top|best|highest|lowest|worst)\b", t)
    if m:
        q.n = {"three": 3, "five": 5, "ten": 10}.get(m.group(1)) or int(m.group(1))
        q.n = max(1, min(q.n, 20))
        q.toks = [x for x in q.toks if x != m.group(1)]

    for page in PAGES.values():
        if any(re.search(rf"\b{re.escape(w)}\b", t) for w in page.words):
            q.pages.append(page.key)
    if re.search(r"\bsamples?\b", t) and "samples" not in q.pages:
        q.pages.append("samples")
    if re.search(r"\b(target|revenue|sales)\b", t) and "target" not in q.pages:
        q.pages.append("target")
    if (re.search(r"\bfabric\b", t) and re.search(r"\b(po|pos|purchase|ordered|order)\b", t) or
            re.search(r"\b(po|pos|fpo|purchase orders?)\b", t)) and "fabric-po" not in q.pages:
        q.pages.append("fabric-po")
    # "fabric pending / received / ordered" is the Fabric PO sheet; fabric *issued* to fabricators is not
    if re.search(r"\b(fabric|kapda|cloth)\b", t) and not re.search(r"\b(issue|issued|fabricators?|karigar|stock)\b", t) \
            and "fabric-po" not in q.pages:
        q.pages.append("fabric-po")

    # intent --------------------------------------------------------------------
    same_type = {}
    for e in q.entities:
        same_type.setdefault(e.type, []).append(e)
    if any(e.type == "po" for e in q.entities):
        q.intent = "record"
    elif _COMPARE.search(t) and (any(len(v) >= 2 for v in same_type.values()) or len(q.months) >= 2):
        q.intent = "compare"
    elif any(len(v) >= 2 for v in same_type.values() if v[0].type != "month"):
        q.intent = "compare"
    elif _EXPLAIN.search(t):
        q.intent = "explain"
    elif _WHERE.search(t) and q.metric_toks:
        q.intent = "where"
    elif TREND in q.toks and "require" not in q.toks:
        q.intent = "trend"
    elif re.search(r"\b(designer|vendor|client|party|customer|fabricator|category|item|product)s?[- ]?wise\b|"
                   r"\b(by|per|har) (designer|vendor|client|party|customer|fabricator|category|item|product)s?\b",
                   t) and q.dims:
        q.intent = "rank"
        q.n = max(q.n, 10)
    elif _EACH.search(t) and q.dims and q.dims[0] != "po" and q.metric_toks and not q.entities:
        q.intent = "rank"
        q.n = max(q.n, 10)
    elif q.markers & {TOP, BOTTOM}:
        q.intent = "rank"
    elif q.dims and q.dims[0] != "po" and not q.metric_toks and not q.entities and not q.months and (
            _LIST.search(t) or HOWMANY in q.toks):
        q.intent = "count" if HOWMANY in q.toks and not _LIST.search(t) else "list"
    elif q.dims and re.search(r"\b(which|kaun|kon|konsa|kaunsa|who)\b", t) and q.dims[0] not in {
            e.type for e in q.entities}:
        q.intent = "rank"
    # "best vendor" / "worst fabricator" with no measure: rank by on-time rate, not by size
    if q.intent == "rank" and q.dims and q.dims[0] in QUALITY and not q.metric_toks and _QUALITY.search(t):
        q.toks += tokens(QUALITY[q.dims[0]])
    return q


# ------------------------------------------------------------------------------------------------ scoring
def mscore(label: str, q: Query, unit: str = "", fmt_: str | None = None) -> float:
    lt = label_tokens(label)
    if not lt:
        return 0.0
    if unit:
        lt = lt | (label_tokens(unit) & {"po"})
    added = {"rate"} - lt if fmt_ == "pct" else set()   # "On-time delivery" is a rate even without the word
    lt = lt | added
    qt = set(q.toks)
    matched = lt & qt
    if not matched or not (matched - MARKERS):
        return 0.0
    specific = bool(q.metric_toks - CONTEXT_WORDS)

    def w(t):
        if t in MARKERS or t in DIMENSION_WORDS:
            return 0.6
        return 0.5 if (specific and t in CONTEXT_WORDS) else 1.0
    weight = sum(w(t) for t in matched)
    if not (matched - MARKERS - set(DIMENSION_WORDS)) and q.metric_toks:
        weight *= 0.5                          # only "top"/"designer" matched while a real metric was asked
    extra = [w for w in lt - matched - added if w not in SOFT]
    penalty = 0.2 * len(extra)
    # "New order qty" is only part of "total orders"; "(new)" in brackets is just a note, as in "Achieved (new)"
    if "new" in lt and "new" not in qt and not re.search(r"\(new", label, re.I):
        penalty += 0.3
    # "Total revenue (new + repeat)" is neither "new revenue" nor "repeat revenue" alone
    if re.search(r"\bnew\s*\+\s*repeat\b", label, re.I) and len({"new", "repeat"} & qt) == 1:
        penalty += 0.5
    return weight + 0.5 * len(matched) / len(lt - (added - matched)) - penalty


def col_unit(label: str, data: dict) -> tuple[str, str]:
    """A column's display label and unit; 'Pending' borrows 'pcs' from the page's own 'Pending' KPI."""
    label, unit = fmt.unit_of(label)
    if not unit:
        want = label_tokens(label)
        unit = next((k.get("unit") or "" for k in kpi_list(data)
                     if want and k.get("unit") and label_tokens(k["label"]) == want), "")
    return label, unit


@dataclass
class Candidate:
    score: float
    kind: str                # kpi | cell | rank | trend
    page: str
    label: str
    fmt: str | None = None
    unit: str = ""
    value: object = None
    row: str = ""
    hint: str = ""
    rows: list = field(default_factory=list)  # rank / trend: [(name, value)]
    entity: Entity | None = None
    payload: dict | None = None

    def text(self):
        return fmt.value(self.value, self.fmt, self.unit)


class Assistant:
    """Answers one question at a time. ``fetch(page, filters)`` returns that dashboard page's API payload."""

    def __init__(self, fetch: Fetch, today_month: Callable[[], str | None] = lambda: None, interpreter=None,
                 today: Callable[[], date] | None = None):
        self.fetch = fetch
        self.today_month = today_month
        self.today = today                      # today's date, for "this month is still running" notes
        self.interpreter = interpreter          # optional Gemini helper (see gemini.py)

    # -------------------------------------------------------------------------------------------- public
    def answer(self, question: str, context: dict | None = None) -> dict:
        question = (question or "").strip()[:MAX_QUESTION]
        if not question:
            return self._reply("Please type a question about the dashboard.", understood=False)
        snap = Snapshot(self.fetch)
        vocab = Vocabulary(snap)
        if len(vocab.errors) == len(PAGES):
            return self._reply("I can't read the dashboard data right now (" + next(iter(vocab.errors.values())) +
                               "). Please try again in a minute.", understood=False)

        t = norm(question)
        if _GREET.match(t):
            return self._reply("Hi! I'm FLO Assistant. " + HELP, intent="greet")
        if _THANKS.match(t) and len(t.split()) <= 4:
            return self._reply("You're welcome! Ask me anything else about the dashboard.", intent="thanks")

        if _SMALLTALK.search(t) and not _HELP.search(t):
            result = self._smalltalk(question)
            if result:
                return self._polish(question, result, "normal")

        q = parse(question, vocab, self.today_month())
        self._ctx_in = context if isinstance(context, dict) else None
        self._inherit(q, context, vocab)
        if _DEVANAGARI.search(question):
            if self.interpreter is None:
                return self._reply("Please write your question in English or Hinglish (Hindi in English letters), "
                                   "for example: \"is mahine ki sales kitni hai\".", understood=False, intent="unknown")
            result = None                        # the rules read Roman letters only; Gemini reads this one
        else:
            result = self._solve(q, snap, vocab)
        if self.interpreter is not None and (result is None or self._shaky(q, result)):
            catalog = self._catalog(vocab)
            if isinstance(context, dict) and context.get("metric"):
                catalog["previous"] = str(context["metric"])[:80]
            hint = self.interpreter.interpret(question, catalog)
            if hint:
                chat = self._chat_reply(hint, result)
                if chat is not None:
                    return chat
                q2 = self._from_hint(hint, question, vocab)
                if q2 is not None:
                    q2.style = q.style
                    self._inherit(q2, context, vocab)
                    again = self._solve(q2, snap, vocab)
                    if again is not None and (result is None or self._better(q, again, result)):
                        result = again
                        result["engine"] = "gemini"
        if result is None:
            result = self._not_understood(q, snap, vocab)
        return self._polish(question, result, q.style)

    # -------------------------------------------------------------------------------------------- Gemini helpers
    @staticmethod
    def _label(result: dict) -> str:
        return str((result.get("context") or {}).get("metric") or "")

    @staticmethod
    def _unexplained(q: Query, label: str) -> set:
        """Words of the question that the figure named ``label`` does not account for."""
        explained = label_tokens(label) | CONTEXT_WORDS | SOFT | HARMLESS | {"avg", "number", "po"}
        return {t for t in q.metric_toks if t not in explained and len(t) > 2}

    def _shaky(self, q: Query, result: dict) -> bool:
        """The rules answered, but part of the question matched nothing in that answer: let Gemini double-check."""
        label = self._label(result)
        return bool(label and result.get("intent") in ("value", "rank", "trend") and self._unexplained(q, label))

    def _better(self, q: Query, again: dict, result: dict) -> bool:
        """Gemini's reading replaces the rules' answer only if it is a different figure that explains at least as
        much of the question as the rules' own answer did."""
        a, b = self._label(again), self._label(result)
        return bool(a) and a != b and len(self._unexplained(q, a)) <= len(self._unexplained(q, b))

    def _chat_reply(self, hint: dict, result):
        """Small talk or a question that is not about the dashboard: Gemini's short reply (it never holds figures)."""
        reply = str(hint.get("reply") or "").strip()
        if hint.get("intent") in ("chat", "unknown") and reply and result is None:
            return self._reply(reply[:400], understood=hint.get("intent") == "chat", intent="chat", engine="gemini")
        return None

    def _smalltalk(self, question: str):
        hing = bool(re.search(r"\b(kaise|kaisa|kaisi|haal|kya chal|bhai|yaar)\b", norm(question)))
        text = ("Main badhiya hoon, shukriya! Dashboard ke numbers ke baare mein kuch bhi poochiye."
                if hing else "I'm doing well, thanks for asking! Ask me anything about the dashboard's numbers.")
        return self._reply(text, intent="chat")

    def _polish(self, question: str, result: dict, style: str) -> dict:
        """Gemini rewrites the finished answer as a natural reply in the person's own language. The figures in it
        are checked against the original, and the plain answer is kept if anything differs."""
        phrase = getattr(self.interpreter, "phrase", None)
        if (phrase is None or not getattr(self.interpreter, "phrasing", False) or style == "terse"
                or result.get("intent") not in PHRASE_INTENTS or not result.get("answer")):
            return result
        better = phrase(question, result["answer"], language_of(question))
        if better:
            result = {**result, "answer": better, "phrased": True}
        return result

    # -------------------------------------------------------------------------------------------- pieces
    @staticmethod
    def _reply(answer, page=None, context=None, understood=True, intent="", engine="rules"):
        p = PAGES.get(page) if page else None
        return {"answer": answer, "page": p.path if p else None, "page_label": p.label if p else None,
                "context": context or {}, "understood": understood, "intent": intent, "engine": engine}

    def _inherit(self, q: Query, ctx: dict | None, vocab: Vocabulary):
        """Follow-up questions ("and for May?", "what about Rekha?") reuse the previous question's subject."""
        if not ctx or not isinstance(ctx, dict):
            return
        t = norm(q.text)
        follow = bool(_FOLLOW.search(t)) or len(q.toks) <= 1
        if not q.metric_toks and ctx.get("metric") and (q.entities or q.months or follow) and q.intent in (
                "value", "compare", "rank", "trend"):
            q.toks = q.toks + list(label_tokens(str(ctx["metric"])))
            if ctx.get("page") in PAGES and ctx["page"] not in q.pages:
                q.pages.append(ctx["page"])
            if q.intent == "value" and ctx.get("intent") in ("rank", "trend") and not q.entities and not q.months:
                q.intent = ctx["intent"]
                q.dims = q.dims or ([ctx["dim"]] if ctx.get("dim") else [])
            q.inherited = True
        if (follow or _PRONOUN.search(t)) and q.metric_toks:
            if not q.entities:
                for ref in ctx.get("entities") or []:
                    e = vocab.entities.get((ref.get("type"), name_key(str(ref.get("value", "")))))
                    if e:
                        q.entities.append(e)
            if not q.months and _PRONOUN.search(t):
                q.months = [m for m in ctx.get("months") or [] if m in vocab.months]

    def _filters(self, page: str, q: Query, skip_type: str | None = None) -> dict | None:
        """API filters for this page, or None if a named thing can't be applied there."""
        p = PAGES[page]
        f: dict[str, list] = {}
        if q.months:
            if "month" not in p.filters:
                return None
            f["month"] = list(q.months)
        for e in q.entities:
            if e.type in ("month", skip_type, "po"):
                continue
            param = next((k for k, v in p.filters.items() if v == e.type), None)
            if not param or page not in e.raw:
                return None
            f.setdefault(param, []).append(e.raw[page])
        return f

    def _page_bonus(self, page: str, q: Query) -> float:
        return (0.5 if page in q.pages else 0.0) - 0.01 * PAGES[page].order - (0.3 if page == "overview" else 0.0)

    def _candidates(self, q: Query, snap: Snapshot) -> list[Candidate]:
        out: list[Candidate] = []
        named_types = {e.type for e in q.entities}
        rank_dim = q.dims[0] if q.intent == "rank" and q.dims else None
        for page in PAGES:
            bonus = self._page_bonus(page, q)
            # KPIs: only when every name in the question can be applied as a filter on this page
            f = self._filters(page, q)
            if f is not None and q.intent in ("value", "explain", "where", "rank") and not rank_dim:
                try:
                    data = snap.get(page, f)
                except DataUnavailable:
                    data = None
                if data:
                    for k in kpi_list(data):
                        s = mscore(k["label"], q, k.get("unit") or "", k.get("format"))
                        if s <= 0:
                            continue
                        if q.intent == "rank" and not (label_tokens(k["label"]) & {TOP, BOTTOM}):
                            s -= 0.5
                        out.append(Candidate(s + bonus + 0.1, "kpi", page, k["label"], k.get("format"),
                                             k.get("unit") or "", k.get("value"), hint=_hint(k.get("hint")),
                                             payload=data))
            # tables
            for etype in ({e.type for e in q.entities if e.type not in ("month", "po")} | {rank_dim, "month"}):
                if not etype:
                    continue
                tf = self._filters(page, q, skip_type=etype)
                if tf is None and etype != "month":
                    continue
                month_cell = etype == "month" and len(q.months) == 1 and q.intent in ("value", "explain")                     and not rank_dim
                if etype == "month":
                    if q.intent not in ("trend",) and not (rank_dim == "month") and not month_cell:
                        continue
                    tf = self._filters(page, replace(q, months=[]))
                    if tf is None:
                        continue
                try:
                    data = snap.get(page, tf)
                except DataUnavailable:
                    continue
                for tname, table in table_list(data):
                    if row_type(table) != etype:
                        continue
                    cols = table["columns"]
                    key_col = table.get("key_col")
                    for ci, c in enumerate(cols[1:], start=1):
                        s = mscore(c["label"], q, fmt_=c.get("format"))
                        if s <= 0 and not q.metric_toks and c["key"] == key_col:
                            s = 0.5 + (0.3 if HOME_PAGE.get(etype) == page else 0.0)
                        if s <= 0:
                            continue
                        label, unit = col_unit(c["label"], data)
                        if month_cell:
                            r = next((r for r in table["rows"] if r and r[0] == q.months[0]), None)
                            if r is not None and isinstance(r[ci], (int, float)) and not isinstance(r[ci], bool):
                                out.append(Candidate(s + bonus + 0.05, "mcell", page, label, c.get("format"), unit,
                                                     r[ci], row=str(r[0]), payload=data))
                            continue
                        if etype == rank_dim or (etype == "month" and q.intent == "trend"):
                            rows = [(r[0], r[ci]) for r in table["rows"]
                                    if r and isinstance(r[ci], (int, float)) and not SPECIAL_ROW.match(str(r[0]))]
                            if rows:
                                kind = "trend" if etype == "month" and q.intent == "trend" else "rank"
                                out.append(Candidate(s + bonus + 0.6, kind, page, label, c.get("format"), unit,
                                                     rows=rows, row=etype, payload=data))
                        elif etype in named_types:
                            for e in q.entities:
                                if e.type != etype:
                                    continue
                                r = next((r for r in table["rows"] if r and name_key(str(r[0])) == e.key), None)
                                if r is not None and r[ci] is not None:
                                    out.append(Candidate(s + bonus + 0.4, "cell", page, label, c.get("format"),
                                                         unit, r[ci], row=str(r[0]), entity=e, payload=data))
        out.sort(key=lambda c: -c.score)
        return out

    def _solve(self, q: Query, snap: Snapshot, vocab: Vocabulary) -> dict | None:
        if q.intent == "record":
            return self._record(q, snap)
        res = self._orders(q, snap, vocab)
        if res:
            return res
        if q.intent in ("list", "count"):
            return self._list(q, vocab)
        res = self._calc(q, snap, vocab)
        if res:
            return res
        if q.intent == "compare" and len(set(q.months)) >= 2 and not self._entity_groups(q, 2):
            res = self._calc_period(q, calc.Spec("diff"), snap, vocab)       # two months: show the change
            if res:
                return res
        if q.intent == "compare":
            res = self._compare(q, snap)
            if res:
                return res
            q.intent = "value"
        if q.intent == "value" and _COMPARE.search(norm(q.text)):
            res = self._compare_metrics(q, snap, vocab)
            if res:
                return res
        if q.intent == "explain" and not q.metric_toks:
            page = next(iter(q.pages), None)
            if page:
                return self._page_about(page, snap)
        features = self._feature(q)
        if features and (_HOWTO.search(norm(q.text)) or not q.metric_toks):
            return self._reply(features, intent="help")
        if q.pages and not q.entities and re.search(
                r"\b(what|show|shows|dikhata|dikhati|about|kya|contain|contains|explain|tell)\b", norm(q.text)):
            page = q.pages[0]
            page_words = {w for phrase in PAGES[page].words for w in tokens(phrase)} | {"page", "tab", "dashboard",
                                                                                         "screen", "section"}
            if not (q.metric_toks - page_words) and (re.search(r"\b(page|tab|dashboard|screen|section)\b",
                                                                norm(q.text)) or not q.metric_toks):
                return self._page_about(page, snap)
        if _HELP.search(norm(q.text)) and not q.metric_toks:
            return self._reply(HELP, intent="help")

        cands = self._candidates(q, snap)
        if q.intent in ("rank", "trend") and not any(c.kind in ("rank", "trend") and c.score >= THRESHOLD
                                                     for c in cands):
            q.intent = "value"
            cands = self._candidates(q, snap)
        if not cands or cands[0].score < THRESHOLD:
            return None
        best = cands[0]
        if q.intent == "where":
            p = PAGES[best.page]
            return self._reply(f"**{best.label}** is on the **{p.label}** page.", best.page,
                               self._ctx(q, best), intent="where")
        if q.intent == "explain":
            what = best.hint or self._describe(best)
            return self._reply(f"**{best.label}**: {what} Right now it is **{best.text()}**.", best.page,
                               self._ctx(q, best), intent="explain")
        if best.kind in ("rank",):
            return self._rank(q, best)
        if best.kind == "trend":
            return self._trend(q, best)
        return self._value(q, best, cands)

    # -------------------------------------------------------------------------------------------- answers
    def _ctx(self, q: Query, c: Candidate | None, intent: str | None = None) -> dict:
        return {"page": c.page if c else None, "metric": c.label if c else None, "intent": intent or q.intent,
                "entities": [e.ref() for e in q.entities if e.type != "po"], "months": q.months,
                "dim": c.row if c and c.kind in ("rank", "trend") else None}

    def _value(self, q: Query, best: Candidate, cands: list[Candidate]) -> dict:
        val = best.text()
        if q.style == "terse":
            return self._reply(f"**{val}**", best.page, self._ctx(q, best), intent="value")
        elsewhere = any(c.label == best.label and c.page != best.page and c.text() != val for c in cands[:8])
        if best.kind == "cell":
            scope = q.scope(skip_type=best.entity.type if best.entity else None)
            who = best.row
            sentence = f"{best.label} for **{who}**{(' ' + scope) if scope else ''} is **{val}**."
        else:
            scope = q.scope()
            sentence = f"{best.label}{(' ' + scope) if scope else ''} is **{val}**."
        if not q.months and best.kind == "kpi" and not best.label.lower().startswith(("top", "most")):
            sentence = sentence[:-1] + " (all months so far)."
        if elsewhere and best.page not in q.pages:
            sentence = sentence[:-1] + f" (from the {PAGES[best.page].label} page)."
        lines = [sentence]
        same = label_tokens(best.label) & set(q.toks)
        for alt in cands[1:4]:
            if alt.score >= best.score - 0.15 and alt.kind in ("kpi", "cell", "mcell") and alt.text() != val and \
                    alt.label != best.label and label_tokens(alt.label) & set(q.toks) == same and \
                    not (label_tokens(alt.label) - set(q.toks) - SOFT):
                lines.append(f"Also, {alt.label} is **{alt.text()}** ({PAGES[alt.page].label} page).")
                break
        if q.style == "detail":
            if best.hint:
                lines.append(best.hint)
            lines.extend(self._breakdown(best, q))
        return self._reply("\n".join(lines), best.page, self._ctx(q, best), intent="value")

    def _breakdown(self, c: Candidate, q: Query) -> list[str]:
        """For "in detail": the same figure split by designer / vendor / fabricator / category / month."""
        if not c.payload or c.kind == "mcell":
            return []
        best = None
        lt = label_tokens(c.label) - SOFT
        for _, t in table_list(c.payload):
            rt = row_type(t)
            if rt in (None, "po") or (c.entity and rt == c.entity.type):
                continue
            for ci, col in enumerate(t["columns"][1:], start=1):
                ov = len(label_tokens(col["label"]) & lt)
                if ov and (best is None or ov > best[0] or (ov == best[0] and rt != "month" and best[3] == "month")):
                    best = (ov, t, ci, rt)
        if not best:
            return []
        _, t, ci, rt = best
        col = t["columns"][ci]
        label, unit = fmt.unit_of(col["label"])
        rows = [(r[0], r[ci]) for r in t["rows"]
                if isinstance(r[ci], (int, float)) and r[ci] and not SPECIAL_ROW.match(str(r[0]))]
        unit = unit or (c.unit if col.get("format") == c.fmt else "")
        if rt != "month":
            rows.sort(key=lambda x: -x[1])
        if not rows:
            return []
        out = [f"By {TYPE_NAMES.get(rt, rt)} ({label}):"]
        out += [f"• {name}: {fmt.value(v, col.get('format'), unit)}" for name, v in rows[:8]]
        if len(rows) > 8:
            out.append(f"• … and {len(rows) - 8} more on the {PAGES[c.page].label} page.")
        return out

    def _rank(self, q: Query, c: Candidate) -> dict:
        low = BOTTOM in q.markers
        rows = sorted(c.rows, key=lambda x: x[1], reverse=not low)
        if c.row == "month":
            rows = [r for r in rows if r[1] is not None]
        if not rows:
            return None
        n = q.n if q.n > 1 else (5 if q.style == "detail" else 1)
        what = TYPE_NAMES.get(c.row, c.row)
        scope = q.scope()
        word = "lowest" if low else "highest"
        name, v = rows[0]
        tied = [nm for nm, val in rows if val == v]
        if n == 1 and len(tied) > 1 and q.style != "terse":
            names = ", ".join(f"**{x}**" for x in tied[:8]) + (f" and {len(tied) - 8} more" if len(tied) > 8 else "")
            text = (f"{len(tied)} {PLURALS.get(what, what + 's')} share the {word} {c.label}"
                    f"{(' ' + scope) if scope else ''} (**{fmt.value(v, c.fmt, c.unit)}**): {names}.")
        elif q.style == "terse":
            text = f"**{name}**"
        elif n == 1:
            text = (f"**{name}** is the {what} with the {word} {c.label}{(' ' + scope) if scope else ''}: "
                    f"**{fmt.value(v, c.fmt, c.unit)}**.")
        else:
            head = f"{'Bottom' if low else 'Top'} {min(n, len(rows))} {PLURALS.get(what, what + 's')} by {c.label}" + (f" {scope}" if scope else "") + ":"
            text = "\n".join([head] + [f"{i}. **{nm}**: {fmt.value(val, c.fmt, c.unit)}"
                                       for i, (nm, val) in enumerate(rows[:n], 1)])
        return self._reply(text, c.page, self._ctx(q, c, "rank"), intent="rank")

    def _trend(self, q: Query, c: Candidate) -> dict:
        rows = list(c.rows)
        while rows and not rows[-1][1]:
            rows.pop()
        if not rows:
            return None
        scope = q.scope()
        head = f"{c.label} month by month{(' ' + scope) if scope else ''}:"
        lines = [head] + [f"• {m}: **{fmt.value(v, c.fmt, c.unit)}**" for m, v in rows]
        if len({v for _, v in rows}) == 1:
            v = fmt.value(rows[0][1], c.fmt, c.unit)
            span = rows[0][0] if len(rows) == 1 else f"{rows[0][0]} to {rows[-1][0]}"
            lines = [f"**{v}**"] if q.style == "terse" else [
                f"{c.label}{(' ' + scope) if scope else ''} is **{v}** every month ({span})."]
        elif q.style == "terse":
            lines = [", ".join(f"{m}: {fmt.value(v, c.fmt, c.unit)}" for m, v in rows)]
        else:
            peak = max(rows, key=lambda x: x[1])
            lines.append(f"Highest: **{peak[0]}** ({fmt.value(peak[1], c.fmt, c.unit)}).")
        return self._reply("\n".join(lines), c.page, self._ctx(q, c, "trend"), intent="trend")

    def _compare(self, q: Query, snap: Snapshot) -> dict | None:
        groups: dict[str, list] = {}
        for e in q.entities:
            groups.setdefault(e.type, []).append(e)
        if len(q.months) >= 2 and not any(len(v) >= 2 for v in groups.values()):
            items = [("month", m) for m in q.months]
        else:
            etype, ents = max(groups.items(), key=lambda kv: len(kv[1]))
            if len(ents) < 2:
                return None
            items = [(etype, e) for e in ents]
        results = []
        first = None
        for etype, item in items:
            sub = replace(q, entities=list(q.entities), months=list(q.months), pages=list(q.pages))
            sub.intent = "value"
            if etype == "month":
                sub.months = [item]
                name = item
            else:
                sub.entities = [e for e in q.entities if e.type != etype] + [item]
                name = item.display
            if first is not None:
                sub.pages = list(dict.fromkeys([first.page] + sub.pages))
            cands = [c for c in self._candidates(sub, snap) if c.kind in ("kpi", "cell", "mcell")]
            if first is not None:
                cands = [c for c in cands if c.label == first.label and c.page == first.page] or cands
            if not cands or cands[0].score < THRESHOLD:
                return None
            c = cands[0]
            first = first or c
            results.append((name, c))
        lines = [f"{first.label}" + (f" in {fmt.months(q.months)}" if q.months and items[0][0] != "month" else "")
                 + ":"]
        lines += [f"• {name}: **{c.text()}**" for name, c in results]
        nums = [(name, c.value) for name, c in results if isinstance(c.value, (int, float))]
        if len(nums) == 2 and nums[0][1] != nums[1][1]:
            hi, lo = sorted(nums, key=lambda x: -x[1])
            more = fmt.more_pct(hi[1], lo[1]) if first.fmt != "pct" else ""
            lines.append(f"**{hi[0]}** is higher by **{fmt.diff(hi[1], lo[1], first.fmt, first.unit)}**"
                         + (f" ({more} than {lo[0]})." if more else "."))
        elif len(nums) > 2:
            hi = max(nums, key=lambda x: x[1])
            lines.append(f"Highest: **{hi[0]}**.")
        if q.style == "terse":
            lines = [" · ".join(f"{name}: {c.text()}" for name, c in results)]
        return self._reply("\n".join(lines), first.page, self._ctx(q, first, "compare"), intent="compare")

    def _compare_metrics(self, q: Query, snap: Snapshot, vocab: Vocabulary) -> dict | None:
        """Two measures side by side: "new vs repeat revenue" -> New revenue and Repeat revenue."""
        t = _TERSE.sub(" ", _DETAIL.sub(" ", norm(q.text)))
        t = re.sub(r"^\s*(compare|comparison( of)?|difference( between)?|between)\s+", "", t)
        parts = [p.split() for p in re.split(r"\b(?:vs\.?|versus|and|aur|or|compared to|against|with)\b", t)]
        parts = [p for p in parts if p]
        if len(parts) != 2:
            return None
        left, right = parts
        if len(left) == 1 and len(right) > 1:          # "new vs repeat revenue": the shared word is at the end
            left = left + right[1:]
        elif len(right) == 1 and len(left) > 1:        # "revenue new vs repeat": the shared word is at the start
            right = left[:-1] + right
        results = []
        for words in (left, right):
            sub = parse(" ".join(words), vocab, self.today_month())
            sub.entities, sub.months, sub.intent = list(q.entities), list(q.months), "value"
            sub.pages = list(dict.fromkeys(q.pages + sub.pages))
            cands = [c for c in self._candidates(sub, snap) if c.kind in ("kpi", "cell", "mcell")]
            if not sub.metric_toks or not cands or cands[0].score < THRESHOLD:
                return None
            results.append(cands[0])
        a, b = results
        if a.label == b.label or (a.fmt == "pct") != (b.fmt == "pct") or (a.unit != b.unit and a.fmt != "inr"):
            return None
        scope = q.scope()
        if q.style == "terse":
            text = f"{a.label}: **{a.text()}** · {b.label}: **{b.text()}**"
        else:
            lines = [f"{a.label} vs {b.label}{(' ' + scope) if scope else ''}:",
                     f"• {a.label}: **{a.text()}**", f"• {b.label}: **{b.text()}**"]
            if isinstance(a.value, (int, float)) and isinstance(b.value, (int, float)) and a.value != b.value:
                hi, lo = (a, b) if a.value > b.value else (b, a)
                more = fmt.more_pct(hi.value, lo.value) if hi.fmt != "pct" else ""
                lines.append(f"**{hi.label}** is higher by **{fmt.diff(hi.value, lo.value, hi.fmt, hi.unit)}**"
                             + (f" ({more} than {lo.label})." if more else "."))
            text = "\n".join(lines)
        ctx = self._ctx(q, a, "compare")
        return self._reply(text, a.page, ctx, intent="compare")

    # -------------------------------------------------------------------------------------------- calculations
    @staticmethod
    def _entity_groups(q: Query, at_least: int) -> bool:
        counts: dict[str, int] = {}
        for e in q.entities:
            if e.type not in ("month", "po"):
                counts[e.type] = counts.get(e.type, 0) + 1
        return any(v >= at_least for v in counts.values())

    @staticmethod
    def _numeric(*cands) -> bool:
        return all(c is not None and isinstance(c.value, (int, float)) and not isinstance(c.value, bool)
                   for c in cands)

    def _orders(self, q: Query, snap: Snapshot, vocab: Vocabulary) -> dict | None:
        """Orders per customer (designer): counts, new vs repeat, rankings, comparisons and month-to-month change."""
        analyst = OrderAnalyst(snap.get, self._running_note, self.today_month)
        try:
            spec = analyst.parse(q, self._ctx_in, vocab)
            out = analyst.answer(spec, q.text) if spec else None
        except (DataUnavailable, KeyError, ZeroDivisionError):
            return None
        if out is None:
            return None
        text, ctx = out
        return self._reply(text, "designer", ctx, intent="orders")

    def _calc(self, q: Query, snap: Snapshot, vocab: Vocabulary) -> dict | None:
        """Growth, difference, sums, averages, shares and plain arithmetic. The figures still come from the
        dashboard; only the arithmetic is done here."""
        spec = calc.detect(q.text)
        if spec is None:
            return None
        handlers = {"arithmetic": self._calc_arith, "n_of": self._calc_n_of, "share": self._calc_share,
                    "metric_op": self._calc_metric_op, "growth": self._calc_period, "diff": self._calc_period,
                    "sum": self._calc_sum, "average": self._calc_average}
        try:
            return handlers[spec.kind](q, spec, snap, vocab)
        except ZeroDivisionError:
            return self._reply("That would mean dividing by zero, which isn't possible.", intent="calc")

    def _calc_arith(self, q: Query, spec, snap, vocab):
        try:
            value = calc.evaluate(spec.expr)
        except ZeroDivisionError:
            raise
        except (ValueError, SyntaxError, OverflowError):
            return None
        text = f"**{calc.num(value)}**" if q.style == "terse" else f"{spec.disp} = **{calc.num(value)}**"
        return self._reply(text, intent="calc")

    def _phrase_value(self, q: Query, phrase: str, snap: Snapshot, vocab: Vocabulary, like: Candidate | None = None):
        """The dashboard figure a phrase like "pending pcs" or "total revenue" points at, with the question's months
        and names applied."""
        sub = parse(phrase, vocab, self.today_month())
        have = {(e.type, e.key) for e in sub.entities}
        sub.entities = sub.entities + [e for e in q.entities if (e.type, e.key) not in have]
        sub.months = list(q.months) or sub.months
        sub.intent = "value"
        sub.pages = list(dict.fromkeys(([like.page] if like else []) + sub.pages + q.pages))
        if not sub.metric_toks:
            return None
        cands = [c for c in self._candidates(sub, snap) if c.kind in ("kpi", "cell", "mcell")]
        if not cands or cands[0].score < THRESHOLD or not self._numeric(cands[0]):
            return None
        return cands[0]

    def _calc_n_of(self, q: Query, spec, snap, vocab):
        b = self._phrase_value(q, spec.b, snap, vocab)
        if b is None:
            return None
        value = b.value * spec.n / 100
        out = fmt.value(value, b.fmt, b.unit)
        if q.style == "terse":
            return self._reply(f"**{out}**", b.page, self._ctx(q, b, "calc"), intent="calc")
        return self._reply(f"{calc.num(spec.n)}% of **{b.label}**{self._in(q)} (**{b.text()}**) is **{out}**.",
                           b.page, self._ctx(q, b, "calc"), intent="calc")

    def _in(self, q: Query) -> str:
        scope = q.scope()
        return f" {scope}" if scope else ""

    def _calc_share(self, q: Query, spec, snap, vocab):
        a = self._phrase_value(q, spec.a, snap, vocab)
        b = self._phrase_value(q, spec.b, snap, vocab, like=a)
        if a is None or b is None or a.label == b.label:
            return None
        if a.fmt == "pct" or b.fmt == "pct" or (a.unit != b.unit and "inr" not in (a.fmt, b.fmt)):
            return None
        if b.value == 0:
            return self._reply(f"**{b.label}** is 0{self._in(q)}, so a share of it can't be calculated.",
                               b.page, self._ctx(q, a, "calc"), intent="calc")
        share = a.value / b.value * 100
        if q.style == "terse":
            return self._reply(f"**{fmt.value(share, 'pct')}**", a.page, self._ctx(q, a, "calc"), intent="calc")
        return self._reply(f"**{a.label}** is **{fmt.value(share, 'pct')}** of **{b.label}**{self._in(q)}: "
                           f"{a.text()} out of {b.text()}.", a.page, self._ctx(q, a, "calc"), intent="calc")

    def _calc_metric_op(self, q: Query, spec, snap, vocab):
        a = self._phrase_value(q, spec.a, snap, vocab)
        if a is None:
            return None
        n, v = spec.n, a.value
        words = {"/": f"divided by {calc.num(n)}", "*": f"multiplied by {calc.num(n)}",
                 "+": f"plus {fmt.value(n, a.fmt, a.unit) if a.fmt == 'inr' else calc.num(n)}",
                 "-": f"minus {fmt.value(n, a.fmt, a.unit) if a.fmt == 'inr' else calc.num(n)}",
                 "pct+": f"increased by {calc.num(n)}%", "pct-": f"reduced by {calc.num(n)}%"}[spec.op]
        result = {"/": v / n if n else None, "*": v * n, "+": v + n, "-": v - n,
                  "pct+": v * (1 + n / 100), "pct-": v * (1 - n / 100)}[spec.op]
        if result is None:
            raise ZeroDivisionError
        out = fmt.value(result, a.fmt, a.unit)
        if q.style == "terse":
            return self._reply(f"**{out}**", a.page, self._ctx(q, a, "calc"), intent="calc")
        return self._reply(f"**{a.label}**{self._in(q)} is **{a.text()}**; {words} that is **{out}**.", a.page,
                           self._ctx(q, a, "calc"), intent="calc")

    def _running_note(self, month: str) -> str:
        """A warning when a month being compared has not finished yet."""
        if self.today is None:
            return ""
        d = self.today()
        if month != f"{d.strftime('%B')}-{d.year % 100:02d}":
            return ""
        last = calendar.monthrange(d.year, d.month)[1]
        if d.day >= last:
            return ""
        return f"Note: {month} is still running (day {d.day} of {last}), so this is not a full-month comparison."

    def _month_value(self, q: Query, snap: Snapshot, month: str, like: Candidate | None = None):
        sub = replace(q, entities=list(q.entities), months=[month], pages=list(q.pages), intent="value")
        if like is not None:
            sub.pages = list(dict.fromkeys([like.page] + sub.pages))
        cands = [c for c in self._candidates(sub, snap) if c.kind in ("kpi", "cell", "mcell")]
        if like is not None:
            cands = [c for c in cands if c.label == like.label and c.page == like.page]
        if not cands or cands[0].score < THRESHOLD or not self._numeric(cands[0]):
            return None
        return cands[0]

    def _calc_period(self, q: Query, spec, snap, vocab):
        """Change between two months: the difference and the percentage growth. Defaults to last month -> this month."""
        fy = vocab.months
        months = sorted(set(q.months), key=fy.index)
        if self._entity_groups(q, 2) or (q.dims and not q.entities):
            return None
        if spec.kind == "diff" and not months:
            return None
        today_m = self.today_month()
        if len(months) >= 2:
            base_m, cur_m = months[0], months[-1]
        else:
            cur_m = months[0] if months else (today_m if today_m in fy else None)
            i = fy.index(cur_m) if cur_m in fy else 0
            base_m = fy[i - 1] if cur_m and i > 0 else None
        if cur_m is None:
            return None
        if base_m is None:
            return self._reply(f"{cur_m} is the first month of the year, so there is no earlier month to compare with.",
                               intent="calc")
        qq = replace(q, toks=list(q.toks) + ([] if q.metric_toks else ["revenue"]))
        cur = self._month_value(qq, snap, cur_m)
        base = self._month_value(qq, snap, base_m, like=cur) if cur else None
        if cur is None or base is None:
            return None
        delta = cur.value - base.value
        pct = fmt.pct_change(base.value, cur.value) if cur.fmt != "pct" else None
        names = [e.display for e in q.entities if e.type not in ("month", "po")]
        scope = f" for {' and '.join(names)}" if names else ""
        if q.style == "terse":
            out = fmt.pct_text(pct) if pct is not None and spec.kind == "growth" else fmt.diff(
                cur.value, base.value, cur.fmt, cur.unit)
            sign = "+" if delta > 0 else "-" if delta < 0 else ""
            return self._reply(f"**{sign}{out}**", cur.page, self._ctx(replace(q, months=[base_m, cur_m]), cur, "calc"),
                               intent="calc")
        head = (f"**{cur.label}**{scope} is **{cur.text()}** in **{cur_m}**, against **{base.text()}** in "
                f"**{base_m}**.")
        if delta == 0:
            tail = " There is no change."
        else:
            word = "higher" if delta > 0 else "lower"
            amount = fmt.diff(cur.value, base.value, cur.fmt, cur.unit)
            if pct is not None:
                tail = (f" That is **{amount} {word}**, a **{fmt.pct_text(pct)} {'growth' if delta > 0 else 'decline'}**"
                        f" compared with {base_m}.")
            elif cur.fmt == "pct":
                tail = f" That is **{amount} {word}**."
            else:
                tail = f" That is **{amount} {word}**; {base_m} was 0, so a percentage can't be worked out."
        note = self._running_note(cur_m)
        text = head + tail + (f"\n{note}" if note else "")
        return self._reply(text, cur.page, self._ctx(replace(q, months=[base_m, cur_m]), cur, "calc"), intent="calc")

    def _each(self, q: Query, snap: Snapshot, items):
        """The same figure for each named thing: [(type, Entity), ...] -> (first candidate, [(name, candidate)])."""
        results, first = [], None
        for etype, item in items:
            sub = replace(q, entities=list(q.entities), months=list(q.months), pages=list(q.pages), intent="value")
            sub.entities = [e for e in q.entities if e.type != etype] + [item]
            if first is not None:
                sub.pages = list(dict.fromkeys([first.page] + sub.pages))
            cands = [c for c in self._candidates(sub, snap) if c.kind in ("kpi", "cell", "mcell")]
            if first is not None:
                cands = [c for c in cands if c.label == first.label and c.page == first.page] or cands
            if not cands or cands[0].score < THRESHOLD or not self._numeric(cands[0]):
                return None
            first = first or cands[0]
            results.append((item.display, cands[0]))
        return first, results

    def _calc_sum(self, q: Query, spec, snap, vocab):
        """Several named designers / clients / vendors added together ("Rekha aur Anamika ki revenue milake")."""
        groups: dict[str, list] = {}
        for e in q.entities:
            if e.type not in ("month", "po"):
                groups.setdefault(e.type, []).append(e)
        if not groups:
            return None
        etype, ents = max(groups.items(), key=lambda kv: len(kv[1]))
        if len(ents) < 2:
            return None
        got = self._each(q, snap, [(etype, e) for e in ents])
        if got is None:
            return None
        first, results = got
        if first.fmt in ("pct", "dec1") or first.unit == "days":
            return self._reply(f"**{first.label}** is a rate or an average, so adding the values together would not "
                               f"mean anything.", first.page, self._ctx(q, first, "calc"), intent="calc")
        total = sum(c.value for _, c in results)
        out = fmt.value(total, first.fmt, first.unit)
        if q.style == "terse":
            return self._reply(f"**{out}**", first.page, self._ctx(q, first, "calc"), intent="calc")
        parts = " + ".join(f"{name} {c.text()}" for name, c in results)
        return self._reply(f"**{first.label}**{self._in(q)}, added together: {parts} = **{out}**.", first.page,
                           self._ctx(q, first, "calc"), intent="calc")

    def _calc_average(self, q: Query, spec, snap, vocab):
        """Average per month (completed months) or per designer / vendor / client / fabricator / category."""
        t = norm(q.text)
        per_month = bool(re.search(r"\b(monthly|per month|each month|every month|har mahine|mahine ka|month wise|"
                                   r"monthwise|month)\b", t))
        if not per_month and not q.dims:
            return None
        sub = replace(q, toks=[x for x in q.toks if x not in ("avg",)], intent="trend" if per_month else "rank",
                      entities=list(q.entities), months=[], pages=list(q.pages))
        cands = [c for c in self._candidates(sub, snap) if c.kind in ("trend", "rank")]
        if per_month:
            cands = [c for c in cands if c.row == "month"]
        if not cands or cands[0].score < THRESHOLD:
            return None
        c = cands[0]
        if c.fmt in ("pct", "dec1") or c.unit == "days":
            return None
        if per_month:
            fy = vocab.months
            today_m = self.today_month()
            upto = fy.index(today_m) if today_m in fy else len(fy) - 1
            rows = [(m, v) for m, v in c.rows if m in fy and fy.index(m) <= upto and isinstance(v, (int, float))]
            if not rows:
                return None
            running = bool(self._running_note(rows[-1][0])) and len(rows) > 1
            done = rows[:-1] if running else rows
            avg = sum(v for _, v in done) / len(done)
            out = fmt.value(avg, c.fmt, c.unit)
            if q.style == "terse":
                return self._reply(f"**{out}**", c.page, self._ctx(q, c, "calc"), intent="calc")
            text = (f"Average monthly **{c.label}** over the {len(done)} completed month{'s' if len(done) != 1 else ''}"
                    f" ({done[0][0]} to {done[-1][0]}) is **{out}**.")
            if running:
                with_run = sum(v for _, v in rows) / len(rows)
                text += (f" Counting {rows[-1][0]} too, which is still running, the average is "
                         f"**{fmt.value(with_run, c.fmt, c.unit)}**.")
            return self._reply(text, c.page, self._ctx(q, c, "calc"), intent="calc")
        rows = [(n, v) for n, v in c.rows if isinstance(v, (int, float))]
        if not rows:
            return None
        avg = sum(v for _, v in rows) / len(rows)
        what = TYPE_NAMES.get(c.row, c.row)
        out = fmt.value(avg, c.fmt, c.unit)
        if q.style == "terse":
            return self._reply(f"**{out}**", c.page, self._ctx(q, c, "calc"), intent="calc")
        return self._reply(f"Average **{c.label}** per {what}, across {len(rows)} {PLURALS.get(what, what + 's')}, "
                           f"is **{out}**.", c.page, self._ctx(q, c, "calc"), intent="calc")

    def _record(self, q: Query, snap: Snapshot) -> dict | None:
        e = next(e for e in q.entities if e.type == "po")
        for page in e.raw:
            try:
                data = snap.get(page)
            except DataUnavailable as err:
                return self._reply(f"I can't read the {PAGES[page].label} data right now ({err}).", page,
                                   understood=False)
            for _, t in table_list(data):
                if row_type(t) != "po":
                    continue
                r = next((r for r in t["rows"] if r and name_key(str(r[0])) == e.key), None)
                if r is None or len(t["columns"]) < 6:
                    continue
                parts = []
                for col, v in zip(t["columns"][1:], r[1:]):
                    if v in (None, ""):
                        continue
                    label, unit = fmt.unit_of(col["label"])
                    parts.append(f"• {label}: **{fmt.value(v, col.get('format'), unit)}**")
                timing = next((v for col, v in zip(t["columns"], r) if norm(col["label"]) in ("timing", "status")), "")
                if q.style == "terse":
                    return self._reply(f"**{timing or r[0]}**", page, {"page": page}, intent="record")
                return self._reply(f"**{r[0]}**\n" + "\n".join(parts), page, {"page": page}, intent="record")
        return None

    def _list(self, q: Query, vocab: Vocabulary) -> dict:
        dim = q.dims[0]
        if dim == "month":
            names = vocab.months
        else:
            names = sorted({e.display for e in vocab.of_type(dim)}, key=str.lower)
        what = TYPE_NAMES.get(dim, dim)
        if not names:
            return self._reply(f"I don't see any {PLURALS.get(what, what + 's')} on the dashboard right now.",
                               intent=q.intent)
        whats = PLURALS.get(what, what + "s")
        if q.intent == "count" or q.style == "terse":
            text = f"There are **{len(names)}** {whats} on the dashboard." if q.style != "terse" else f"**{len(names)}**"
            if q.style == "detail":
                text += "\n" + ", ".join(names)
        else:
            text = f"{len(names)} {whats}: " + ", ".join(names) + "."
        return self._reply(text, intent=q.intent, context={"intent": q.intent, "dim": dim})

    def _page_about(self, page: str, snap: Snapshot) -> dict:
        p = PAGES[page]
        lines = [f"The **{p.label}** page: {p.about}"]
        try:
            data = snap.get(page)
            ks = [k for k in kpi_list(data) if k.get("value") not in (None, "")][:6]
            if ks:
                lines.append("Headline numbers right now: " + "; ".join(
                    f"{k['label']} **{fmt.value(k['value'], k.get('format'), k.get('unit') or '')}**" for k in ks) + ".")
        except DataUnavailable:
            pass
        return self._reply("\n".join(lines), page, {"page": page}, intent="page")

    def _feature(self, q: Query) -> str | None:
        words = set(raw_tokens(q.text))
        for triggers, text in FEATURES:
            if words & triggers:
                return text
        return None

    @staticmethod
    def _describe(c: Candidate) -> str:
        return f"a figure on the {PAGES[c.page].label} page."

    def _not_understood(self, q: Query, snap: Snapshot, vocab: Vocabulary) -> dict:
        cands = [c for c in self._candidates(q, snap) if c.score > 0] if q.toks else []
        seen, sugg = set(), []
        for c in cands:
            key = (c.label, c.page)
            if key not in seen:
                seen.add(key)
                sugg.append(f"• {c.label} ({PAGES[c.page].label})")
            if len(sugg) == 3:
                break
        if vocab.errors:
            down = ", ".join(PAGES[p].label for p in vocab.errors)
            text = (f"I can't read some of the dashboard data right now ({down}), so I can't answer that yet. "
                    "Please try again in a minute.")
        elif sugg:
            text = "I'm not sure which number you mean. Did you mean one of these?\n" + "\n".join(sugg)
        else:
            text = ("Sorry, I couldn't match that to anything on the dashboard. " + HELP)
        return self._reply(text, understood=False, intent="unknown")

    # -------------------------------------------------------------------------------------------- Gemini hint
    def _catalog(self, vocab: Vocabulary) -> dict:
        return {"pages": {k: p.label for k, p in PAGES.items()}, "labels": sorted(vocab.labels),
                "dimensions": sorted(set(DIMENSION_WORDS.values())), "months": vocab.months}

    def _from_hint(self, hint: dict, question: str, vocab: Vocabulary) -> Query | None:
        """Turns the model's reading of the question back into words the rules understand, then re-parses."""
        intent = str(hint.get("intent") or "")
        metric = str(hint.get("metric") or "")       # an exact label, or a plain word ("sales") the rules can read
        bits = []
        if intent in ("top", "bottom"):
            bits.append("highest" if intent == "top" else "lowest")
            if hint.get("n"):
                bits.append(str(hint["n"]))
        if intent == "trend":
            bits.append("month wise")
        if intent == "where":
            bits.append("where is")
        if intent == "count":
            bits.append("how many")
        operation = str(hint.get("operation") or "")
        metric2 = str(hint.get("metric2") or "")
        number = hint.get("number")
        if operation == "growth":
            bits.append("growth percent")
            if not hint.get("months"):
                bits.append("this month vs last month")
        elif operation == "difference":
            bits.append("difference")
            if not hint.get("months"):
                bits.append("this month vs last month")
        elif operation == "sum":
            bits.append("added together")
        elif operation == "average":
            bits.append("average monthly")
        elif operation == "percent_of" and metric2:
            bits = [metric, "as percent of", metric2] + [str(x) for x in hint.get("months") or [] if isinstance(x, str)]
            metric = ""
        elif operation in ("divide", "multiply") and isinstance(number, (int, float)):
            bits = [metric, "divided by" if operation == "divide" else "multiplied by", str(number)]
            metric = ""
        if hint.get("dimension") in DIMENSION_WORDS.values():
            bits.append(str(hint["dimension"]))
        bits.append(metric)
        if operation not in ("percent_of", "divide", "multiply"):
            bits += [str(x) for x in hint.get("names") or [] if isinstance(x, str)][:4]
            bits += [str(x) for x in hint.get("months") or [] if isinstance(x, str)][:12]
        canonical = " ".join(b for b in bits if b)
        q = parse(canonical, vocab, self.today_month())
        if hint.get("page") in PAGES:
            q.pages = [hint["page"]]
        q.text = canonical if operation in ("growth", "difference", "sum", "average", "percent_of", "divide",
                                            "multiply") else question
        return q
