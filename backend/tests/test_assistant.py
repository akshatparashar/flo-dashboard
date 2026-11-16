"""FLO Assistant: answers must quote the dashboard's own figures, understand English and Hinglish, stay read-only, and
fall back gracefully. Runs on the built-in demo data; every expected number is read from the API in the same test."""
from __future__ import annotations

import json
import re

import pytest
from fastapi.testclient import TestClient

from app import main
from app.assistant import Assistant
from app.assistant import fmt
from app.assistant.gemini import GeminiInterpreter
from app.config import Settings
from app.sources.demo import DemoSheetSource
from app.sources.google import SheetAccessError
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


def ask(client, message, context=None):
    r = client.post("/api/chat", json={"message": message, "context": context})
    assert r.status_code == 200, r.text
    return r.json()


def kpi(client, path, label, **params):
    body = client.get(path, params=params).json()
    k = next(k for k in body["kpis"] if k["label"] == label)
    return fmt.value(k["value"], k["format"], k.get("unit") or "")


def bold(answer):
    return re.findall(r"\*\*(.+?)\*\*", answer)


# ------------------------------------------------------------------------------------------------ numbers
def test_total_pos_matches_fabric_po_page(client):
    r = ask(client, "what is the total PO count")
    assert r["understood"] and r["page"] == "/fabric-po"
    assert kpi(client, "/api/fabric-po", "Total POs") in bold(r["answer"])
    assert r["answer"].startswith("Total POs")


def test_month_filter(client):
    r = ask(client, "total po count for april")
    assert "April-26" in r["answer"]
    assert kpi(client, "/api/fabric-po", "Total POs", month="April-26") in bold(r["answer"])


def test_month_range_hinglish(client):
    r = ask(client, "april se june tak ka revenue")
    want = client.get("/api/target", params=[("month", m) for m in ("April-26", "May-26", "June-26")]).json()
    k = next(k for k in want["filtered"]["kpis"] if k["label"] == "Total revenue")
    assert fmt.value(k["value"], "inr") in bold(r["answer"])


def test_name_filter_hinglish(client):
    r = ask(client, "Rekha ka pending kitna hai")
    assert "REKHA" in r["answer"]
    assert kpi(client, "/api/production", "Pending", designer="REKHA") in bold(r["answer"])


def test_specific_word_beats_page_word(client):
    r = ask(client, "kitne samples reject hue")
    assert kpi(client, "/api/samples", "Rejected") in bold(r["answer"])


def test_po_counts_not_pieces(client):
    r = ask(client, "how many POs are overdue")
    assert "POs" in r["answer"] and "pcs" not in r["answer"]


def test_ranking_matches_table_order(client):
    r = ask(client, "top 3 vendors by pending fabric")
    t = client.get("/api/fabric-po").json()["tables"]["vendors"]
    ci = next(i for i, c in enumerate(t["columns"]) if c["label"] == "Pending (mtr)")
    rows = sorted((r_ for r_ in t["rows"] if not str(r_[0]).startswith(("(", "TOTAL"))), key=lambda x: -x[ci])
    names = [n for n in bold(r["answer"])]
    assert names[:3] == [rows[0][0], rows[1][0], rows[2][0]]


def test_top_designer_uses_designers_page(client):
    r = ask(client, "top designer")
    top = client.get("/api/designer").json()["kpis"]
    assert next(k["value"] for k in top if k["label"] == "Top performer") in r["answer"]
    assert r["page"] == "/designers"


def test_trend(client):
    r = ask(client, "revenue month wise")
    assert r["intent"] == "trend" and "April-26" in r["answer"]


def test_compare(client):
    r = ask(client, "compare rekha vs anamika revenue")
    assert r["intent"] == "compare" and "REKHA" in r["answer"] and "ANAMIKA" in r["answer"]
    assert "higher by" in r["answer"]


def test_po_record_lookup(client):
    po = client.get("/api/fabric-po").json()["tables"]["pos"]["rows"][0][0]
    number = re.sub(r"\D", "", po)
    r = ask(client, f"po {number} ka status")
    assert r["intent"] == "record" and po in r["answer"]


