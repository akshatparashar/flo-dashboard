"""Stock Ageing through FLO Assistant, and questions it used to get wrong (arriving deliveries by month, outsource
projects, "visits and meetings", a person's open tasks). Expected figures are read from the API in the same run."""
from __future__ import annotations

import pytest

from app import main
from app.assistant import fmt, planner, stock
from test_assistant_calc import client  # noqa: F401  (fixture)


@pytest.fixture(autouse=True)
def no_snapshot(monkeypatch):
    monkeypatch.delenv("SQL_SNAPSHOT_DIR", raising=False)


def chat(client, message, conv=None):
    r = client.post("/api/chat", json={"message": message, "conversation_id": conv})
    assert r.status_code == 200, r.text
    return r.json()


def inr(v):
    return f"₹{v / 1e7:,.2f} Cr" if v >= 1e7 else f"₹{v / 1e5:,.2f} L" if v >= 1e5 else f"₹{v:,.0f}"


@pytest.mark.parametrize("question", ["stock ageing report", "closing stock kitna hai", "Stock value batao"])
def test_stock_summary(client, question):
    body = client.get("/api/stock-ageing").json()
    a = chat(client, question)
    assert a["page"] == "/stock-ageing" and a["page_label"] == "Stock Ageing"
    assert "Closing stock:" in a["answer"] and f"**{fmt.fmt_int(body['summary']['qty'])} pcs**" in a["answer"]
    assert "demo rows" in a["answer"]                     # made-up data is always called out (English or Hinglish)


@pytest.mark.parametrize("question,buckets", [("stock value over 180 days", [4, 5]),
                                              ("kitna stock 1 saal se purana hai", [5]),
                                              ("old stock over 90 days", [3, 4, 5])])
def test_stock_age_bands(client, question, buckets):
    body = client.get("/api/stock-ageing").json()
    value = sum(body["charts"]["value_by_age"][i]["value"] for i in buckets)
    a = chat(client, question)
    assert a["page"] == "/stock-ageing" and inr(value) in a["answer"]


def test_series_number_is_not_an_age(client):
    options = client.get("/api/stock-ageing").json()["options"]["type"]
    series = next(o for o in options if o.startswith("Series "))
    a = chat(client, f"stock ageing {series.lower()}")
    assert series in a["answer"] and "days old" not in a["answer"] and "Closing stock" in a["answer"]


def test_stock_follow_up(client):
    first = chat(client, "closing stock kitna hai")
    follow = chat(client, "aur over 365 days?", first["conversation_id"])
    assert follow["page"] == "/stock-ageing" and ("over 365 days old" in follow["answer"] or "365 din se purana" in follow["answer"])


def test_other_stock_words_are_left_to_their_pages():
    assert not stock.matches("fabricator remaining stock kitna hai", None)
    assert not stock.matches("fabric po pending", "stock-ageing")
    assert not stock.matches("production pending kitna hai", None)


def test_arriving_in_a_month(client):
    t = client.get("/api/client").json()["delivery60"]["tables"]["months"]["rows"]
    month = t[0][0].split("-")[0].lower()
    a = chat(client, f"{month} me kitne pcs aane wale hai")
    assert "Expected deliveries" in a["answer"] and "Total quantity" not in a["answer"]
    assert t[0][0] in a["answer"]


def test_which_month_has_most_deliveries(client):
    rows = [r for r in client.get("/api/client").json()["delivery60"]["tables"]["months"]["rows"] if r[0] != "TOTAL"]
    best = max(rows, key=lambda r: r[2])[0]
    for q in ("which month has the most expected deliveries", "kis month me sabse zyada pcs aane wale hai"):
        assert chat(client, q)["answer"].startswith(f"**{best}**")


def test_visits_and_meetings_is_one_question(client):
    assert len(planner.split_questions("visits and meetings status")) == 1
    a = chat(client, "visits and meetings status")["answer"]
    assert a.count("Visits & Meetings Done") == 1


def test_outsource_projects_are_listed(client):
    rows = [r for r in client.get("/api/flo-future").json()["tables"]["outsource"]["rows"] if r[0] != "TOTAL"]
    a = chat(client, "outsource projects in flo future")
    assert a["understood"] and f"**{len(rows)}** outsource project" in a["answer"]


def test_registry_has_every_page_the_assistant_reads():
    assert {"stock-ageing", "daily-delegation", "in-out-sale"} <= set(main._ASSISTANT_PAGES)
