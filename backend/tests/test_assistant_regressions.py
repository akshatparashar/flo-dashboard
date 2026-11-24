"""Regression tests for the real-data testing round: every expected figure is read from the page APIs (demo data)."""
from __future__ import annotations

import re

import pytest

from app.assistant import fmt
from test_assistant_calc import client  # noqa: F401  (fixture)


def chat(client, message, conv=None):
    r = client.post("/api/chat", json={"message": message, "conversation_id": conv})
    assert r.status_code == 200, r.text
    return r.json()


def ios(client, **params):
    return client.get("/api/in-out-sale", params=params).json()


def fab_rows(body):
    t = body["tables"]["fabricators"]
    cols = [c["label"] for c in t["columns"]]
    return cols, [r for r in t["rows"] if r[0] != "TOTAL"]


# ---------------------------------------------------------------------------------------------------- A. In/Out Sale
def test_in_house_vs_outsource_sale_pcs_does_not_answer_with_incoming(client):
    for q in ("Compare In-house and Outsource sale pcs", "In-house vs outsource sale kitna hai?"):
        r = chat(client, q)
        assert r["page"] == "/in-out-sale"
        assert "does not split" in r["answer"] and "Incoming pcs: In-house vs Outsource" not in r["answer"]
        sale = next(k["value"] for k in ios(client)["kpis"] if k["label"] == "Sale pcs")
        assert f"{sale:,.0f} pcs" in r["answer"]


def test_in_house_vs_outsource_incoming_uses_the_type_filter(client):
    want = {}
    for typ in ("In-house", "Outsource"):
        cols, rows = fab_rows(ios(client, type=typ))
        want[typ] = sum(r[cols.index("Total")] for r in rows)
    r = chat(client, "In-house vs outsource incoming kitna hai?")
    assert f"{want['In-house']:,.0f}" in r["answer"] and f"{want['Outsource']:,.0f}" in r["answer"]


def test_fabricator_share_uses_all_fabricators_as_the_denominator(client):
    cols, rows = fab_rows(ios(client))
    top = max(rows, key=lambda r: r[cols.index("Total")])
    grand = sum(r[cols.index("Total")] for r in rows)
    r = chat(client, f"What is {top[0]}'s share of incoming?")
    share = top[cols.index("Total")] / grand * 100
    assert f"{share:.1f}%" in r["answer"] and "100.0%" not in r["answer"]
    assert f"{grand:,.0f}" in r["answer"]


def test_two_incoming_totals_are_explained_not_hidden(client):
    body = ios(client)
    kpi = next(k["value"] for k in body["kpis"] if k["label"] == "Incoming pcs")
    cols, rows = fab_rows(body)
    fab_total = sum(r[cols.index("Total")] for r in rows)
    r = chat(client, "What is the total incoming pcs?")
    assert f"{kpi:,.0f} pcs" in r["answer"]
    if abs(kpi - fab_total) > 0.5:
        assert f"{fab_total:,.0f}" in r["answer"] and "month table" in r["answer"]
    else:
        assert "month table" not in r["answer"]


def test_fabricator_and_month_filters_together(client):
    months = ios(client)["options"]["month"]
    cols, rows = fab_rows(ios(client, month=months[0]))
    if not rows:
        pytest.skip("no fabricator rows for that month")
    name = rows[0][0]
    r = chat(client, f"Show incoming pcs of {name} in {months[0].split('-')[0]}")
    assert f"{rows[0][cols.index('Total')]:,.0f} pcs" in r["answer"] and months[0] in r["answer"]


# ---------------------------------------------------------------------------------------------------- B. Designers
def repeat_table(client):
    t = client.get("/api/designer", params={"order_type": "REPEAT"}).json()["tables"]["designers"]
    cols = [c["label"] for c in t["columns"]]
    rows = [r for r in t["rows"] if r[0] != "TOTAL" and r[cols.index("Design Count")]]
    return sorted(rows, key=lambda r: (-r[cols.index("Design Count")], -r[cols.index("Total Volume (Pcs)")]))


def test_top_five_by_repeat_orders_even_after_comparing_two_designers(client):
    rows = repeat_table(client)
    names = [x[0] for x in client.get("/api/designer").json()["tables"]["designers"]["rows"] if x[0] != "TOTAL"]
    first = chat(client, f"Compare {names[0]} and {names[1]}")
    for q, n in (("Show top 5 designers by repeat orders", 5), ("top 3 designers by repeat orders", 3)):
        r = chat(client, q, first["conversation_id"])
        listed = re.findall(r"^\d+\. ", r["answer"], re.M)
        assert len(listed) == min(n, len(rows)), r["answer"]
        assert all(x[0] in r["answer"] for x in rows[:min(n, len(rows))])


def test_compare_her_with_keeps_the_designer_and_the_metric(client):
    rows = repeat_table(client)
    if len(rows) < 2:
        pytest.skip("need two designers with repeat orders")
    a, b = rows[0][0], rows[1][0]
    r1 = chat(client, f"How many repeat orders does {a.title()} have?")
    r2 = chat(client, f"Compare her with {b.title()}", r1["conversation_id"])
    assert a in r2["answer"] and b in r2["answer"] and "Repeat" in r2["answer"]


