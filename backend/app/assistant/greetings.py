"""Greetings and small talk: "good morning", "hello ji", "kaise ho", "who are you", "bye". No figures.

``reply`` answers only when the whole message is small talk. ``split`` takes a greeting off the front of a real question
("good morning, aaj ka pending kaam") so the question is still answered.
"""
from __future__ import annotations

import re

_ADDRESS = r"(?:\s+(?:sir|mam|ma'am|madam|ji|bhai|yaar|dear|team|everyone|all|flo|bot|assistant|there))*"
_HELLO = (r"(?:hi+|hey+|hello+|helo|hlo|hola|yo|namaste|namaskar|pranam|ram ram|jai shree krishna|salaam|adaab|"
          r"good\s*(?:morning|afternoon|evening|day)|gm|suprabhat|shubh prabhat)")
_HOW = (r"(?:how are (?:you|u)(?: doing)?|how r u|how do you do|how's it going|what's up|whats up|sup|"
        r"(?:aap |tum )?(?:kaise|kaisa|kaisi) (?:ho|hain|hai|hein)|kya haal(?: chaal)?(?: hai)?|kya chal raha(?: hai)?|"
        r"sab (?:theek|thik|badhiya)(?: hai)?)")
_WHO = (r"(?:who are you|what are you|what(?:'s| is) your name|(?:aap|tum|tu) kaun (?:ho|hain|hai)|"
        r"(?:aapka|tumhara|tera) naam(?: kya)?(?: hai)?|introduce yourself|apna intro (?:do|dijiye))")
_BYE = (r"(?:bye+(?: bye)?|goodbye|good\s*night|gn|see (?:you|ya)(?: later| soon| tomorrow)?|tata|alvida|"
        r"phir milte hain|chalo bye|shubh ratri)")
_PRAISE = (r"(?:(?:great|good|nice|awesome|excellent|superb) (?:job|work)|well done|bahut (?:accha|achha|badhiya)|"
           r"(?:very )?(?:good|helpful) (?:bot|assistant)|shabash|mast|badhiya|you(?:'re| are) (?:great|good|helpful))")
_END = r"[\s!.,?🙏👋🙂]*$"

WHOLE = {kind: re.compile(rf"^\s*(?:(?:{_HELLO}){_ADDRESS}[\s!.,]*)?(?:{body}){_ADDRESS}{_END}", re.I)
         for kind, body in (("how", _HOW), ("who", _WHO), ("bye", _BYE), ("praise", _PRAISE))}
HELLO = re.compile(rf"^\s*(?:{_HELLO}){_ADDRESS}{_END}", re.I)
LEADING = re.compile(rf"^\s*({_HELLO}){_ADDRESS}\s*[,!.:-]*\s+(?=\S)", re.I)
_HINDI = re.compile(r"\b(namaste|namaskar|pranam|ram ram|suprabhat|shubh|jai shree|salaam|adaab|ji|kaise|kaisa|kaisi|haal|"
                    r"aap\w*|tum\w*|naam|kaun|alvida|phir|chalo|bahut|accha|achha|badhiya|shabash|mast|bhai|yaar|theek|"
                    r"thik|chal)\b", re.I)

EXAMPLES_EN = "Try: \"oldest open task\", \"top 3 designers\" or \"which fabricator has the most pending\"."
EXAMPLES_HI = "Jaise: \"sabse purana open task\", \"top 3 designers\" ya \"sabse zyada pending kis fabricator ke paas hai\"."


def _salute(text: str, hindi: bool) -> str:
    m = re.search(r"good\s*(morning|afternoon|evening)|\bgm\b|suprabhat|shubh prabhat", text, re.I)
    if m and not hindi:
        return f"Good {(m.group(1) or 'morning').lower()}!"
    if re.search(r"suprabhat|shubh prabhat", text, re.I):
        return "Suprabhat!"
    return "Namaste!" if hindi else "Hi!"


def reply(text: str) -> tuple[str, str] | None:
    """(answer, intent) when the message is only a greeting or small talk."""
    hindi = bool(_HINDI.search(text))
    if HELLO.match(text):
        if hindi:
            return (f"{_salute(text, True)} Main FLO Assistant hoon. Daily Delegation, Designers, Production aur "
                    f"dashboard ke baaki pages ke baare mein poochiye. {EXAMPLES_HI}", "greet")
        return (f"{_salute(text, False)} I'm FLO Assistant. Ask me about Daily Delegation, Designers, Production or any "
                f"other page. {EXAMPLES_EN}", "greet")
    kind = next((k for k, p in WHOLE.items() if p.match(text)), None)
    if kind is None:
        return None
    opening = f"{_salute(text, hindi)} " if LEADING.match(text) else ""
    if kind == "how":
        return (opening + ("Main badhiya hoon, shukriya! Aaj dashboard se kya jaanna hai?" if hindi else
                           "I'm doing well, thanks for asking! What would you like to check on the dashboard today?"),
                "chat")
    if kind == "who":
        return (opening + (f"Main **FLO Assistant** hoon, FLO Operations dashboard ka sahayak. Main sirf dashboard ke "
                           f"figures padhta hoon, kuch badalta nahi. {EXAMPLES_HI}" if hindi else
                           f"I'm **FLO Assistant**, the helper for the FLO Operations dashboard. I read its figures and "
                           f"never change anything. {EXAMPLES_EN}"), "chat")
    if kind == "bye":
        return ("Alvida! Aapka din achha rahe." if hindi else "Goodbye! Have a good day.", "chat")
    return ("Shukriya! Aur kuch dekhna ho to bataiye." if hindi else
            "Thank you! Tell me if you want to check anything else.", "chat")


def split(text: str) -> tuple[str, str]:
    """("Good morning!", "aaj ka pending kaam") for a greeting followed by a question, else ("", text)."""
    m = LEADING.match(text)
    if not m or reply(text):
        return "", text
    return _salute(m.group(0), bool(_HINDI.search(m.group(0)))), text[m.end():]
