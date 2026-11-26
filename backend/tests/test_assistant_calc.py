"""FLO Assistant calculations: growth and difference between months, sums, averages, shares and plain maths, plus the
Gemini helper's language handling. Every expected figure is read from the dashboard's own API in the same test, so
these check that the maths matches what the pages show. Runs on the built-in demo data (today = 16 Nov 2026)."""
from __future__ import annotations

import re
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import main
from app.assistant import Assistant, calc, fmt
from app.assistant.gemini import GeminiInterpreter, figures_match
from app.config import Settings
from app.sources.demo import DemoSheetSource
from app.store import DataStore

TODAY = date(2026, 11, 16)


def make_assistant(**kw):
    return Assistant(main._assistant_fetch, today_month=lambda: "November-26", today=lambda: TODAY, **kw)


@pytest.fixture()
def client(monkeypatch):
    settings = Settings(data_source="demo")
    store = DataStore(DemoSheetSource(), settings)
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    monkeypatch.setattr(main, "get_store", lambda: store)
    monkeypatch.setattr(main, "get_assistant", lambda: make_assistant())
    return TestClient(main.app)


def ask(client, message, context=None):
    r = client.post("/api/chat", json={"message": message, "context": context})
    assert r.status_code == 200, r.text
    return r.json()


def target_kpi(client, label, **params):
    body = client.get("/api/target", params=params).json()
    return next(k["value"] for k in body["filtered"]["kpis"] if k["label"] == label)


def prod(client, label):
    return next(k["value"] for k in client.get("/api/production").json()["kpis"] if k["label"] == label)


def bold(answer):
    return re.findall(r"\*\*(.+?)\*\*", answer)


# ------------------------------------------------------------------------------------------------ growth / difference
GROWTH_QUESTIONS = [
    "sales growth percentage this month vs last month",
    "how many sales between last month and this month, give me difference",
    "pichle mahine aur is mahine ki sales me kitna fark hai",
    "percentage of how many sales growth in this month rather than last month",
    "is mahine sales kitne percent badhi",
    "october vs november revenue",
]


@pytest.mark.parametrize("question", GROWTH_QUESTIONS)
def test_month_change_matches_the_dashboard(client, question):
    cur = target_kpi(client, "Total revenue", month="November-26")
    base = target_kpi(client, "Total revenue", month="October-26")
    pct = (cur - base) / base * 100
    r = ask(client, question)
    assert r["intent"] == "calc" and r["page"] == "/target"
    text = r["answer"]
    assert fmt.value(cur, "inr") in text and fmt.value(base, "inr") in text
    assert fmt.pct_text(pct) in text
    assert fmt.diff(cur, base, "inr") in text
    if cur < base:      # English, or the Hinglish reply to a Hinglish question
        assert ("lower" in text and "decline" in text) or ("kam" in text and "giravat" in text)
    else:
        assert ("higher" in text and "growth" in text) or ("zyada" in text and "badhat" in text)
    assert "November-26" in text and "October-26" in text


def test_running_month_is_flagged_and_complete_month_is_not(client):
    r = ask(client, "sales growth this month vs last month")
    assert "still running (day 16 of 30)" in r["answer"]
    done = Assistant(main._assistant_fetch, today_month=lambda: "November-26", today=lambda: date(2026, 11, 30))
    assert "still running" not in done.answer("sales growth this month vs last month")["answer"]
    older = ask(client, "september vs october revenue")
    assert "still running" not in older["answer"]


def test_one_word_growth(client):
    cur = target_kpi(client, "Total revenue", month="November-26")
    base = target_kpi(client, "Total revenue", month="October-26")
    r = ask(client, "sales growth percentage this month vs last month in one word")
    sign = "-" if cur < base else "+"
    assert r["answer"] == f"**{sign}{fmt.pct_text((cur - base) / base * 100)}**"


def test_percentage_metrics_report_points_not_growth(client):
    r = ask(client, "approval rate last month vs this month")
    assert "points" in r["answer"] and "growth" not in r["answer"] and "decline" not in r["answer"]


def test_first_month_has_nothing_to_compare_with(client):
    r = ask(client, "april growth in sales")
    assert "first month" in r["answer"]


