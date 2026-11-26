"""FLO Assistant replies in the language of the question: English in, English out; Hinglish in, Hinglish out. Without
Gemini the rules' own rewrite (app/assistant/hinglish.py) does the Hinglish, and it must never change a figure."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import main
from app.assistant import Assistant
from app.assistant.gemini import figures_match
from app.assistant.hinglish import to_hinglish
from app.config import Settings
from app.sources.demo import DemoSheetSource
from app.store import DataStore


@pytest.fixture()
def client(monkeypatch):
    settings = Settings(data_source="demo")
    store = DataStore(DemoSheetSource(), settings)
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    monkeypatch.setattr(main, "get_store", lambda: store)
    main.get_assistant.cache_clear()
    monkeypatch.setattr(main, "get_assistant",
                        lambda: Assistant(main._assistant_fetch, today_month=lambda: "November-26"))
    return TestClient(main.app)


def ask(client, message):
    r = client.post("/api/chat", json={"message": message})
    assert r.status_code == 200, r.text
    return r.json()


# Answer shapes the assistant really produces, and the Hinglish they should become.
CASES = [
    ("Total revenue in November-26 is **₹4.06 Cr**.", "November-26 mein Total revenue **₹4.06 Cr** hai."),
    ("Total Revenue for **REKHA** is **₹3.76 Cr**.", "**REKHA** ka Total Revenue **₹3.76 Cr** hai."),
    ("Total POs is **170 POs** (all months so far).", "Total POs **170 POs** hai (ab tak ke sabhi mahine)."),
    ("Pending is **184 pcs** (Nov 2026 promises).", "Pending **184 pcs** hai (Nov 2026 promises)."),
    ("**MAHI EXPORTS** is the fabricator with the highest Pending Pcs: **1,758 pcs**.",
     "Sabse zyada Pending Pcs **MAHI EXPORTS** (fabricator) ke paas hai: **1,758 pcs**."),
    ("Top 3 designers by Total Revenue:", "Total Revenue ke hisaab se top 3 designers:"),
    ("Total Revenue month by month:", "Total Revenue mahine-wise:"),
    ("Highest: **August-26** (₹5.19 Cr).", "Sabse zyada: **August-26** (₹5.19 Cr)."),
    ("**Delayed POs** is on the **Fabric PO** page.", "**Delayed POs** **Fabric PO** page par dikhega."),
    ("**Pending** is **8.3%** of **In production**: 6,858 pcs out of 83,060 pcs.",
     "**Pending**, **In production** ka **8.3%** hai: 83,060 pcs mein se 6,858 pcs."),
    ("**REKHA** is higher by **₹1.97 L** (0.5% more than CHARU).", "**REKHA** **₹1.97 L** se aage hai (CHARU se 0.5% zyada)."),
    ("**Total revenue** is **₹4.06 Cr** in **November-26**, against **₹4.87 Cr** in **October-26**. That is "
     "**₹80.75 L lower**, a **16.6% decline** compared with October-26.",
     "**Total revenue** **November-26** mein **₹4.06 Cr** hai, jabki **October-26** mein **₹4.87 Cr** tha. Yani "
     "**₹80.75 L kam**, October-26 ke mukable **16.6% giravat**."),
    ("Closing stock: **2,046 pcs** in 220 designs, worth **₹27.36 L**; average age 130 days.",
     "Closing stock: 220 designs mein **2,046 pcs**, value **₹27.36 L**; average umar 130 din."),
    ("Stock over 365 days old: **203 pcs**, **₹2.37 L** at cost (9.9% of pieces, 8.7% of value).",
     "365 din se purana stock: **203 pcs**, cost par **₹2.37 L** (9.9% pcs, 8.7% value)."),
    ("FLO has **122 repeat orders**, totalling **27,270 pcs**.", "FLO ke paas **122 repeat orders** hain, kul **27,270 pcs**."),
    ("Expected in December-26: **1,110 pcs** pending.", "December-26 mein **1,110 pcs** aane baaki hain."),
]


@pytest.mark.parametrize("english,hinglish", CASES)
def test_rewrite_shapes(english, hinglish):
    assert to_hinglish(english) == hinglish
    assert figures_match(english, hinglish)


def test_tables_and_unknown_lines_are_kept():
    text = "Something the rules have no pattern for.\n| Age | Pcs |\n|---|---|\n| 0-30 days | 545 |"
    assert to_hinglish(text) == text


@pytest.mark.parametrize("question", [
    "is mahine ki sales kitni hai", "total po kitne hai", "production pending kitna hai",
    "sabse zyada pending kis fabricator ke paas hai", "pichle mahine aur is mahine ki sales me kitna fark hai",
    "top 3 designer kaun hai revenue me", "delayed PO kahan dikhega", "kitna stock 1 saal se purana hai",
])
def test_hinglish_question_gets_hinglish_reply_with_the_same_figures(client, question):
    reply = ask(client, question)
    assert reply["understood"]
    assert reply.get("phrased") == "rules"
    text = reply["answer"]
    assert any(w in text.lower() for w in (" hai", " mein ", " ke ", " ka ", "dikhega", "sabse", "din"))


@pytest.mark.parametrize("question", ["total revenue this month", "total PO count", "which fabricator has the most pending pcs"])
def test_english_question_stays_english(client, question):
    reply = ask(client, question)
    assert reply["understood"] and not reply.get("phrased")
    assert " hai" not in reply["answer"] and " mein " not in reply["answer"]


def test_same_figures_in_english_and_hinglish(client):
    en = ask(client, "total revenue this month")["answer"]
    hi = ask(client, "is mahine ki sales kitni hai")["answer"]
    assert figures_match(en, hi)


def test_one_word_answers_are_not_rewritten(client):
    reply = ask(client, "total po kitne hai in one word")
    assert not reply.get("phrased")


def test_hindi_greeting_and_thanks_in_hinglish(client):
    assert ask(client, "namaste")["answer"].startswith("Namaste!")
    assert ask(client, "shukriya")["answer"].startswith("Aapka swagat hai")
    assert ask(client, "hello")["answer"].startswith("Hi!")


def test_gemini_phrasing_comes_first(client, monkeypatch):
    class Fake:
        phrasing = True

        def interpret(self, *a):
            return None

        def phrase(self, question, answer, language):
            assert language.startswith("Hinglish")
            return answer + " (gemini)"

    monkeypatch.setattr(main, "get_assistant",
                        lambda: Assistant(main._assistant_fetch, today_month=lambda: "November-26", interpreter=Fake()))
    reply = ask(client, "total po kitne hai")
    assert reply["phrased"] is True and reply["answer"].endswith("(gemini)")


def test_failed_gemini_falls_back_to_rules_hinglish(client, monkeypatch):
    class Down:
        phrasing = True

        def interpret(self, *a):
            return None

        def phrase(self, *a):
            return None                       # timeout, quota or a changed figure

    monkeypatch.setattr(main, "get_assistant",
                        lambda: Assistant(main._assistant_fetch, today_month=lambda: "November-26", interpreter=Down()))
    reply = ask(client, "total po kitne hai")
    assert reply["phrased"] == "rules" and " hai" in reply["answer"]
