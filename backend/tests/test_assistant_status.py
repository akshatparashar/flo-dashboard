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


# ------------------------------------------------------------------------------------------------ designs: ready / pending
def prod_designs(client, name, status=None):
    p = {"designer": name.upper()}
    if status:
        opts = client.get("/api/production").json()["options"]["status"]
        p["status"] = [s for s in opts if s.upper() in ("DONE", "COMPLETED", "COMPLETE")]
    return int(kpi(client, "/api/production", "Designs in production", **p))


def ff_summary(client, name):
    return client.get("/api/flo-future", params={"designer": name}).json()["summary"]


def pick_designer(client):
    """A designer with designs on both pages."""
    rows = client.get("/api/flo-future").json()["tables"]["designers"]["rows"]
    for r in rows:
        if r[0] != "TOTAL" and not str(r[0]).startswith("(") and prod_designs(client, r[0]) > 0:
            return r[0]
    pytest.skip("no designer on both pages in the demo data")


def test_ready_is_not_total_designs_and_follow_ups_keep_the_designer(chat, client):
    name = pick_designer(client)
    r1 = chat(f"{name} ke total designs kitne hain?")
    r2 = chat("Kitne ready hain?", r1["conversation_id"])
    ready = prod_designs(client, name, "DONE")
    total_orders = int(r1["answer"].split("**")[3].split()[0].replace(",", ""))
    assert r2["intent"] == "status" and f"{ready:,}" in r2["answer"] and "Ready designs" in r2["answer"]
    ff = ff_summary(client, name)
    assert f"{ff['items_done']:,}" in r2["answer"]
    r3 = chat("Aur kitne pending hain?", r1["conversation_id"])
    assert "Pending designs" in r3["answer"]
    assert f"{prod_designs(client, name) - ready:,}" in r3["answer"]
    r4 = chat("Completion percentage kitna hai?", r1["conversation_id"])
    if prod_designs(client, name):
        assert f"{ready / prod_designs(client, name) * 100:.2f}%" in r4["answer"]
    assert name.upper() in r4["answer"].upper()
    assert total_orders >= 0


def test_two_designers_compare_same_metric_then_difference(chat, client):
    rows = client.get("/api/flo-future").json()["tables"]["designers"]["rows"]
    a, b = [r[0] for r in rows if r[0] != "TOTAL" and not str(r[0]).startswith("(")][:2]
    r1 = chat(f"{a} aur {b} ka completion percentage batao.")
    cid = r1["conversation_id"]
    r2 = chat("Dono mein kiska performance better hai?", cid)
    r3 = chat("Kitne percentage points ka difference hai?", cid)
    for r in (r1, r2, r3):
        assert "Approval" not in r["answer"] and "Samples" not in r["answer"]
        assert "Completion %" in r["answer"]
    pa = [x for x in rows if x[0] == a][0][6]
    pb = [x for x in rows if x[0] == b][0][6]
    assert f"{abs(pa - pb):.2f} percentage points" in r3["answer"] or pa == pb


def test_pages_side_by_side_and_second_designer(chat, client):
    name = pick_designer(client)
    r1 = chat(f"Production mein {name} ke kitne designs pending hain?")
    p_pend = prod_designs(client, name) - prod_designs(client, name, "DONE")
    assert f"{p_pend:,}" in r1["answer"] and "FLO Future" not in r1["answer"].split("How designs")[0]
    r2 = chat(f"FLO Future mein {name} ke kitne designs pending hain?", r1["conversation_id"])
    assert "Production" not in r2["answer"].split("How designs")[0]
    r3 = chat("Dono pages ka data alag-alag dikhao.", r1["conversation_id"])
    assert "| Metric | Production | FLO Future |" in r3["answer"] and "Pending designs" in r3["answer"]
    assert f"{kpi(client, '/api/production', 'Pending', designer=name.upper()):,.0f} pcs" in r3["answer"]
    assert f"{kpi(client, '/api/flo-future', 'Pending', designer=name):,.0f} pcs" in r3["answer"]
    rows = client.get("/api/flo-future").json()["tables"]["designers"]["rows"]
    other = next(r[0] for r in rows if r[0] not in ("TOTAL", name) and not str(r[0]).startswith("("))
    r4 = chat(f"{other} ka bhi dono pages par comparison karo.", r1["conversation_id"])
    assert "| Metric | Production | FLO Future |" in r4["answer"] and other.upper() in r4["answer"].upper()
    assert f"{kpi(client, '/api/flo-future', 'Pending', designer=other):,.0f} pcs" in r4["answer"]


def two_on_both(client):
    rows = client.get("/api/flo-future").json()["tables"]["designers"]["rows"]
    names = [r[0] for r in rows if r[0] != "TOTAL" and not str(r[0]).startswith("(") and prod_designs(client, r[0]) > 0]
    if len(names) < 3:
        pytest.skip("need three designers on both pages")
    return names[:3]


def cells(answer, row):
    """The cells of one table row ('| Ready designs | 49 designs | 0 designs |') -> ['49 designs', '0 designs']."""
    for line in answer.splitlines():
        if line.startswith(f"| {row} |"):
            return [c.strip() for c in line.strip("|").split("|")[1:]]
    return []


def test_ready_designs_comparison_uses_ready_not_total(chat, client):
    a, b = two_on_both(client)[:2]
    for q in (f"{a} aur {b} mein kiske zyada designs ready hain?", f"Which has more ready designs, {a} or {b}?"):
        r = chat(q)
        assert r["intent"] == "status"
        ready = [f"{prod_designs(client, x, 'DONE'):,} design" for x in (a, b)]
        assert [c.split("s")[0] for c in cells(r["answer"], "Ready designs")][:2] == [x for x in ready][:2] or \
            all(x in r["answer"] for x in ready)
        ffa, ffb = ff_summary(client, a)["items_done"], ff_summary(client, b)["items_done"]
        assert f"{ffa:,} design" in r["answer"] and f"{ffb:,} design" in r["answer"]
        assert "Ready designs:" in r["answer"] or "same" in r["answer"]
        assert "Total designs" in r["answer"]