def test_entities_compare_with_percentage(client):
    a = target_kpi(client, "Total revenue", designer="ANAMIKA")
    b = target_kpi(client, "Total revenue", designer="REKHA")
    r = ask(client, "compare rekha vs anamika revenue")
    hi, lo = (a, b) if a > b else (b, a)
    assert fmt.diff(hi, lo, "inr") in r["answer"] and fmt.more_pct(hi, lo) in r["answer"]


def test_growth_for_one_designer(client):
    cur = target_kpi(client, "Total revenue", month="November-26", designer="REKHA")
    base = target_kpi(client, "Total revenue", month="October-26", designer="REKHA")
    r = ask(client, "rekha ki sales is mahine pichle mahine se kitni badhi")
    assert "REKHA" in r["answer"] and fmt.value(cur, "inr") in r["answer"] and fmt.value(base, "inr") in r["answer"]


# ------------------------------------------------------------------------------------------------ sums, shares, maths
def test_sum_of_two_designers(client):
    a = target_kpi(client, "Total revenue", designer="ANAMIKA")
    b = target_kpi(client, "Total revenue", designer="REKHA")
    r = ask(client, "rekha aur anamika ki total revenue milake kitni hai")
    assert fmt.value(a + b, "inr") in bold(r["answer"]) and "REKHA" in r["answer"] and "ANAMIKA" in r["answer"]


def test_a_rate_is_not_added(client):
    r = ask(client, "rekha and anamika approval rate added together")
    assert "would not mean anything" in r["answer"]


def test_share_of_another_figure(client):
    pending, produced = prod(client, "Pending"), prod(client, "In production")
    for q in ("pending pcs ka percentage kitna hai total production me", "what percent of in production is pending"):
        r = ask(client, q)
        assert fmt.value(pending / produced * 100, "pct") in bold(r["answer"]), q


def test_percent_of_and_division_of_a_figure(client):
    total = target_kpi(client, "Total revenue")
    assert fmt.value(total * 0.1, "inr") in bold(ask(client, "what is 10% of total revenue")["answer"])
    assert fmt.value(total / 12, "inr") in bold(ask(client, "total revenue divided by 12")["answer"])
    assert fmt.value(total * 2, "inr") in bold(ask(client, "double the total revenue")["answer"])
    assert fmt.value(total * 1.1, "inr") in bold(ask(client, "total revenue plus 10 percent")["answer"])


def test_plain_arithmetic(client):
    assert ask(client, "what is 12*5")["answer"] == "12 × 5 = **60**"
    assert "**300**" in ask(client, "15% of 2000")["answer"]
    assert "**30**" in ask(client, "(120 + 30) / 5")["answer"]
    assert "**1,024**" in ask(client, "2 ^ 10")["answer"]
    assert "**2.5**" in ask(client, "10 divided by 4")["answer"]
    assert "dividing by zero" in ask(client, "5 / 0")["answer"]


def test_arithmetic_cannot_run_code(client):
    for q in ("__import__('os').system('ls') + 1", "2 + 2; import os", "9**9**9", "1 + open('x')"):
        r = ask(client, q)
        assert r["intent"] != "calc" or "**" not in r["answer"], q


def test_average_monthly_uses_completed_months(client):
    rows = client.get("/api/target").json()["filtered"]["tables"]["monthly"]["rows"]
    col = 3                                                    # Total Revenue
    done = [r[col] for r in rows[:7]]                          # April-October are complete; November is running
    r = ask(client, "average monthly revenue")
    assert fmt.value(sum(done) / 7, "inr") in bold(r["answer"]) and "still running" in r["answer"]


# ------------------------------------------------------------------------------------------------ wording fixes
def test_po_count_this_month_is_not_received_pos(client):
    want = next(k["value"] for k in client.get("/api/fabric-po", params={"month": "November-26"}).json()["kpis"]
                if k["label"] == "Total POs")
    r = ask(client, "kitne PO is mahine aaye")
    assert f"{want} POs" in bold(r["answer"])


def test_money_needed_per_month_is_the_required_figure(client):
    want = next(k["value"] for k in client.get("/api/target").json()["tracker"]["kpis"]
                if k["label"] == "Required per month")
    r = ask(client, "how much more revenue needed per month")
    assert r["intent"] == "value" and fmt.value(want, "inr") in bold(r["answer"])


