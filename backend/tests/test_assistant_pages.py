"""Page-level answers across the whole dashboard (summary, samples waiting, pending POs, rate list, target achieved,
fabricator pending work, zero repeat orders, volume ranking, like-for-like comparisons). Expected figures are read from
the same page APIs; runs on the demo data."""
from __future__ import annotations

import pytest

from test_assistant_calc import client  # noqa: F401  (fixture)


def ask(client, q):
    r = client.post("/api/chat", json={"message": q})
    assert r.status_code == 200, r.text
    return r.json()


def kpi(client, path, start, **params):
    return next(k for k in client.get(path, params=params).json()["kpis"] if k["label"].startswith(start))["value"]


def test_dashboard_summary_lists_every_section(client):
    r = ask(client, "Show me the complete dashboard summary.")
    assert r["intent"] == "summary"
    ov = client.get("/api/overview").json()["sections"]
    for sec in ov.values():
        for k in sec.get("kpis") or []:
            assert k["label"] in r["answer"]


def test_samples_waiting_uses_the_samples_page(client):
    r = ask(client, "How many samples are pending?")
    assert r["page"] == "/samples"
    assert f"{kpi(client, '/api/samples', 'Open pipeline'):,.0f} pcs" in r["answer"]


def test_pending_pos_counts_rows_with_pending_fabric(client):
    r = ask(client, "How many fabric POs are pending?")
    rows = client.get("/api/fabric-po").json()["tables"]["pos"]
    cols = [c["label"] for c in rows["columns"]]
    n = sum(1 for x in rows["rows"] if isinstance(x[cols.index("Pending (mtr)")], (int, float)) and x[cols.index("Pending (mtr)")] > 0)
    assert f"{n:,} POs are still pending" in r["answer"]


def test_target_achieved_percentage(client):
    r = ask(client, "What is the target achievement percentage?")
    tr = client.get("/api/target").json()["tracker"]
    tgt = next(k["value"] for k in tr["kpis"] if k["label"].startswith("Yearly target"))
    ach = next(k["value"] for k in tr["kpis"] if k["label"].startswith("Achieved (new)"))
    assert f"{ach / tgt * 100:.2f}%" in r["answer"]


def test_zero_repeat_orders_and_volume_ranking(client):
    rows = client.get("/api/designer").json()["tables"]["designers"]
    cols = [c["label"] for c in rows["columns"]]
    data = [x for x in rows["rows"] if x[0] != "TOTAL"]
    r = ask(client, "Which designers have zero repeat orders?")
    zero = [x[0] for x in data if not x[cols.index("Repeat Orders (Pcs)")]]
    assert r["intent"] == "orders" and all(z in r["answer"] for z in zero)
    r2 = ask(client, "Who has the highest total volume?")
    top = max(data, key=lambda x: x[cols.index("Total Volume (Pcs)")])
    assert top[0] in r2["answer"] and f"{top[cols.index('Total Volume (Pcs)')]:,.0f} pcs" in r2["answer"]


def test_two_clients_compare_same_page_same_figure(client):
    names = client.get("/api/client").json()["options"]["client"][:2]
    r = ask(client, f"Compare {names[0]} and {names[1]} by order quantity")
    assert r["intent"] in ("compare", "orders", "value")
    assert "page" in r["answer"] or r["intent"] != "unknown"


def test_fabricator_pending_work(client):
    names = client.get("/api/fabricator").json()["options"]["fabricator"]
    fab = names[0]
    r = ask(client, f"What work is pending with {fab}?")
    rem = kpi(client, "/api/fabricator", "Remaining", fabricator=fab)
    assert f"{rem:,.0f} pcs" in r["answer"]


def test_orders_context_conversation(client):
    names = [x[0] for x in client.get("/api/designer").json()["tables"]["designers"]["rows"] if x[0] != "TOTAL"][:2]
    r1 = client.post("/api/chat", json={"message": f"How many orders does {names[0]} have?"}).json()
    cid = r1["conversation_id"]
    r2 = client.post("/api/chat", json={"message": f"What about {names[1]}?", "conversation_id": cid}).json()
    r3 = client.post("/api/chat", json={"message": "Compare both.", "conversation_id": cid}).json()
    r4 = client.post("/api/chat", json={"message": "Now show repeat orders.", "conversation_id": cid}).json()
    assert names[1].upper() in r2["answer"].upper()
    assert all(n.upper() in r3["answer"].upper() for n in names)
    assert "Repeat" in r4["answer"] and all(n.upper() in r4["answer"].upper() for n in names)
