"""Short follow-ups must stay on the subject of the earlier question. Every expected figure or page is read from the
dashboard API in the same run (demo data), and each conversation is driven like the chat widget: the conversation id
and the last context are sent back with every message."""
from __future__ import annotations

import pytest

from app.assistant import fmt, followups
from test_assistant_calc import client  # noqa: F401  (fixture)


@pytest.fixture(autouse=True)
def no_snapshot(monkeypatch):
    monkeypatch.delenv("SQL_SNAPSHOT_DIR", raising=False)
    monkeypatch.delenv("EASYTRADE_MCP_URL", raising=False)


def talk(client, *messages):
    """Sends the messages as one conversation and returns every reply."""
    conv = ctx = None
    out = []
    for m in messages:
        r = client.post("/api/chat", json={"message": m, "conversation_id": conv, "context": ctx})
        assert r.status_code == 200, r.text
        j = r.json()
        conv = j["conversation_id"]
        if j["understood"]:
            ctx = j["context"]
        out.append(j)
    return out


def text(reply):
    return reply["answer"].replace("**", "")


def test_the_name_that_came_top_is_remembered(client):
    first, follow = talk(client, "kis fabricator ka sabse zyada pending hai", "uska received?")
    name = first["context"]["top"]["name"]
    assert name in text(first)
    body = client.get("/api/production", params={"fabricator": name}).json()
    received = next(k["value"] for k in body["kpis"] if k["label"] == "Received")
    assert follow["page"] == "/production" and name in text(follow) and fmt.fmt_int(received) in text(follow)


def test_a_month_keeps_the_in_out_sale_figure(client):
    month = client.get("/api/in-out-sale").json()["options"]["month"][3]
    word = month.split("-")[0].lower()
    first, follow = talk(client, "net sale this year", f"{word} ka?")
    assert follow["page"] == "/in-out-sale" and "Net sale" in text(follow) and month in text(follow)
    _, _, incoming = talk(client, "net sale this year", f"{word} ka?", "aur incoming?")
    assert "Incoming pcs" in text(incoming) and month in text(incoming)       # the month stays in hand


def test_fw_orders_follow_ups_stay_on_fw_orders(client):
    rows = [r for r in client.get("/api/client").json()["fw_orders"]["table"]["rows"] if r[0] != "TOTAL"]
    word = rows[1][0].split("-")[0].lower()
    _, month, dispatched = talk(client, "fw orders pending kitna hai", f"{word} me?", "dispatched?")
    for reply in (month, dispatched):
        assert "FW ORDER'S" in text(reply) and fmt.fmt_int(rows[1][2]) in text(reply)


def test_delivery_month_follow_up_reads_delivery_dates(client):
    rows = [r for r in client.get("/api/client").json()["delivery60"]["tables"]["months"]["rows"] if r[0] != "TOTAL"]
    month = rows[-1][0]
    _, follow = talk(client, "expected deliveries month wise", f"{month.split('-')[0].lower()} me kitne?")
    assert "Expected deliveries" in text(follow) and month in text(follow) and fmt.fmt_int(rows[-1][2]) in text(follow)


def test_target_achieved_after_remaining(client):
    _, follow = talk(client, "target kitna bacha hai", "ab tak kitna hua?")
    assert follow["page"] == "/target" and "achieved" in text(follow).lower()


def test_po_ranking_follow_up_ranks_overdue_pos_then_keeps_the_vendor(client):
    _, ranked, metres = talk(client, "kitne PO overdue hai", "kis vendor ke sabse zyada?", "uska pending metre?")
    assert "Overdue" in text(ranked)
    name = ranked["context"]["top"]["name"]
    assert name in text(ranked) and name in text(metres) and metres["page"] == "/fabric-po"
    assert "Production" not in text(metres)


def test_compare_both_after_two_flo_future_questions(client):
    designers = [r[0] for r in client.get("/api/flo-future").json()["tables"]["designers"]["rows"] if r[0] != "TOTAL"]
    a, b = designers[0].lower(), designers[1].lower()
    for follow in ("dono compare karo", "kiska zyada hai?"):
        reply = talk(client, f"flo future me {a} ka pending kitna hai", f"aur {b} ka?", follow)[-1]
        assert reply["understood"] and reply["page"] == "/flo-future"
        assert a.upper() in text(reply).upper() and b.upper() in text(reply).upper()


