"""In/Out Sale page (11th page) through the chatbot. Expected figures are read from /api/in-out-sale on the demo data."""
from __future__ import annotations

import pytest

from test_assistant_calc import client  # noqa: F401  (fixture)


def chat(client, message, conv=None):
    r = client.post("/api/chat", json={"message": message, "conversation_id": conv})
    assert r.status_code == 200, r.text
    return r.json()


def kpi(client, label, **params):
    return next(k["value"] for k in client.get("/api/in-out-sale", params=params).json()["kpis"] if k["label"] == label)


def months(client):
    return client.get("/api/in-out-sale").json()["options"]["month"]


def test_page_is_registered_and_old_names_still_work(client):
    from app.assistant.pages import PAGES
    assert PAGES["in-out-sale"].path == "/in-out-sale" and PAGES["in-out-sale"].label == "In/Out Sale"
    assert PAGES["target"].label == "Designer Order Target" and "target page" in PAGES["target"].words
    assert PAGES["client"].label == "Clients Order Status" and "clients page" in PAGES["client"].words
    r = chat(client, "What is the target & revenue page?")
    assert r["page"] == "/target"


def test_sale_figures_match_the_api(client):
    r = chat(client, "How many sale pcs this year?")
    assert r["page"] == "/in-out-sale" and f"{kpi(client, 'Sale pcs'):,.0f} pcs" in r["answer"]
    m = months(client)[0]
    r = chat(client, f"Net sale in {m.split('-')[0]}?")
    from app.assistant import fmt
    assert fmt.inr_short(kpi(client, "Net sale", month=m)) in r["answer"]


def test_year_on_year_comparison_uses_the_dashboard_table(client):
    body = client.get("/api/in-out-sale").json()
    cols = [c["label"] for c in body["tables"]["compare"]["columns"]]
    rows = [r for r in body["tables"]["compare"]["rows"] if r[0] != "TOTAL"]
    this_total, last_total = sum(r[1] for r in rows), sum(r[2] for r in rows)
    r = chat(client, "Compare sale pcs with last year")
    assert f"{this_total:,.0f}" in r["answer"] and f"{last_total:,.0f}" in r["answer"]
    if last_total:
        assert f"{(this_total - last_total) / last_total * 100:+.1f}%" in r["answer"]
    assert cols[1].split()[-1] in r["answer"]


def test_best_month_and_follow_ups_keep_the_figure(client):
    rows = [r for r in client.get("/api/in-out-sale").json()["tables"]["flow"]["rows"] if r[0] != "TOTAL"]
    best = max(rows, key=lambda r: r[6])           # Net sale column
    r1 = chat(client, "Which month has the highest net sale?")
    assert best[0] in r1["answer"]
    m1, m2 = months(client)[:2]
    a = chat(client, f"How many sale pcs in {m1.split('-')[0]}?")
    b = chat(client, f"What about {m2.split('-')[0]}?", a["conversation_id"])
    assert f"{kpi(client, 'Sale pcs', month=m2):,.0f}" in b["answer"] and b["page"] == "/in-out-sale"
    c = chat(client, "Compare with last year.", a["conversation_id"])
    assert "vs" in c["answer"] and m2.split("-")[0] in c["answer"]


def test_fabricator_incoming_and_in_house_vs_outsource(client):
    body = client.get("/api/in-out-sale").json()
    t = body["tables"]["fabricators"]
    cols = [c["label"] for c in t["columns"]]
    rows = [r for r in t["rows"] if r[0] != "TOTAL"]
    top = max(rows, key=lambda r: r[cols.index("Total")])
    r = chat(client, "Which fabricator has the highest incoming pcs?")
    assert top[0] in r["answer"] and f"{top[cols.index('Total')]:,.0f} pcs" in r["answer"]
    ih = sum(x[cols.index("Total")] for x in rows if x[1] == "In-house")
    r2 = chat(client, "In-house vs outsource incoming kitna hai?")
    assert f"{ih:,.0f}" in r2["answer"]


def test_promised_vs_incoming(client):
    rows = client.get("/api/in-out-sale").json()["tables"]["promises"]["rows"]
    if not rows:
        pytest.skip("no promised pcs in the demo data")
    m = rows[0][0]
    r = chat(client, f"How many pcs were promised for {m.split('-')[0]} and how many came?")
    prom = sum(x[2] for x in rows if x[0] == m)
    assert r["page"] == "/in-out-sale" and f"{prom:,.0f}" in r["answer"]


def test_deducted_percentage_is_worked_out_from_the_page(client):
    rows = [r for r in client.get("/api/in-out-sale").json()["tables"]["flow"]["rows"] if r[0] != "TOTAL"]
    amt, net = sum(r[5] for r in rows), sum(r[6] for r in rows)
    r = chat(client, "What is the deducted percentage in net sale?")
    assert f"{(amt - net) / amt * 100:.2f}%" in r["answer"]
