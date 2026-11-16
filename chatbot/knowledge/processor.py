"""Clean scraped text and split it into chunks for retrieval."""

import hashlib
import re
import unicodedata

from .models import Chunk

_BOILERPLATE = re.compile(
    r"^(home|menu|search|login|sign in|sign up|cart|my account|skip to content|accept( all)? cookies?|"
    r"subscribe|follow us|share|back to top|all rights reserved.*|©.*)$",
    re.IGNORECASE,
)


def clean_text(text):
    """Normalise unicode/whitespace and drop short navigation/boilerplate lines and duplicate lines."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text).replace(" ", " ")
    seen, lines = set(), []
    for raw in text.splitlines():
        line = re.sub(r"[ \t]+", " ", raw).strip()
        if not line or _BOILERPLATE.match(line):
            continue
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        lines.append(line)
    return "\n".join(lines)


def extract_faqs(text):
    """Pull "question? answer" pairs from cleaned text: a line ending with '?' followed by its answer lines."""
    faqs, question, answer = [], None, []
    for line in text.splitlines():
        if line.endswith("?") and len(line) <= 200:
            if question and answer:
                faqs.append({"question": question, "answer": " ".join(answer)})
            question, answer = line, []
        elif question is not None:
            answer.append(line)
    if question and answer:
        faqs.append({"question": question, "answer": " ".join(answer)})
    return faqs


def chunk_text(text, max_chars=1200, overlap=150):
    """Split on paragraph/sentence boundaries into chunks of at most ``max_chars``, with a small overlap."""
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    units = []
    for para in re.split(r"\n+", text):
        if len(para) <= max_chars:
            units.append(para)
        else:
            units.extend(s for s in re.split(r"(?<=[.!?])\s+", para) if s)
    chunks, current = [], ""
    for unit in units:
        while len(unit) > max_chars:                       # a single very long sentence
            chunks.append(unit[:max_chars])
            unit = unit[max_chars - overlap:]
        candidate = f"{current}\n{unit}" if current else unit
        if len(candidate) <= max_chars:
            current = candidate
        else:
            chunks.append(current)
            tail = current[-overlap:] if overlap else ""
            current = f"{tail}\n{unit}" if tail and len(tail) + len(unit) + 1 <= max_chars else unit
    if current:
        chunks.append(current)
    return chunks


def build_chunks(pages, max_chars=1200, overlap=150):
    """Turn scraped ``Page`` objects into ``Chunk`` objects (FAQs become their own chunks)."""
    out = []
    for page in pages:
        body = clean_text(page.text)
        pieces = chunk_text(body, max_chars=max_chars, overlap=overlap)
        for faq in page.faqs or extract_faqs(body):
            pieces.append(f"Q: {faq['question']}\nA: {faq['answer']}")
        for piece in pieces:
            cid = hashlib.sha1(f"{page.url}\n{piece}".encode()).hexdigest()[:16]
            out.append(Chunk(id=cid, text=piece, url=page.url, title=page.title, section=page.section))
    return out
