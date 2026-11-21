"""Question text handling: normalising English / Hinglish, tokens, months, fuzzy name matching."""
from __future__ import annotations

import re
from difflib import SequenceMatcher

# Intent markers. They are kept as tokens so labels such as "Top performer" can still match them.
TOP, BOTTOM, HOWMANY, TREND = "qqtop", "qqbottom", "qqhowmany", "qqtrend"
MARKERS = {TOP, BOTTOM, HOWMANY, TREND}

# Multi-word phrases first (longest first). Hinglish is mapped onto the same English words.
PHRASES = [
    ("purchase orders", "po"), ("purchase order", "po"), ("fabric po", "fabric po"),
    ("on time", "ontime"), ("on-time", "ontime"), ("job worker", "fabricator"), ("job workers", "fabricator"),
    ("sabse zyada", TOP), ("sabse jyada", TOP), ("sabse adhik", TOP), ("sab se zyada", TOP), ("sabse jada", TOP),
    ("sabse kam", BOTTOM), ("sab se kam", BOTTOM), ("sabse neeche", BOTTOM),
    ("how many", HOWMANY), ("how much", "howmuch"), ("number of", HOWMANY), ("count of", HOWMANY),
    ("month wise", TREND), ("monthwise", TREND), ("month-wise", TREND), ("by month", TREND), ("per month", TREND),
    ("har mahine", TREND), ("mahine wise", TREND), ("every month", TREND), ("each month", TREND),
    ("month by month", TREND),
    ("order by", "client"), ("ordered by", "client"),
    ("total orders", "order qty"), ("total order", "order qty"), ("order quantity", "order qty"),
    ("kitne order", "order qty"), ("kitna order", "order qty"),
    ("not updated", "notupdated"), ("update nahi", "notupdated"),
    ("due soon", "due"), ("next 7 days", "due"), ("next week", "due"), ("this week", "due"), ("is hafte", "due"),
    ("visits and meetings", "visit meeting"), ("visits & meetings", "visit meeting"),
    ("not planned", "unplanned"), ("plan nahi", "unplanned"),
]

# Single words -> canonical word.
WORDS = {
    # intent
    "top": TOP, "highest": TOP, "maximum": TOP, "max": TOP, "most": TOP, "best": TOP, "biggest": TOP,
    "largest": TOP, "leading": TOP, "zyada": TOP, "jyada": TOP,
    "lowest": BOTTOM, "minimum": BOTTOM, "min": BOTTOM, "least": BOTTOM, "worst": BOTTOM, "bottom": BOTTOM,
    "smallest": BOTTOM, "fewest": BOTTOM,
    "kitna": HOWMANY, "kitne": HOWMANY, "kitni": HOWMANY, "count": HOWMANY,
    "trend": TREND, "monthly": TREND,
    # metrics
    "pos": "po", "po's": "po", "fpo": "po",
    "pcs": "qty", "pc": "qty", "piece": "qty", "pieces": "qty", "qty": "qty", "quantity": "qty", "volume": "qty",
    "quantities": "qty",
    "rcvd": "received", "recieved": "received", "receive": "received", "receipt": "received", "aaya": "received",
    "aya": "received", "aaye": "received", "mila": "received",
    "baki": "pending", "baaki": "pending", "bacha": "pending", "outstanding": "pending",
    "mtr": "mtr", "meter": "mtr", "meters": "mtr", "metre": "mtr", "metres": "mtr", "mtrs": "mtr",
    "sales": "revenue", "sale": "revenue", "turnover": "revenue", "kamai": "revenue", "income": "revenue",
    "business": "revenue", "amount": "revenue",
    "late": "delay", "delayed": "delay", "delays": "delay", "der": "delay", "lateness": "delay",
    "overdue": "overdue",
    "percent": "rate", "percentage": "rate", "%": "rate", "ratio": "rate", "pct": "rate",
    "approved": "approv", "approval": "approv", "approve": "approv", "approvals": "approv", "pass": "approv",
    "rejected": "reject", "rejection": "reject", "rejects": "reject", "fail": "reject",
    "kapda": "fabric", "cloth": "fabric", "fabrics": "fabric",
    "goal": "target", "lakshya": "target",
    "achievement": "achieved", "achieve": "achieved",
    "left": "remaining",
    "issue": "issued",
    "supplier": "vendor", "suppliers": "vendor", "mill": "vendor", "mills": "vendor", "vendors": "vendor",
    "customer": "client", "customers": "client", "party": "client", "parties": "client", "buyer": "client",
    "buyers": "client", "clients": "client",
    "karigar": "fabricator", "fabricators": "fabricator", "stitcher": "fabricator",
    "item": "category", "items": "category", "product": "category", "products": "category", "categories": "category",
    "style": "category", "styles": "category",
    "designers": "designer", "employee": "designer", "employees": "designer", "staff": "designer",
    "mahina": "month", "mahine": "month", "months": "month",
    "samples": "sample", "sampling": "sample",
    "orders": "order", "designs": "design",
    "average": "avg", "avg": "avg", "mean": "avg",
    "required": "require", "needed": "require", "need": "require", "zaroorat": "require", "chahiye": "require",
    "chahie": "require", "chahiyen": "require",
    # FLO Future
    "promise": "promised", "promises": "promised", "commitment": "promised", "commitments": "promised",
    "committed": "promised", "vaada": "promised", "vada": "promised", "wada": "promised",
    "done": "completed", "complete": "completed", "finished": "completed", "ready": "completed",
    "completion": "completed", "pura": "completed", "poora": "completed",
    "outsourced": "outsource", "bahar": "outsource",
    "meetings": "meeting", "visits": "visit", "baithak": "meeting",
    "teams": "team",
}

