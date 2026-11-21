"""Total / completed / pending / completion % per designer on Production and FLO Future, kept apart.
Every expected figure is read from the same page API with the same filters. Runs on the built-in demo data."""
from __future__ import annotations

import pytest

from app import main
from app.assistant.memory import ConversationStore
from test_assistant_calc import client  # noqa: F401  (fixture)


@pytest.fixture()
def chat(client, monkeypatch):
    store = ConversationStore(":memory:")
    monkeypatch.setattr(main, "get_conversations", lambda: store)

    def send(message, conv=None):
        r = client.post("/api/chat", json={"message": message, "conversation_id": conv})
        assert r.status_code == 200, r.text
        return r.json()
    return send


def kpi(client, path, start, **params):
    return next(k["value"] for k in client.get(path, params=params).json()["kpis"] if k["label"].startswith(start))


def two_designers(client):
    rows = client.get("/api/flo-future").json()["tables"]["designers"]["rows"]
    names = [r[0] for r in rows if r[0] != "TOTAL" and not str(r[0]).startswith("(")]
    prod = set(client.get("/api/production").json()["options"]["designer"])
    both = [n for n in names if n.upper() in {p.upper() for p in prod}]
    return both[0], both[1]


def pcs(v):
    return f"{v:,.0f} pcs"


def test_total_and_pending_shows_both_pages_separately(chat, client):
    a, _ = two_designers(client)
    r = chat(f"How much total and pending quantity does {a} have?")
    up = a.upper()
    assert pcs(kpi(client, "/api/production", "Pending", designer=up)) in r["answer"]
    assert pcs(kpi(client, "/api/production", "In production", designer=up)) in r["answer"]
    assert pcs(kpi(client, "/api/flo-future", "Pending", designer=a)) in r["answer"]
    assert pcs(kpi(client, "/api/flo-future", "Target Qty", designer=a)) in r["answer"]
    assert "never added" in r["answer"]


def test_follow_up_keeps_all_metrics_and_compare_shows_a_table(chat, client):
    a, b = two_designers(client)
    r1 = chat(f"Show completed, pending and completion percentage for {a}.")
    done, tot = kpi(client, "/api/flo-future", "Completed", designer=a), kpi(client, "/api/flo-future", "Target Qty", designer=a)
    assert pcs(done) in r1["answer"] and (f"{done / tot * 100:.2f}%" if tot else "not available") in r1["answer"]
    r2 = chat(f"What about {b}?", r1["conversation_id"])
    for start in ("Completed", "Pending"):
        assert pcs(kpi(client, "/api/flo-future", start, designer=b)) in r2["answer"]
    assert "Completion %" in r2["answer"]
    r3 = chat("Compare both designers.", r1["conversation_id"])
    assert "| Metric |" in r3["answer"] and a.upper() in r3["answer"].upper() and b.upper() in r3["answer"].upper()


def test_named_page_only(chat, client):
    a, _ = two_designers(client)
    r = chat(f"Show {a}'s pending quantity in FLO Future.")
    assert "Production" not in r["answer"]
    assert pcs(kpi(client, "/api/flo-future", "Pending", designer=a)) in r["answer"]
    r = chat(f"Show {a}'s pending quantity in Production.")
    assert "FLO Future" not in r["answer"]
    assert pcs(kpi(client, "/api/production", "Pending", designer=a.upper())) in r["answer"]


def test_page_totals_separately(chat, client):
    r = chat("Show pending quantity from Production and FLO Future separately.")
    assert pcs(kpi(client, "/api/production", "Pending")) in r["answer"]
    assert pcs(kpi(client, "/api/flo-future", "Pending")) in r["answer"]
