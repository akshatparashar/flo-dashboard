"""Gemini helper for FLO Assistant (optional; needs GEMINI_API_KEY).

It does three small jobs, each with a short prompt and a strict check on what comes back:

1. interpret(): reads a question the rules could not place (English, Hindi, Hinglish) and maps it onto the dashboard's
   own labels. It receives the question and the list of labels, never any figures. For small talk it also writes a
   short reply that contains no figures.
2. phrase(): rewrites a finished answer as a natural reply in the person's own language. This is the one step that
   sees figures (the answer text). Every number in the reply is checked against the original, and the original is
   kept if anything differs. Turn it off with ASSISTANT_GEMINI_PHRASING=off.
3. Without a key, or when a call fails or is slow, none of this runs and the rules' own answer is used.
"""
from __future__ import annotations

import json
import logging
import os
import re

import requests

log = logging.getLogger(__name__)

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_MODEL = "gemini-flash-lite-latest"     # Google's alias for the current small, low-cost Flash-Lite model

SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "intent": {"type": "STRING", "enum": ["value", "top", "bottom", "trend", "where", "count", "chat", "unknown"]},
        "operation": {"type": "STRING", "nullable": True,
                      "enum": ["none", "growth", "difference", "sum", "average", "percent_of", "divide", "multiply"]},
        "metric": {"type": "STRING", "nullable": True},
        "metric2": {"type": "STRING", "nullable": True},
        "number": {"type": "NUMBER", "nullable": True},
        "page": {"type": "STRING", "nullable": True},
        "dimension": {"type": "STRING", "nullable": True},
        "names": {"type": "ARRAY", "items": {"type": "STRING"}},
        "months": {"type": "ARRAY", "items": {"type": "STRING"}},
        "n": {"type": "INTEGER", "nullable": True},
        "reply": {"type": "STRING", "nullable": True},
    },
    "required": ["intent"],
}

PROMPT = """You help a chatbot read questions about a company operations dashboard. The question may be in English, Hindi (Devanagari) or Hinglish (Hindi in Roman letters), with spelling mistakes. Do not answer data questions; return JSON only.

- intent: value (one figure), top / bottom (highest / lowest by a dimension), trend (month by month), where (which page shows it), count (how many of a dimension), chat (greeting, thanks, small talk, who are you), unknown (not about this dashboard).
- operation: none, or growth (percentage increase / decrease between months), difference (how much more / less between months), sum (add several named things), average, percent_of (one metric as a percentage of another), divide / multiply (a metric by a number).
- metric: copy exactly one label from LABELS ("sales", "kamai", "business" mean a revenue label), or null.
- metric2: for percent_of, the second label from LABELS, else null.
- number: for divide / multiply, the number, else null.
- page: one key from PAGES, or null.
- dimension: one of DIMENSIONS when the question ranks or counts by it, else null.
- names: person / company / product names, written in Roman letters (transliterate from Devanagari, e.g. रेखा -> Rekha).
- months: month names mentioned, using MONTHS. For "this month" / "last month" leave months empty.
- n: how many items for top / bottom, else null.
- reply: only for intent chat or unknown. One or two short, friendly sentences in the same language and style as the question. Say what you can help with (numbers and pages of this dashboard). Never include any figure, name or company fact.

PAGES: {pages}
DIMENSIONS: {dimensions}
MONTHS: {months}
LABELS: {labels}
PREVIOUS QUESTION'S LABEL: {previous}

If the QUESTION is only a short follow-up (just a name, a month, "and for X?"), set intent value, operation none, metric to the PREVIOUS QUESTION'S LABEL, and fill names / months.

QUESTION: {question}"""