def test_small_talk_without_gemini(client):
    assert "doing well" in ask(client, "hello how are you")["answer"]
    assert "badhiya" in ask(client, "bhai kaise ho")["answer"]


def test_devanagari_needs_gemini_or_roman_letters(client):
    r = ask(client, "इस महीने की बिक्री पिछले महीने से कितनी बढ़ी")
    assert r["understood"] is False and "Hinglish" in r["answer"]


# ------------------------------------------------------------------------------------------------ calc helpers
@pytest.mark.parametrize("text,kind", [
    ("12*5", "arithmetic"), ("what is 15% of 2000", "arithmetic"), ("total revenue divided by 12", "metric_op"),
    ("10% of total revenue", "n_of"), ("pending pcs ka percentage kitna hai total production me", "share"),
    ("revenue ko 12 se divide karo", "metric_op"), ("sales kitne percent badhi", "growth"),
    ("pichle mahine ki sales me kitna fark hai", "diff"), ("rekha aur anamika milake", "sum"),
    ("average monthly revenue", "average"),
])
def test_detect(text, kind):
    assert calc.detect(text).kind == kind


@pytest.mark.parametrize("text", ["total PO count", "pending pcs", "target ka kitna percent achieve hua", "2026",
                                  "approval rate last month vs this month"])
def test_plain_questions_are_not_calculations(text):
    assert calc.detect(text) is None


def test_evaluate_is_safe_and_exact():
    assert calc.evaluate("(15/100)*2000") == 300 and calc.evaluate("2**10") == 1024
    with pytest.raises(ValueError):
        calc.evaluate("9**9**9")
    with pytest.raises(ValueError):
        calc.evaluate("__import__('os')")
    assert calc.num(1234.5) == "1,234.5" and calc.num(60.0) == "60"


# ------------------------------------------------------------------------------------------------ Gemini: language and phrasing
class Fake:
    """Stands in for GeminiInterpreter: returns a fixed reading of the question and a fixed rewrite."""

    def __init__(self, hint=None, rewrite=None):
        self.hint, self.rewrite, self.phrasing = hint, rewrite, rewrite is not None
        self.seen = []

    def interpret(self, question, catalog):
        self.seen.append(("interpret", question, catalog))
        return self.hint

    def phrase(self, question, answer, language="English"):
        self.seen.append(("phrase", question, answer, language))
        return self.rewrite(answer) if self.rewrite else None


def test_hindi_question_is_read_by_gemini_and_answered_by_the_rules(client):
    fake = Fake({"intent": "value", "operation": "growth", "metric": "sales", "months": []})
    r = make_assistant(interpreter=fake).answer("इस महीने की बिक्री पिछले महीने से कितनी बढ़ी")
    cur = target_kpi(client, "Total revenue", month="November-26")
    base = target_kpi(client, "Total revenue", month="October-26")
    assert r["engine"] == "gemini" and r["intent"] == "calc"
    assert fmt.value(cur, "inr") in r["answer"] and fmt.value(base, "inr") in r["answer"]
    sent = [x[2] for x in fake.seen if x[0] == "interpret"][0]
    assert not re.search(r"\d{4,}", re.sub(r"20\d\d-\d\d", "", str(sent)).replace("-26", "").replace("-27", ""))        # labels only, no figures


def test_follow_up_context_reaches_gemini(client):
    fake = Fake({"intent": "value", "metric": "Pending", "names": ["Rekha"]})
    a = make_assistant(interpreter=fake)
    first = a.answer("total pending pcs")
    r = a.answer("और रेखा का", first["context"])
    assert fake.seen[0][2]["previous"] == "Pending"
    assert fmt.value(prod_for(client, "REKHA"), "int", "pcs") in r["answer"]


def prod_for(client, designer):
    body = client.get("/api/production", params={"designer": designer}).json()
    return next(k["value"] for k in body["kpis"] if k["label"] == "Pending")