def test_pending_quantity_compare_after_two_single_questions(chat, client):
    a, b = two_on_both(client)[:2]
    r1 = chat(f"{a} ke kitne designs pending hain?")
    cid = r1["conversation_id"]
    chat(f"{b} ke kitne designs pending hain?", cid)
    r3 = chat("Dono ka pending quantity compare karo.", cid)
    assert r3["intent"] == "status" and a.upper() in r3["answer"].upper() and b.upper() in r3["answer"].upper()
    assert "| Metric | " in r3["answer"]
    assert pcs(kpi(client, "/api/flo-future", "Pending", designer=a)) in r3["answer"]
    assert pcs(kpi(client, "/api/flo-future", "Pending", designer=b)) in r3["answer"]
    assert pcs(kpi(client, "/api/production", "Pending", designer=a.upper())) in r3["answer"]
    every = kpi(client, "/api/production", "Pending")
    assert pcs(every) not in r3["answer"] or every in (kpi(client, "/api/production", "Pending", designer=a.upper()),)


def test_completion_conversation_keeps_metric_page_and_names(chat, client):
    a, b, c = two_on_both(client)
    r1 = chat(f"{a} ka completion percentage kitna hai?")
    cid = r1["conversation_id"]
    r2 = chat(f"Ab {b} ka bhi batao.", cid)
    assert b.upper() in r2["answer"].upper() and "Completion %" in r2["answer"]
    r3 = chat("Dono mein kaun better perform kar raha hai?", cid)
    r4 = chat("Kitne percentage points ka difference hai?", cid)
    r5 = chat(f"Ab {c} ke saath compare karo.", cid)
    ff = {x[0]: x[6] for x in client.get("/api/flo-future").json()["tables"]["designers"]["rows"]}
    for r, names in ((r3, (a, b)), (r4, (a, b)), (r5, (a, b, c))):
        assert r["intent"] == "status"
        assert "Approval" not in r["answer"] and "approval" not in r["answer"] and "Samples" not in r["answer"]
        for n in names:
            assert n.upper() in r["answer"].upper()
            assert f"{ff[n]:.2f}%" in r["answer"]
    hi, lo = sorted((ff[a], ff[b]))[::-1]
    if hi != lo:
        assert f"{hi - lo:.2f} percentage points" in r4["answer"]
    assert "highest" in r5["answer"] or "same" in r5["answer"]


def test_flo_future_item_categories_add_up_to_the_dashboard_items(chat, client):
    rows = client.get("/api/flo-future").json()["tables"]["designers"]["rows"]
    name = next(r[0] for r in rows if r[0] != "TOTAL" and not str(r[0]).startswith("(") and r[2])
    r = chat(f"FLO Future mein {name} ke kitne designs pending hain?")
    s = ff_summary(client, name)
    assert f"Total promised items: {s['items']:,}" in r["answer"]
    assert f"Items marked done: {s['items_done']:,}" in r["answer"]
    assert "Items with pcs still remaining:" in r["answer"] and "zero remaining pcs but not marked done" in r["answer"]


def test_completion_percent_basis_is_explained(chat, client):
    name = two_on_both(client)[0]
    r = chat(f"FLO Future mein {name} ka completion percentage kitna hai?")
    s = ff_summary(client, name)
    assert f"{s['done_pct']:.2f}%" in r["answer"]
    if s["items"]:
        assert f"{s['items_done'] / s['items'] * 100:.2f}%" in r["answer"] and "differ" in r["answer"]


def month_orders(client, month):
    rows = client.get("/api/designer", params={"month": month}).json()["tables"]["designers"]
    cols = [c["label"] for c in rows["columns"]]
    return sum(r[cols.index("Design Count")] for r in rows["rows"] if r[0] != "TOTAL")


def test_month_difference_decrease_and_previous_month(chat, client):
    months = client.get("/api/designer").json()["options"]["month"]
    if len(months) < 3:
        pytest.skip("need three months")
    m1, m2, m3 = months[:3]
    v1, v2, v3 = (month_orders(client, m) for m in (m1, m2, m3))
    short = lambda m: m.split("-")[0]
    r1 = chat(f"Total orders in {short(m1)}, {short(m2)} and {short(m3)}")
    cid = r1["conversation_id"]
    r2 = chat(f"{short(m1)} se {short(m3)} tak kitna difference aaya?", cid)
    assert f"{abs(v3 - v1):,}" in r2["answer"] or v3 == v1
    r3 = chat(f"{short(m2)} se {short(m3)} mein kitna decrease hua?", cid)
    assert f"{abs(v3 - v2):,}" in r3["answer"] or v3 == v2
    r4 = chat("Pichhle month ke comparison mein kitna increase hua?", cid)
    assert m1 in r4["answer"] and m2 in r4["answer"] and m3 not in r4["answer"].split("Note:")[0]
    assert f"{abs(v2 - v1):,}" in r4["answer"] or v2 == v1


def test_cold_month_difference_names_its_assumption(chat, client):
    months = client.get("/api/designer").json()["options"]["month"]
    if len(months) < 2:
        pytest.skip("need two months")
    r = chat(f"{months[0].split('-')[0]} se {months[1].split('-')[0]} tak kitna difference aaya?")
    assert "didn't name a figure" in r["answer"] and "Received" not in r["answer"]