PHRASE_PROMPT = """You are FLO Assistant, the chatbot inside a company operations dashboard. Rewrite the ANSWER as a clear, fluent, friendly reply to the QUESTION.

Rules:
- Write the whole reply in this language: {language}. Do not mix in another language. Always write numbers with ordinary digits.
- Keep every number, name, unit (pcs, mtr, POs, Cr, L), month label and sign from the ANSWER exactly as written. Do not add, drop, round or recalculate any number.
- Translate every other word of the ANSWER (higher, lower, growth, decline, still running, "all months so far", ...) into the language of the reply, so the reply does not mix languages.
- Never add a fact. In particular, mention only the names, months and pages that appear in the ANSWER: if the QUESTION names a person, company or month that the ANSWER does not name, do not attribute the figure to it.
- Lead with what the person asked for. Be brief: one to three sentences, or a short list if the ANSWER is a list.
- Formatting: **bold** for the key figures. Lists use lines starting with "• " (or "1. ", "2. " for rankings). No headings, no code, no emojis.
- If the ANSWER ends with a note (for example that a month is still running), keep it, in the same language.
- Output only the reply.

The reply is always in English or Hinglish (Hindi in Roman letters), never in Devanagari script. Hinglish should read the way people in an Indian office type on WhatsApp: simple Hindi words, common English business words kept in English (pending, target, order, PO, revenue, sample, vendor, fabricator, stock).
Glossary for Hinglish replies: higher = zyada; lower = kam; growth = badhat; decline or decrease = giravat; still running = abhi chal raha hai; all months so far = ab tak ke sabhi mahine; not a full-month comparison = poore mahine ki tulna nahi hai; compared with = ke mukable; highest = sabse zyada; lowest = sabse kam; is on the X page = X page par dikhega.

Example (Hinglish):
ANSWER: **Total revenue** is **₹1.88 Cr** in **November-26**, against **₹3.86 Cr** in **October-26**. That is **₹1.99 Cr lower**, a **51.4% decline** compared with October-26.
Note: November-26 is still running (day 20 of 30), so this is not a full-month comparison.
REPLY: **November-26** mein **Total revenue** **₹1.88 Cr** hai, jabki **October-26** mein **₹3.86 Cr** tha. Yani **₹1.99 Cr kam**, ek **51.4% giravat** October-26 ke mukable.
Note: November-26 abhi chal raha hai (day 20 of 30), isliye yeh poore mahine ki tulna nahi hai.

QUESTION: {question}

ANSWER:
{answer}"""

_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


_MONTH_YEAR = re.compile(r"([^\W\d_]+)(?:-\d{2}|\s+20\d{2})\b")      # "November-26" / "November 2026" -> "November"


def _numbers(text: str) -> list[str]:
    text = _MONTH_YEAR.sub(r"\1", text)
    return sorted(n.replace(",", "").rstrip(".") for n in _NUM.findall(text))


def figures_match(original: str, rewritten: str) -> bool:
    """True when the rewrite holds exactly the same figures as the original answer, no more and no fewer."""
    return _numbers(original) == _numbers(rewritten)


class GeminiInterpreter:
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, timeout: float = 8.0, session=None,
                 phrasing: bool = True, phrase_timeout: float = 6.0):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.phrase_timeout = phrase_timeout
        self.phrasing = phrasing
        self.session = session or requests.Session()

    @classmethod
    def from_env(cls) -> "GeminiInterpreter | None":
        key = os.getenv("GEMINI_API_KEY", "").strip()
        off = ("off", "0", "false", "no")
        if not key or os.getenv("ASSISTANT_GEMINI", "on").strip().lower() in off:
            return None
        return cls(key, os.getenv("GEMINI_MODEL", "").strip() or DEFAULT_MODEL,
                   phrasing=os.getenv("ASSISTANT_GEMINI_PHRASING", "on").strip().lower() not in off)

    def _call(self, prompt: str, config: dict, timeout: float):
        body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": config}
        r = self.session.post(API.format(model=self.model), json=body, timeout=timeout,
                              headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"})
        if r.status_code != 200:
            log.warning("Gemini returned %s", r.status_code)
            return None
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]

    def interpret(self, question: str, catalog: dict) -> dict | None:
        prompt = PROMPT.format(pages=json.dumps(catalog["pages"]), dimensions=", ".join(catalog["dimensions"]),
                               months=", ".join(catalog["months"]), labels=json.dumps(catalog["labels"]),
                               previous=catalog.get("previous") or "none", question=question)
        try:
            text = self._call(prompt, {"temperature": 0, "maxOutputTokens": 320,
                                       "responseMimeType": "application/json", "responseSchema": SCHEMA},
                              self.timeout)
            hint = json.loads(text) if text else None
        except Exception as e:                       # network, quota, unexpected shape: the rules' answer stands
            log.warning("Gemini call failed: %s", type(e).__name__)
            return None
        if not isinstance(hint, dict) or not hint.get("intent"):
            return None
        return hint

    def phrase(self, question: str, answer: str, language: str = "English") -> str | None:
        """The answer in natural language, or None to keep the original (call failed, or a figure differs)."""
        if not self.phrasing or not answer:
            return None
        try:
            text = self._call(PHRASE_PROMPT.format(question=question, answer=answer, language=language),
                              {"temperature": 0.2, "maxOutputTokens": 600}, self.phrase_timeout)
        except Exception as e:
            log.warning("Gemini phrasing failed: %s", type(e).__name__)
            return None
        text = (text or "").strip()
        if not text or "```" in text or len(text) > 4 * len(answer) + 300:
            return None
        if not figures_match(answer, text):
            log.warning("Gemini phrasing changed a figure; kept the original answer")
            return None
        return text
