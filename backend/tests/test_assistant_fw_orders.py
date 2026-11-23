"""Clients Order Status page through the chatbot: FW ORDER'S and expected deliveries (60-day delivery date)."""
from __future__ import annotations

import pytest

from test_assistant_calc import client  # noqa: F401  (fixture)


def chat(client, message, conv=None):
    r = client.post("/api/chat", json={"message": message, "conversation_id": conv})
    assert r.status_code == 200, r.text
    return r.json()


def test_fw_orders_table_and_totals_match_the_api(client):
    fw = client.get("/api/client").json().get("fw_orders")
    if not fw:
        pytest.skip("no FW ORDER'S in the demo data")
    r = chat(client, "Show FW orders month by month")
    t = fw["totals"]
    assert r["page"] == "/clients"
    assert f"{t['order']:,.0f}" in r["answer"] and f"{t['pending']:,.0f}" in r["answer"]
    assert f"{t['dispatched']:,.0f}" in r["answer"]


def test_fw_orders_for_one_month_and_no_raw_serial_months(client):
    fw = client.get("/api/client").json().get("fw_orders")
    if not fw:
        pytest.skip("no FW ORDER'S in the demo data")
    row = [r for r in fw["table"]["rows"] if str(r[0]).upper() != "TOTAL"][0]
    r = chat(client, "FW orders month by month")
    assert f"{row[1]:,.0f}" in r["answer"]
    import re
    assert not re.search(r"\| \d{5} \|", r["answer"])           # sheet serial dates are shown as month names


def test_expected_deliveries_overall_and_overdue(client):
    d = client.get("/api/client").json().get("delivery60")
    if not d:
        pytest.skip("no delivery data")
    k = {x["label"]: x for x in d["kpis"]}
    r = chat(client, "What are the expected deliveries by month?")
    assert f"{k['Pending']['value']:,.0f} pcs" in r["answer"]
    r2 = chat(client, "How much is overdue in expected deliveries?")
    assert f"{k['Overdue']['value']:,.0f} pcs" in r2["answer"]
    r3 = chat(client, "Overdue deliveries kitne hain?")
    assert f"{k['Overdue']['value']:,.0f} pcs" in r3["answer"]


def test_expected_deliveries_for_one_client_and_top_client(client):
    d = client.get("/api/client").json().get("delivery60")
    if not d:
        pytest.skip("no delivery data")
    rows = [r for r in d["tables"]["clients"]["rows"] if r[0] != "TOTAL"]
    top = max(rows, key=lambda r: r[3])
    r = chat(client, "Which client has the most overdue pcs?")
    assert top[0] in r["answer"] and f"{top[3]:,.0f} pcs" in r["answer"]
    one = rows[0][0]
    cd = client.get("/api/client", params={"client": one}).json()["delivery60"]
    r2 = chat(client, f"Expected deliveries for {one}")
    assert f"{cd['kpis'][0]['value']:,.0f} pcs" in r2["answer"]


def test_bare_overdue_still_means_production(client):
    r = chat(client, "Overdue pcs kitne hain?")
    prod = next(k["value"] for k in client.get("/api/production").json()["kpis"] if k["label"].startswith("Overdue pcs"))
    assert r["page"] == "/production" and f"{prod:,.0f} pcs" in r["answer"]
