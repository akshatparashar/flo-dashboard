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


# ---- period selection: "this year" / FY / year to date mean every available month, a named month stays narrow --------
def short(m):
    return m.split("-")[0]


def all_year(client):
    body = client.get("/api/in-out-sale").json()
    rows = [r for r in body["tables"]["compare"]["rows"] if r[0] != "TOTAL"]
    return body, rows


def pct(a, b):
    return f"{(a - b) / b * 100:+.1f}%"


@pytest.mark.parametrize("question", [
    "Compare this year's net sale with last year.",
    "Compare FY 2026-27 net sale with last year",
    "Net sale year to date vs last year",
    "Compare net sale with last year for all months",
    "Is saal ka net sale pichhle saal se compare karo",
])
def test_whole_year_comparison_uses_every_month_even_after_a_month_was_discussed(client, question):
    body, rows = all_year(client)
    months = [r[0] for r in rows]
    net = next(k["value"] for k in body["kpis"] if k["label"] == "Net sale")
    this_net, last_net = sum(r[4] for r in rows), sum(r[5] for r in rows)
    from app.assistant import fmt
    for first in (None, f"Net sale in {short(months[-1])}?"):
        conv = chat(client, first)["conversation_id"] if first else None
        r = chat(client, question, conv)
        assert r["page"] == "/in-out-sale"
        assert all(m in r["answer"] for m in months), "every available month is in the comparison"
        assert fmt.inr_short(net) in r["answer"] and "all available months" in r["answer"]
        if last_net:
            assert pct(this_net, last_net) in r["answer"]


def test_whole_year_growth_matches_the_dashboard_kpi_hint(client):
    body, _ = all_year(client)
    k = {x["label"]: x for x in body["kpis"]}
    r = chat(client, "Compare this year's sale amount with last year.")
    assert k["Sale amount"]["hint"].split(" vs")[0] in r["answer"]            # e.g. "▲ 66.0%"
    r = chat(client, "Compare this year's net sale with last year.")
    assert k["Net sale"]["hint"].split(" vs")[0] in r["answer"]


def test_selected_months_stay_narrow(client):
    _, rows = all_year(client)
    if len(rows) < 3:
        pytest.skip("need three months")
    m1, m2 = rows[-2][0], rows[-1][0]
    r = chat(client, f"Compare net sale with last year for {short(m1)} and {short(m2)}")
    this_net, last_net = sum(x[4] for x in rows[-2:]), sum(x[5] for x in rows[-2:])
    assert m1 in r["answer"] and m2 in r["answer"] and rows[0][0] not in r["answer"]
    assert pct(this_net, last_net) in r["answer"]
    one = chat(client, f"Compare {short(m2)} net sale with last year")
    assert rows[-1][0] in one["answer"] and rows[0][0] not in one["answer"]


def test_bare_follow_up_keeps_the_month_but_a_year_word_widens_it(client):
    _, rows = all_year(client)
    m = rows[-1][0]
    a = chat(client, f"Net sale in {short(m)}?")
    keep = chat(client, "Compare with last year", a["conversation_id"])
    assert m in keep["answer"] and rows[0][0] not in keep["answer"]
    wide = chat(client, "Net sale this year?", a["conversation_id"])
    from app.assistant import fmt
    net = next(k["value"] for k in client.get("/api/in-out-sale").json()["kpis"] if k["label"] == "Net sale")
    assert fmt.inr_short(net) in wide["answer"]


def test_this_year_resets_the_period_on_other_pages_too(client):
    first = chat(client, "How many orders in October?")
    r = chat(client, "And this year?", first["conversation_id"])
    total = next(k["value"] for k in client.get("/api/designer").json()["kpis"] if k["label"] == "Total designs")
    assert r["page"] == "/designers" and f"{total:,.0f} orders" in r["answer"]
    first = chat(client, "Revenue in October?")
    r = chat(client, "What about this year?", first["conversation_id"])
    rev = next(k for k in client.get("/api/target").json()["filtered"]["kpis"] if k["label"] == "Total revenue")
    from app.assistant import fmt
    assert fmt.inr_short(rev["value"]) in r["answer"]