def test_compare_two_measures(client):
    r = ask(client, "new vs repeat revenue")
    assert r["intent"] == "compare"
    k = {k["label"]: k for k in client.get("/api/target").json()["filtered"]["kpis"]}
    assert fmt.value(k["New order revenue"]["value"], "inr") in bold(r["answer"])
    assert "new + repeat" not in r["answer"]
    r = ask(client, "pending vs received in april")
    assert r["intent"] == "compare" and "April-26" in r["answer"]
    assert kpi(client, "/api/production", "Pending", month="April-26") in bold(r["answer"])


def test_total_orders_is_all_orders_not_new_only(client):
    r = ask(client, "total orders")
    assert not r["answer"].startswith("New")
    ov = client.get("/api/overview").json()["sections"]["orders"]["kpis"]
    want = next(k for k in ov if k["label"] == "Order qty")
    assert fmt.value(want["value"], "int", "pcs") in bold(r["answer"])


def test_one_month_of_a_yearly_figure(client):
    t = client.get("/api/target").json()["tracker"]["table"]
    ci = next(i for i, c in enumerate(t["columns"]) if c["label"] == "Target")
    row = next(r for r in t["rows"] if r[0] == "November-26")
    r = ask(client, "this month target")
    assert "November-26" in r["answer"] and fmt.value(row[ci], "inr") in bold(r["answer"])
    assert "every month" in ask(client, "monthly target")["answer"]


def test_best_and_worst_vendor_rank_by_on_time_rate(client):
    r = ask(client, "worst vendor")
    assert r["intent"] == "rank" and "On-Time %" in r["answer"]
    r = ask(client, "on time rate of vendors")
    assert r["intent"] == "rank" and r["page"] == "/fabric-po" and r["answer"].count("%") >= 3


def test_every_row_of_a_kind(client):
    r = ask(client, "har designer ka revenue")
    assert r["intent"] == "rank" and r["answer"].count("₹") >= 5


def test_fabric_words_mean_fabric_po(client):
    r = ask(client, "fabric pending month wise")
    assert r["page"] == "/fabric-po" and "mtr" in r["answer"]


def test_table_units_follow_the_page(client):
    r = ask(client, "category wise pending")
    assert r["intent"] == "rank" and r["answer"].count("pcs") >= 3


def test_dimension_word_is_not_a_name(client):
    r = ask(client, "best client")
    assert r["intent"] == "rank" and r["understood"]


# ------------------------------------------------------------------------------------------------ answer style
def test_one_word_and_detail(client):
    short = ask(client, "approval rate in one word")
    assert short["answer"] == f"**{kpi(client, '/api/samples', 'Approval rate')}**"
    long = ask(client, "pending pcs in detail")
    assert "By " in long["answer"] and long["answer"].count("•") >= 3


def test_follow_up_keeps_subject(client):
    first = ask(client, "total samples")
    second = ask(client, "and for may", first["context"])
    assert "May-26" in second["answer"]
    assert kpi(client, "/api/samples", "Total samples", month="May-26") in bold(second["answer"])


# ------------------------------------------------------------------------------------------------ dashboard features
def test_counts_lists_pages_and_help(client):
    designers = [d for d in client.get("/api/designer").json()["options"]["designer"] if not d.startswith("(")]
    assert f"**{len(designers)}**" in ask(client, "how many designers")["answer"]
    assert "GANGA MILLS" in ask(client, "list vendors")["answer"]
    about = ask(client, "production page kya dikhata hai")
    assert about["intent"] == "page" and about["page"] == "/production"
    assert ask(client, "where can I see delayed POs")["page"] == "/fabric-po"
    assert "Download CSV" in ask(client, "how do I download the table")["answer"]
    assert ask(client, "hi")["intent"] == "greet"


def test_unrelated_question_is_not_answered_with_a_number(client):
    r = ask(client, "what is the weather in delhi")
    assert r["understood"] is False
    assert not re.search(r"\d", r["answer"])


