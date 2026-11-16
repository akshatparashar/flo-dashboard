"""Keyword retriever (BM25 ranking) over stored chunks. Pure Python - no extra dependencies.

Can be replaced by an embedding/vector retriever later: the service only needs ``search(query, k)``.
"""

import math
import re
from collections import Counter

_TOKEN = re.compile(r"[a-z0-9ऀ-ॿ]+")
_STOP = frozenset(
    "a an the and or of to in on for with is are was were be by at as it this that from what which who how "
    "do does can i you we our your me my kya hai ka ki ke ko se me mein aur".split()
)


def tokenize(text):
    return [t for t in _TOKEN.findall((text or "").lower()) if t not in _STOP and len(t) > 1]


class KeywordRetriever:
    def __init__(self, chunks, k1=1.5, b=0.75, min_score=0.5):
        self.chunks = list(chunks)
        self.k1, self.b, self.min_score = k1, b, min_score
        self._docs = [Counter(tokenize(f"{c.title}\n{c.text}")) for c in self.chunks]
        self._lens = [sum(d.values()) for d in self._docs]
        self._avg = (sum(self._lens) / len(self._lens)) if self._lens else 0.0
        df = Counter()
        for d in self._docs:
            df.update(d.keys())
        n = len(self._docs)
        self._idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def __len__(self):
        return len(self.chunks)

    def search(self, query, k=4):
        terms = set(tokenize(query))
        if not terms or not self.chunks:
            return []
        scored = []
        for i, doc in enumerate(self._docs):
            score = 0.0
            for t in terms:
                tf = doc.get(t)
                if not tf:
                    continue
                norm = self.k1 * (1 - self.b + self.b * self._lens[i] / (self._avg or 1))
                score += self._idf[t] * tf * (self.k1 + 1) / (tf + norm)
            if score >= self.min_score:
                scored.append((score, i))
        scored.sort(key=lambda x: (-x[0], x[1]))
        return [self.chunks[i] for _, i in scored[:k]]