def test_numbers_given_by_the_person_are_used(client):
    r = chat(client, "If Deepika has 120 orders and Keerti has 90, what is the difference in percentage?")
    assert "33.33% more" in r["answer"] and "25.00% less" in r["answer"] and "30 orders" in r["answer"]
    r = chat(client, "Deepika ke 355 orders hain aur Keerti ke 353, kitna percent zyada?")
    assert "0.57% more" in r["answer"] and "numbers from your message" in r["answer"]
    r = chat(client, "Sales were 40 lakh in September and 50 lakh in October, what is the growth?")
    assert "25.00%" in r["answer"]
    r = chat(client, "What is 54338 minus 50580?")             # plain arithmetic is unchanged
    assert "3,758" in r["answer"]


# ---------------------------------------------------------------------------------------------------- C. Deliveries
def test_delivery_month_question_uses_expected_deliveries(client):
    d = client.get("/api/client").json().get("delivery60")
    if not d:
        pytest.skip("no delivery data")
    rows = [r for r in d["tables"]["months"]["rows"] if r[0] != "TOTAL"]
    m = rows[-1]
    for q in (f"{m[0].split('-')[0]} mein kitne pcs deliver hone hain?",
              f"How many pcs are due for delivery in {m[0].split('-')[0]}?"):
        r = chat(client, q)
        assert r["page"] == "/clients" and f"{m[2]:,.0f}" in r["answer"] and m[0] in r["answer"]
        assert "What the pending figures mean" in r["answer"]


def test_on_time_delivery_is_still_production(client):
    r = chat(client, "What is the on-time delivery in production?")
    assert r["page"] == "/production"


# ---------------------------------------------------------------------------------------------------- D. Target
def target_designers(client):
    t = client.get("/api/target").json()["filtered"]["tables"]["designers"]
    cols = [c["label"] for c in t["columns"]]
    rows = [r for r in t["rows"] if r[0] not in ("TOTAL", "(NOT ASSIGNED)")]
    return sorted(rows, key=lambda r: -r[cols.index("New Revenue")])


@pytest.mark.parametrize("question,low", [("Who achieved the highest target percentage?", False),
                                          ("Which designer has the lowest target achievement?", True),
                                          ("Kis designer ka target achievement sabse kam hai?", True)])
def test_designer_target_questions_use_the_target_page(client, question, low):
    rows = target_designers(client)
    r = chat(client, question)
    assert r["page"] == "/target" and "no target per designer" in r["answer"]
    pick = rows[-1] if low else rows[0]
    assert f"**{pick[0]}**" in r["answer"]
    assert "Done %" not in r["answer"].split("FLO Future")[0]


# ---------------------------------------------------------------------------------------------------- E. Fabric PO
def test_fabric_po_pending_pcs_says_the_unit_is_metres(client):
    for q in ("How many pcs are pending in Fabric PO?", "Fabric PO pending pcs?"):
        r = chat(client, q)
        assert r["page"] == "/fabric-po" and "does not record **pending pcs**" in r["answer"] and "mtr" in r["answer"]
    r = chat(client, "Fabric PO mein kitna pending hai?")          # no unit asked: metres, as before
    assert "mtr" in r["answer"] and "pending pcs" not in r["answer"]


# ---------------------------------------------------------------------------------------------------- retest round
def test_fabricator_share_question_with_two_clauses_is_answered_once(client):
    cols, rows = fab_rows(ios(client))
    top = max(rows, key=lambda r: r[cols.index("Total")])
    grand = sum(r[cols.index("Total")] for r in rows)
    r = chat(client, f"Who has the highest incoming pcs at {top[0]}, and what percentage of total incoming is it?")
    assert r["intent"] != "multi" and f"{top[cols.index('Total')] / grand * 100:.1f}%" in r["answer"]


def test_from_to_numbers_are_before_and_after(client):
    r = chat(client, "If sale pcs increased from 100,000 to 150,000, what is the percentage increase?")
    assert "50.00%" in r["answer"] and "Before 100,000" in r["answer"] and "After 150,000" in r["answer"]
    assert "the dashboard shows" not in r["answer"]            # "before"/"after" are not dashboard rows to check


def test_fw_orders_compare_is_one_answer_with_all_three_totals(client):
    fw = client.get("/api/client").json().get("fw_orders")
    if not fw:
        pytest.skip("no FW ORDER'S in the demo data")
    t = fw["totals"]
    r = chat(client, "Compare FW Orders order, dispatched and pending quantities.")
    assert r["intent"] != "multi"
    for k in ("order", "dispatched", "pending"):
        assert f"{t[k]:,.0f}" in r["answer"]
    if t["order"]:
        assert f"{t['dispatched'] / t['order'] * 100:.1f}% of" in r["answer"]


def test_production_month_question_explains_order_month(client):
    rows = client.get("/api/production").json()["options"]
    names = [x[0] for x in client.get("/api/designer").json()["tables"]["designers"]["rows"] if x[0] != "TOTAL"]
    name = next(n for n in names if n in rows["designer"])
    month = rows["month"][0]
    r = chat(client, f"How many designs did {name.title()} complete in {month.split('-')[0]}?")
    assert r["intent"] == "status" and "order's month" in r["answer"]
    done = [s for s in rows["status"] if s.upper() in ("DONE", "COMPLETED", "COMPLETE")]
    want = next(k["value"] for k in client.get("/api/production", params={"designer": name, "month": month,
                                                                           "status": done}).json()["kpis"]
                if k["label"].startswith("Designs in production"))
    assert f"Ready designs: **{want:,.0f} design" in r["answer"]