def test_phrasing_replaces_the_answer_only_with_the_same_figures(client):
    plain = make_assistant().answer("total po count")["answer"]
    n = re.search(r"\*\*([\d,]+) POs\*\*", plain).group(1)
    ok = make_assistant(interpreter=Fake(rewrite=lambda a: f"Total **{n} POs** hain abhi tak."))
    r = ok.answer("total po kitne hai")
    assert r["answer"].startswith("Total") and r["phrased"] is True
    assert r["answer"] == f"Total **{n} POs** hain abhi tak."


def test_one_word_answers_are_never_rephrased(client):
    fake = Fake(rewrite=lambda a: "x")
    assert make_assistant(interpreter=fake).answer("total po count in one word")["answer"].startswith("**")
    assert not [x for x in fake.seen if x[0] == "phrase"]


def test_chat_reply_from_gemini_only_when_rules_have_nothing(client):
    fake = Fake({"intent": "chat", "reply": "Hello! Ask me about the dashboard."})
    a = make_assistant(interpreter=fake)
    assert a.answer("who built you?")["answer"] == "Hello! Ask me about the dashboard."
    assert a.answer("total po count")["engine"] == "rules"


def test_the_reply_language_is_chosen_by_rules_not_guessed():
    from app.assistant.text import language_of
    assert language_of("total sales") == "English"
    assert language_of("is mahine ki sales kitni hai").startswith("Hinglish")
    assert language_of("इस महीने की बिक्री").startswith("Hinglish")     # English and Hinglish replies only
    seen = {}

    class Spy(Fake):
        def phrase(self, question, answer, language="English"):
            seen["language"] = language
            return None

    make_assistant(interpreter=Spy(rewrite=lambda a: a)).answer("rekha ka pending kitna hai")
    assert seen["language"].startswith("Hinglish")


def test_figures_match_ignores_month_wording_but_not_numbers():
    a = "**Total revenue** is **₹1.88 Cr** in **November-26**, against **₹3.86 Cr** in **October-26**."
    assert figures_match(a, "Nov 2026 ke liye **₹1.88 Cr**, October 2026 mein **₹3.86 Cr**.".replace("Nov ", "November "))
    assert figures_match(a, "November-26: **₹1.88 Cr**; October-26: **₹3.86 Cr**")
    assert not figures_match(a, "November-26: **₹1.89 Cr**; October-26: **₹3.86 Cr**")
    assert not figures_match(a, "It is **₹1.88 Cr** in November-26.")                 # a figure was dropped
    assert not figures_match(a, a + " That is 51% lower.")                              # a figure was added


def test_gemini_phrase_calls_and_failures():
    class Resp:
        def __init__(self, code, text=""):
            self.status_code = code
            self._b = {"candidates": [{"content": {"parts": [{"text": text}]}}]}

        def json(self):
            return self._b

    class Session:
        def __init__(self, resp):
            self.resp, self.sent = resp, None

        def post(self, url, json=None, timeout=None, headers=None):
            self.sent = (url, json, headers, timeout)
            if isinstance(self.resp, Exception):
                raise self.resp
            return self.resp

    answer = "Total POs is **514 POs** (all months so far)."
    s = Session(Resp(200, "Abhi tak kul **514 POs** hain."))
    g = GeminiInterpreter("k", session=s)
    assert g.phrase("total po kitne", answer) == "Abhi tak kul **514 POs** hain."
    url, body, headers, timeout = s.sent
    assert headers["x-goog-api-key"] == "k" and "k" not in url and "total po kitne" in str(body)
    assert GeminiInterpreter("k", session=Session(Resp(200, "Total **515 POs**."))).phrase("q", answer) is None
    assert GeminiInterpreter("k", session=Session(Resp(200, "```Total 514 POs```"))).phrase("q", answer) is None
    assert GeminiInterpreter("k", session=Session(Resp(429))).phrase("q", answer) is None
    assert GeminiInterpreter("k", session=Session(TimeoutError())).phrase("q", answer) is None
    assert GeminiInterpreter("k", session=Session(Resp(200, "x")), phrasing=False).phrase("q", answer) is None


def test_phrasing_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.delenv("ASSISTANT_GEMINI", raising=False)
    monkeypatch.setenv("ASSISTANT_GEMINI_PHRASING", "off")
    g = GeminiInterpreter.from_env()
    assert g is not None and g.phrasing is False