# Words that mostly say which page a question is about. When a question also has a more specific word
# ("rejected samples"), these count less, so "Rejected" beats "Total samples".
CONTEXT_WORDS = {"sample", "po", "fabric", "target", "production", "order", "design"}

# Words that never carry meaning for matching (English + Hinglish fillers).
STOP = set("""
a an the of is are was were be been am what whats what's tell me show give please pls plz total overall all in for
on at to howmuch much many kya hai hain ka ki ke ko se mein me main batao bataiye bata dikhao do current currently
our we us number value figure this that so far till now abhi tak ab and or with did does has have get got which who
whose kaun konsa kaunsa kon sa wala wali wale ye yeh woh wo uska iska there any about i you can could would should
it its it's by from as us my your hamara hamare humara mujhe hume our pe par bhi just only sirf bas aur ji sir mam
madam hello hi hey thanks thank ok okay right now today data number list names name see
find check know dikhata dikhati dikhate dikha hota hoti hote hue hua hui raha rahe rahi gaya gaye gayi paas
kis kisne kisi liye wala tha thi the wise flo future
""".split())

GENERIC_NAME_WORDS = set("""
tex textile textiles mills mill exports export house studio label retail co and & fabrics fabric silks silk weaves
weave garments garment fab works work lab trends trend lane sampling kendra the pvt ltd private limited company
""".split())

MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
          "november", "december"]
MONTH_ALIASES = {m: i + 1 for i, m in enumerate(MONTHS)}
MONTH_ALIASES.update({m[:3]: i + 1 for i, m in enumerate(MONTHS)})
MONTH_ALIASES.update({"sept": 9, "jany": 1, "febuary": 2, "agust": 8, "octuber": 10, "novmber": 11})

_TOKEN = re.compile(r"[a-z0-9%]+(?:[/'.-][a-z0-9]+)*|₹")


def norm(text: str) -> str:
    """Lower case, unify quotes and spaces."""
    t = (text or "").lower().replace("’", "'").replace("‘", "'").replace("–", "-").replace("—", "-")
    t = re.sub(r"(?<=[a-z])'s\b", "", t)                       # possessive: "Kirti's" -> "Kirti"
    return re.sub(r"\s+", " ", t).strip()


def apply_phrases(text: str) -> str:
    t = f" {norm(text)} "
    for src, dst in sorted(PHRASES, key=lambda p: -len(p[0])):
        t = re.sub(rf"(?<![a-z0-9]){re.escape(src)}(?![a-z0-9])", f" {dst} ", t)
    return re.sub(r"\s+", " ", t).strip()


def raw_tokens(text: str) -> list[str]:
    return _TOKEN.findall(norm(text))


def stem(w: str) -> str:
    if w in MARKERS or len(w) <= 3 or not w.isalpha():
        return w
    for suf, rep in (("ies", "y"), ("ing", ""), ("ed", ""), ("es", ""), ("s", "")):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            if suf == "es" and not re.search(r"(ss|x|ch|sh)es$", w):
                continue
            return w[: len(w) - len(suf)] + rep
    return w


def canon(word: str) -> str:
    w = WORDS.get(word, word)
    return stem(w) if w not in MARKERS else w


def tokens(text: str, keep_stop: bool = False) -> list[str]:
    """Canonical tokens of a question or label."""
    out = []
    for w in raw_tokens(apply_phrases(text)):
        c = canon(w)
        if not keep_stop and c not in MARKERS and (c in STOP or w in STOP):
            continue
        out.append(c)
    return out


def label_tokens(label: str) -> set[str]:
    """Tokens of a dashboard label; '(Pcs)' style units count too, '%' becomes 'rate'."""
    t = label.replace("%", " percent ").replace("₹/pc", " rate ").replace("/", " ")
    return {w for w in tokens(t) if w not in {"total"}}


def similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def sound_key(s: str) -> str:
    """How a name sounds, so Indian spellings match: Kirti / Keerti / Keerthi, Pooja / Puja, Jyoti / Jyothi."""
    s = re.sub(r"[^a-z]", "", s.lower())
    for a, b in (("ee", "i"), ("oo", "u"), ("aa", "a"), ("th", "t"), ("dh", "d"), ("bh", "b"), ("kh", "k"),
                 ("w", "v"), ("ph", "f"), ("z", "j"), ("y", "i")):
        s = s.replace(a, b)
    s = re.sub(r"(.)\1+", r"\1", s)
    return s.rstrip("h")


def name_key(s: str) -> str:
    """Comparable form of a name: lower case, letters and digits only, single spaces."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9/& ]+", " ", norm(s))).strip()


_HINDI_WORDS = frozenset("""
kitna kitne kitni hai hain ka ki ke ko mein mahine mahina mahine batao bataiye bata dikhao dikha sabse zyada jyada
aur tak hua hue hui kya kaun konsa kaunsa abhi pichle pichla pichhle fark badhi badha badhe ghata ghati milake
milakar karo nahi paas wala wali liye maal kamai kapda yeh woh isme usme isse uska iska hamara humara chahiye
""".split())


def language_of(text: str) -> str:
    """'Hindi (Devanagari)', 'Hinglish (Hindi written in English letters)' or 'English'; used to pick the reply language."""
    if re.search(r"[\u0900-\u097f]", text or ""):
        return "Hindi in Devanagari script"
    words = set(raw_tokens(text))
    return "Hinglish (Hindi written in English letters)" if words & _HINDI_WORDS else "English"
