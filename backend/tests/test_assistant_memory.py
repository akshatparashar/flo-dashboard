"""FLO Assistant conversation memory (last 15 messages per chat), multi-question messages, follow-ups and page
routing. Figures are read from the dashboard API inside each test. Runs on the built-in demo data."""
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
    send.store = store
    return send


def test_store_keeps_last_15_and_drops_oldest():
    s = ConversationStore(":memory:")
    cid = s.new_id()
    for i in range(20):
        s.add(cid, "user" if i % 2 == 0 else "assistant", f"m{i}")
    msgs = s.messages(cid)
    assert len(msgs) == 15
    assert msgs[0]["text"] == "m5" and msgs[-1]["text"] == "m19"


def test_conversations_are_isolated_and_ids_are_random(chat):
    a = chat("How many orders does each customer have?")
    b = chat("How many vendors are there?")
    assert a["conversation_id"] != b["conversation_id"]
    assert ConversationStore.valid(a["conversation_id"])
    assert all(m["text"] != "How many vendors are there?" for m in chat.store.messages(a["conversation_id"]))


def test_history_endpoint_returns_the_chat(chat, client):
    r = chat("total PO count")
    h = client.get(f"/api/chat/{r['conversation_id']}").json()
    assert [m["role"] for m in h["messages"]] == ["user", "assistant"]
    assert client.get("/api/chat/not-an-id").status_code == 404


def busiest(client):
    t = client.get("/api/designer").json()["tables"]["designers"]
    rows = {r[0]: r for r in t["rows"] if r[0] != "TOTAL"}
    return max(rows, key=lambda k: rows[k][-1])


def test_follow_ups_keep_the_designer_through_server_memory(chat, client):
    name = busiest(client)
    rep = client.get("/api/designer", params={"designer": name, "order_type": "REPEAT"}).json()
    rep_n = rep["tables"]["designers"]["rows"][0][-1]
    r1 = chat(f"Tell me {name.title()}'s total orders")
    r2 = chat("How many are repeat orders?", r1["conversation_id"])
    assert name in r2["answer"] and f"{rep_n:,} repeat order" in r2["answer"]
    r3 = chat("What percentage are repeat orders?", r1["conversation_id"])
    assert name in r3["answer"] and "%" in r3["answer"]


def test_compare_both_uses_the_last_two_names(chat, client):
    t = client.get("/api/designer").json()["tables"]["designers"]
    a, b = [r[0] for r in t["rows"] if r[0] != "TOTAL"][:2]
    r1 = chat(f"How many orders does {a} have?")
    chat(f"what about {b}?", r1["conversation_id"])
    r3 = chat("compare both", r1["conversation_id"])
    assert a in r3["answer"] and b in r3["answer"] and "more" in r3["answer"]


def test_multi_question_answers_every_part(chat, client):
    name = busiest(client)
    r = chat(f"How many orders does {name} have and how many are repeat?")
    assert r["intent"] == "multi"
    assert "**1." in r["answer"] and "**2." in r["answer"]


def test_named_page_wins(chat, client):
    ff = client.get("/api/flo-future").json()["tables"]["designers"]["rows"]
    row = next(r for r in ff if not str(r[0]).startswith("(") and r[0] != "TOTAL")
    r = chat(f"How much is pending for {row[0]} in FLO Future?")
    assert r["page"] == "/flo-future"
