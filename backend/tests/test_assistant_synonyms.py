"""Other words and opposites, and the questions that were answered wrongly. Figures are read from the dashboard's own
endpoints in the same run (made-up demo rows)."""
from __future__ import annotations

import pytest

from app.assistant import synonyms
from test_assistant_calc import client  # noqa: F401  (fixture)


@pytest.fixture(autouse=True)
def no_snapshot(monkeypatch):
    monkeypatch.delenv("SQL_SNAPSHOT_DIR", raising=False)
    monkeypatch.delenv("EASYTRADE_MCP_URL", raising=False)


def ask(client, message):
    return client.post("/api/chat", json={"message": message}).json()


def text(reply):
    return reply["answer"].replace("**", "")


# pairs that must be read as the same question
@pytest.mark.parametrize("other,usual", [
    ("how much inventory do we have", "closing stock"),
    ("total stock", "closing stock"),
    ("warehouse inventory", "closing stock"),
    ("non moving inventory", "unsold stock"),
    ("stagnant items", "unsold stock"),
    ("slow moving stock", "unsold stock"),
    ("newest stock", "fresh stock"),
    ("earnings this month", "revenue this month"),
    ("costliest supplier for crepe", "most expensive vendor for crepe"),
    ("passed samples", "approved samples"),
    ("accepted samples", "approved samples"),
    ("failed samples", "rejected samples"),
    ("declined samples", "rejected samples"),
    ("incomplete pcs in production", "pending pcs in production"),
    ("completed pcs in production", "received pcs in production"),
    ("undelivered fabric", "pending fabric"),
    ("unfinished tasks", "open tasks"),
    ("closed tasks", "completed tasks"),
    ("biggest client", "top client"),
])
def test_other_words_give_the_same_answer(client, other, usual):
    a, b = ask(client, other), ask(client, usual)
    assert a["understood"] and b["understood"], (a["answer"][:150], b["answer"][:150])
    assert a["answer"] == b["answer"]


@pytest.mark.parametrize("question", ["maal kitna pada hai", "godown me kitna stock hai", "naya maal"])
def test_hinglish_stock_words(client, question):
    a = ask(client, question)
    assert a["page"] == "/stock-ageing" and a["understood"], a["answer"][:150]


@pytest.mark.parametrize("question", ["kitna maal aaya", "fabricator stock", "net sale", "failed pos",
                                      "design 70- 71144/S kab bika tha", "kitne designs 90 din se nahi bike",
                                      "sales has declined", "delivered fabric rate"])
def test_words_are_left_alone_where_they_mean_something_else(question):
    said = synonyms.normalise(question)
    assert "closing stock" not in said and "fast selling" not in said and "rejected" not in said
    assert "sale pcs kitne" not in said


def test_fast_selling_is_the_opposite_of_unsold(client):
    for q in ("fast moving designs", "best selling designs", "sold stock"):
        a = ask(client, q)
        assert a["page"] == "/stock-ageing" and "Fastest selling" in text(a), a["answer"][:150]
    assert ask(client, "kitna bika")["page"] == "/in-out-sale"


def test_oldest_open_task_is_not_the_completed_ranking(client):
    def oldest(**filters):
        body = client.get("/api/daily-delegation", params=filters).json()
        return next(k for k in body["kpis"] if k["label"] == "Oldest open task")

    for q, old in (("sabse purana open task", oldest()), ("sabse purana task kiska hai", oldest()),
                   ("oldest pending task", oldest(status="Pending"))):
        a = ask(client, q)
        assert a["page"] == "/daily-delegation" and old["hint"] in text(a), a["answer"][:200]
        assert "Completed" not in a["answer"].split("\n")[0]


@pytest.mark.parametrize("question", ["georgette ka rate", "rate of chiffonette", "banarasi ka sabse sasta vendor"])
def test_an_unknown_fabric_is_not_given_another_rate(client, question):
    a = ask(client, question)
    assert a["page"] == "/vendor-rate" and "no fabric called" in text(a), a["answer"][:150]
    assert "Received rate" not in a["answer"]


def test_worst_vendor_in_hinglish(client):
    assert ask(client, "sabse kharab vendor")["answer"].split()[-1] == ask(client, "worst vendor")["answer"].split()[-1]


@pytest.mark.parametrize("question", ["urgent items", "urgent kya hai", "what needs attention"])
def test_urgent_lists_the_overview_alerts(client, question):
    alerts = client.get("/api/overview").json()["alerts"]
    a = ask(client, question)
    assert a["page"] == "/" and (alerts[0].get("text") or alerts[0]["title"]) in text(a)


@pytest.mark.parametrize("question,path,group", [
    ("where is vendor rate", "/vendor-rate", "Operations"),
    ("delegation kaha dikhega", "/daily-delegation", "Management"),
    ("production page kidhar hai", "/production", "Operations"),
    ("where can I see fabric rates", "/vendor-rate", "Operations"),
    ("samples kaha milega", "/samples", "Design and sales"),
])
def test_where_is_a_page(client, question, path, group):
    a = ask(client, question)
    assert a["page"] == path and f"under {group}" in text(a), a["answer"][:150]


def test_flo_world_and_team_status(client):
    assert "coming soon" in text(ask(client, "FLO World kya hai"))
    assert "coming soon" in text(ask(client, "flo premium kya hai"))
    teams = client.get("/api/flo-future").json()["tables"]["teams"]["rows"]
    a = ask(client, "team wise status")
    assert a["page"] == "/flo-future" and all(str(r[0]) in a["answer"] for r in teams)


def test_most_overdue_whose_is_about_overdue(client):
    a = ask(client, "sabse zyada overdue kiska")
    assert "Overdue" in a["answer"] and "Pending" not in a["answer"], a["answer"][:150]


def talk(client, *messages):
    conv = ctx = None
    out = []
    for m in messages:
        j = client.post("/api/chat", json={"message": m, "conversation_id": conv, "context": ctx}).json()
        conv = j["conversation_id"]
        ctx = j["context"] if j["understood"] else ctx
        out.append(j)
    return out


def test_stock_that_came_in_is_not_the_closing_stock(client):
    assert ask(client, "kitna maal aaya")["page"] != "/stock-ageing"


def test_kharab_samples_are_the_rejected_ones(client):
    assert ask(client, "kharab samples")["answer"].split("**")[1:2] == ask(client, "rejected samples")["answer"].split("**")[1:2]


def test_fabricator_stock_is_the_fabricators_page(client):
    assert ask(client, "fabricator stock")["page"] == "/fabricators"


def test_follow_ups_after_tasks_and_selling(client):
    _, old = talk(client, "open tasks", "sabse purana?")
    assert old["page"] == "/daily-delegation" and "Oldest open task" in text(old), old["answer"][:200]
    first, listed = talk(client, "best selling designs", "kaunse designs hain?")
    assert "Fastest selling" in text(listed), listed["answer"][:200]