def test_flo_overdue_whose(client):
    _, follow = talk(client, "flo future overdue batao", "kiske hain?")
    assert follow["page"] == "/flo-future" and "overdue" in text(follow).lower() and "•" in follow["answer"]


def test_stock_follow_ups(client):
    series = next(o for o in client.get("/api/stock-ageing").json()["options"]["type"] if o.startswith("Series "))
    replies = talk(client, "closing stock kitna hai", "stock 1 saal se purana kitna hai?", f"{series.lower()} ka?",
                   "uski value?", "kaunse designs hain?")
    for reply in replies:
        assert reply["page"] == "/stock-ageing", reply["answer"][:120]
    value, designs = replies[3], replies[4]
    assert series in text(value) and "over 365 days old" in text(value)
    body = client.get("/api/stock-ageing", params={"type": series}).json()
    old = next(c for c in body["unsold"]["cards"] if c["days"] == 365)
    assert f"{old['designs']:,} designs" in text(designs)


def test_rates_follow_ups(client):
    first, narrower, other = talk(client, "crepe ka sabse sasta vendor kaun hai", "44 width me?", "silk ka?")
    assert "cheapest Crepe" in text(first) and 'cheapest Crepe at 44"' in text(narrower)
    assert "cheapest Silk" in text(other)


def test_fabricator_follow_ups_stay_on_the_stock_sheet(client):
    _, top, share, month = talk(client, "fabricator remaining stock kitna hai", "sabse zyada kiske paas?",
                                "uska received percent?", "october me incoming?")
    name = top["context"]["top"]["name"]
    assert "highest Remaining" in text(top) and name in text(share)
    assert month["page"] == "/fabricators" and "Monthly Incoming" in text(month)


def test_delegation_follow_up_does_not_jump_to_another_page(client):
    people = client.get("/api/daily-delegation").json()["options"]["person"]
    _, follow = talk(client, f"{people[0].lower()} ke pending task", "kitne din se open hai?")
    assert follow["page"] == "/daily-delegation" and "open" in text(follow).lower()


def test_the_browsers_context_wins_over_older_server_memory(client):
    """A second server instance may remember less than the browser was told: the browser's context is the newer one."""
    first = client.post("/api/chat", json={"message": "deepika ke total orders kitne hai"}).json()
    newer = client.post("/api/chat", json={"message": "charu ke total orders kitne hai"}).json()["context"]
    reply = client.post("/api/chat", json={"message": "new kitne?", "conversation_id": first["conversation_id"],
                                           "context": newer}).json()
    assert "CHARU" in text(reply).upper() and "DEEPIKA" not in text(reply).upper()


@pytest.mark.parametrize("message", ["production pending kitna hai", "stock ageing report", "net sale this year",
                                     "total po count", "kis fabricator ka sabse zyada pending hai",
                                     "aur vendor rate me sabse sasta silk?", "dashboard summary"])
def test_full_questions_are_left_alone(client, message):
    """A message that stands on its own is never rebuilt, whatever came before it."""
    for before in ("fw orders pending kitna hai", "closing stock kitna hai", "kitne PO overdue hai"):
        ctx = talk(client, before)[0]["context"]
        assert followups.resolve(message, ctx, [ctx], [], []) is None, (before, message)


@pytest.mark.parametrize("context", [{"topic": "production", "top": "oops"}, {"topic": 5, "asked": []},
                                     {"topic": "stock", "band": 3, "series": None}, {"topic": "po", "overdue": True,
                                     "top": {"name": None}}, {"entities": "x", "topic": "flo"}])
def test_a_broken_context_from_the_browser_never_breaks_the_chat(client, context):
    for message in ("uska received?", "dono compare karo", "uski value?", "total po count"):
        r = client.post("/api/chat", json={"message": message, "context": context})
        assert r.status_code == 200, (context, message, r.text)
