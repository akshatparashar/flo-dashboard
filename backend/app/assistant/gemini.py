"""Optional helper: a small Gemini model reads a question the rules could not place.

It only maps the question onto the dashboard's own labels and returns a small JSON object. It receives the question
and the list of labels/page names, never any figures, and it never writes the answer. Without GEMINI_API_KEY this
module does nothing and the assistant runs on rules alone.
"""
from __future__ import annotations

import json
import logging
import os

import requests

log = logging.getLogger(__name__)

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_MODEL = "gemini-flash-lite-latest"     # Google's alias for the current small, low-cost Flash-Lite model

SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "intent": {"type": "STRING", "enum": ["value", "top", "bottom", "trend", "where", "count", "unknown"]},
        "metric": {"type": "STRING", "nullable": True},
        "page": {"type": "STRING", "nullable": True},
        "dimension": {"type": "STRING", "nullable": True},
        "names": {"type": "ARRAY", "items": {"type": "STRING"}},
        "months": {"type": "ARRAY", "items": {"type": "STRING"}},
        "n": {"type": "INTEGER", "nullable": True},
    },
    "required": ["intent"],
}

PROMPT = """You map a user's question about an operations dashboard onto the dashboard's own labels.
The question may be in English or Hinglish. Do not answer it; return JSON only.

- intent: value (one figure), top / bottom (highest / lowest by a dimension), trend (month by month), where (which page shows it), count (how many of a dimension), unknown (not about this dashboard).
- metric: copy exactly one label from LABELS, or null.
- page: one key from PAGES, or null.
- dimension: one of DIMENSIONS when the question ranks or counts by it, else null.
- names: person / company / product names exactly as written in the question.
- months: month names mentioned (e.g. "April-26"), using MONTHS.
- n: how many items for top / bottom (default null).

PAGES: {pages}
DIMENSIONS: {dimensions}
MONTHS: {months}
LABELS: {labels}

QUESTION: {question}"""


class GeminiInterpreter:
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, timeout: float = 8.0, session=None):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.session = session or requests.Session()

    @classmethod
    def from_env(cls) -> "GeminiInterpreter | None":
        key = os.getenv("GEMINI_API_KEY", "").strip()
        if not key or os.getenv("ASSISTANT_GEMINI", "on").strip().lower() in ("off", "0", "false", "no"):
            return None
        return cls(key, os.getenv("GEMINI_MODEL", "").strip() or DEFAULT_MODEL)

    def interpret(self, question: str, catalog: dict) -> dict | None:
        prompt = PROMPT.format(pages=json.dumps(catalog["pages"]), dimensions=", ".join(catalog["dimensions"]),
                               months=", ".join(catalog["months"]), labels=json.dumps(catalog["labels"]),
                               question=question)
        body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0, "maxOutputTokens": 256,
                                     "responseMimeType": "application/json", "responseSchema": SCHEMA}}
        try:
            r = self.session.post(API.format(model=self.model), json=body, timeout=self.timeout,
                                  headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"})
            if r.status_code != 200:
                log.warning("Gemini returned %s", r.status_code)
                return None
            data = r.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            hint = json.loads(text)
        except Exception as e:                       # network, quota, unexpected shape: the rules' answer stands
            log.warning("Gemini call failed: %s", type(e).__name__)
            return None
        if not isinstance(hint, dict) or hint.get("intent") in (None, "unknown"):
            return None
        return hint
