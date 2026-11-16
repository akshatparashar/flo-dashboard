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

from . import fmt
from .pages import (DIMENSION_WORDS, FEATURES, HELP, HOME_PAGE, OPTION_TYPES, PAGES, PLURALS, ROW_TYPES,
                    TYPE_NAMES)
from .text import (BOTTOM, CONTEXT_WORDS, GENERIC_NAME_WORDS, HOWMANY, MARKERS, MONTH_ALIASES, STOP, TOP, TREND, WORDS,
                   label_tokens, name_key, norm, raw_tokens, similar, tokens)

Fetch = Callable[[str, dict], dict]

THRESHOLD = 1.0           # below this, the rules are not sure what was asked
SOFT = {"new", "yearly", "annual", "fy", "all", "sheet", "overall", "qty", "mtr", "day"}
SKIP_KEYS = {"meta", "options", "charts", "matrix", "heatmap", "lines", "top_repeat", "gauge", "schedule"}
SPECIAL_ROW = re.compile(r"^\(.*\)$|^(total|grand total)$", re.I)
MAX_QUESTION = 500


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
            w for lab in self.labels for w in raw_tokens(lab)} | {"page", "dashboard", "tab", "detail", "word"}

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
    elif TREND in q.toks:
        q.intent = "trend"
    elif re.search(r"\b(designer|vendor|client|party|customer|fabricator|category|item|product)s?[- ]?wise\b|"
                   r"\b(by|per|har) (designer|vendor|client|party|customer|fabricator|category|item|product)s?\b",
                   t) and q.dims:
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
    return q


# ------------------------------------------------------------------------------------------------ scoring
def mscore(label: str, q: Query, unit: str = "") -> float:
    lt = label_tokens(label)
    if not lt:
        return 0.0
    if unit:
        lt = lt | (label_tokens(unit) & {"po"})
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
    extra = [w for w in lt - matched if w not in SOFT]
    return weight + 0.5 * len(matched) / len(lt) - 0.2 * len(extra)


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

    def __init__(self, fetch: Fetch, today_month: Callable[[], str | None] = lambda: None, interpreter=None):
        self.fetch = fetch
        self.today_month = today_month
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

        q = parse(question, vocab, self.today_month())
        self._inherit(q, context, vocab)
        result = self._solve(q, snap, vocab)
        if result is None and self.interpreter is not None:
            hint = self.interpreter.interpret(question, self._catalog(vocab))
            if hint:
                q2 = self._from_hint(hint, question, vocab)
                if q2 is not None:
                    q2.style = q.style
                    result = self._solve(q2, snap, vocab)
                    if result is not None:
                        result["engine"] = "gemini"
        if result is not None:
            return result
        return self._not_understood(q, snap, vocab)

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
                        s = mscore(k["label"], q, k.get("unit") or "")
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
                if etype == "month":
                    if q.intent not in ("trend",) and not (rank_dim == "month"):
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
                        s = mscore(c["label"], q)
                        if s <= 0 and not q.metric_toks and c["key"] == key_col:
                            s = 0.5 + (0.3 if HOME_PAGE.get(etype) == page else 0.0)
                        if s <= 0:
                            continue
                        label, unit = fmt.unit_of(c["label"])
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
        if q.intent in ("list", "count"):
            return self._list(q, vocab)
        if q.intent == "compare":
            res = self._compare(q, snap)
            if res:
                return res
            q.intent = "value"
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
        if best.kind == "cell":
            scope = q.scope(skip_type=best.entity.type if best.entity else None)
            who = best.row
            sentence = f"{best.label} for **{who}**{(' ' + scope) if scope else ''} is **{val}**."
        else:
            scope = q.scope()
            sentence = f"{best.label}{(' ' + scope) if scope else ''} is **{val}**."
        if not q.months and best.kind == "kpi" and not best.label.lower().startswith(("top", "most")):
            sentence = sentence[:-1] + " (all months so far)."
        lines = [sentence]
        same = label_tokens(best.label) & set(q.toks)
        for alt in cands[1:4]:
            if alt.score >= best.score - 0.15 and alt.kind in ("kpi", "cell") and alt.text() != val and \
                    alt.label != best.label and label_tokens(alt.label) & set(q.toks) == same:
                lines.append(f"Also, {alt.label} is **{alt.text()}** ({PAGES[alt.page].label} page).")
                break
        if q.style == "detail":
            if best.hint:
                lines.append(best.hint)
            lines.extend(self._breakdown(best, q))
        return self._reply("\n".join(lines), best.page, self._ctx(q, best), intent="value")

    def _breakdown(self, c: Candidate, q: Query) -> list[str]:
        """For "in detail": the same figure split by designer / vendor / fabricator / category / month."""
        if not c.payload:
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
        if q.style == "terse":
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
        if q.style == "terse":
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
            cands = [c for c in self._candidates(sub, snap) if c.kind in ("kpi", "cell")]
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
            lines.append(f"**{hi[0]}** is higher by **{fmt.diff(hi[1], lo[1], first.fmt, first.unit)}**.")
        elif len(nums) > 2:
            hi = max(nums, key=lambda x: x[1])
            lines.append(f"Highest: **{hi[0]}**.")
        if q.style == "terse":
            lines = [" · ".join(f"{name}: {c.text()}" for name, c in results)]
        return self._reply("\n".join(lines), first.page, self._ctx(q, first, "compare"), intent="compare")

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
        metric = str(hint.get("metric") or "")
        if metric and metric not in vocab.labels:
            return None
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
        if hint.get("dimension") in DIMENSION_WORDS.values():
            bits.append(str(hint["dimension"]))
        bits.append(metric)
        bits += [str(x) for x in hint.get("names") or [] if isinstance(x, str)][:4]
        bits += [str(x) for x in hint.get("months") or [] if isinstance(x, str)][:12]
        q = parse(" ".join(b for b in bits if b), vocab, self.today_month())
        if hint.get("page") in PAGES:
            q.pages = [hint["page"]]
        q.text = question
        return q