# ------------------------------------------------------------------------------------------------ safety
def test_read_only(client, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("the assistant must not refresh or write")
    monkeypatch.setattr(DataStore, "refresh", boom)
    assert ask(client, "total revenue")["understood"]


def test_validation_and_auth(monkeypatch):
    settings = Settings(data_source="demo", passcode="flo-2026", token_secret="s")
    store = DataStore(DemoSheetSource(), settings)
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    monkeypatch.setattr(main, "get_store", lambda: store)
    c = TestClient(main.app)
    assert c.post("/api/chat", json={"message": "total POs"}).status_code == 401
    tok = c.post("/api/auth/login", json={"passcode": "flo-2026"}).json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert c.post("/api/chat", json={"message": ""}, headers=h).status_code == 422
    assert c.post("/api/chat", json={"message": "x" * 501}, headers=h).status_code == 422


def test_sheet_down_gives_a_clear_message(monkeypatch):
    class Down(DemoSheetSource):
        def get_values(self, *a, **k):
            raise SheetAccessError("Google API 503")
    settings = Settings(data_source="demo")
    store = DataStore(Down(), settings)
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    monkeypatch.setattr(main, "get_store", lambda: store)
    monkeypatch.setattr(main, "get_assistant", lambda: Assistant(main._assistant_fetch))
    r = TestClient(main.app).post("/api/chat", json={"message": "total POs"}).json()
    assert r["understood"] is False and "can't read" in r["answer"]


# ------------------------------------------------------------------------------------------------ optional Gemini
class FakeInterpreter:
    def __init__(self, hint):
        self.hint, self.calls = hint, []

    def interpret(self, question, catalog):
        self.calls.append((question, catalog))
        return self.hint


def test_gemini_only_when_rules_fail(client):
    fake = FakeInterpreter({"intent": "value", "metric": "Total POs", "page": "fabric-po"})
    a = Assistant(main._assistant_fetch, interpreter=fake)
    assert a.answer("total revenue")["engine"] == "rules" and not fake.calls
    r = a.answer("purchase paperwork tally?")
    assert r["engine"] == "gemini" and kpi(client, "/api/fabric-po", "Total POs") in bold(r["answer"])
    question, catalog = fake.calls[0]
    sent = json.dumps(catalog)
    assert "Total POs" in sent and not re.search(r"\d{3,}", sent.replace("-26", "").replace("-27", ""))


def test_gemini_bad_label_is_ignored(client):
    a = Assistant(main._assistant_fetch, interpreter=FakeInterpreter({"intent": "value", "metric": "Made up"}))
    assert a.answer("purchase paperwork tally?")["understood"] is False


def test_gemini_client_request_and_failures():
    class Resp:
        def __init__(self, code, body):
            self.status_code, self._body = code, body

        def json(self):
            return self._body

    class Session:
        def __init__(self, resp):
            self.resp, self.sent = resp, None

        def post(self, url, json=None, timeout=None, headers=None):
            self.sent = (url, json, headers)
            if isinstance(self.resp, Exception):
                raise self.resp
            return self.resp

    cat = {"pages": {"fabric-po": "Fabric PO"}, "labels": ["Total POs"], "dimensions": ["vendor"], "months": []}
    ok = Session(Resp(200, {"candidates": [{"content": {"parts": [{"text": '{"intent":"value","metric":"Total POs"}'}]}}]}))
    g = GeminiInterpreter("k", "gemini-flash-lite-latest", session=ok)
    assert g.interpret("po kitne", cat) == {"intent": "value", "metric": "Total POs"}
    url, body, headers = ok.sent
    assert "gemini-flash-lite-latest" in url and headers["x-goog-api-key"] == "k" and "k" not in url
    assert GeminiInterpreter("k", session=Session(Resp(429, {}))).interpret("x", cat) is None
    assert GeminiInterpreter("k", session=Session(TimeoutError())).interpret("x", cat) is None


def test_gemini_off_without_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert GeminiInterpreter.from_env() is None
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("ASSISTANT_GEMINI", "off")
    assert GeminiInterpreter.from_env() is None


def test_hinglish_target_left(client):
    r = ask(client, "target kitna bacha hai")
    assert r["answer"].startswith("Remaining target")
