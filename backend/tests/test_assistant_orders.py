"""FLO Assistant order questions per designer ("customer"): counts, new vs repeat, rankings, comparisons, month change
and follow-ups. Expected figures are read from the Designers page API inside each test (no hardcoded names or numbers).
Runs on the built-in demo data."""
from __future__ import annotations

import pytest

from test_assistant_calc import ask, client, make_assistant  # noqa: F401  (fixtures)


def designer_table(client, **params):
    body = client.get("/api/designer", params=params).json()
    t = body["tables"]["designers"]
    cols = [c["label"] for c in t["columns"]]
    rows = {r[0]: dict(zip(cols, r)) for r in t["rows"]}
    return rows


def busy_designer(client, order_type=None):
    rows = designer_table(client, **({"order_type": order_type} if order_type else {}))
    rows.pop("TOTAL")
    name = max(rows, key=lambda k: rows[k]["Design Count"])
    return name, rows


def fy_months(client):
    return client.get("/api/designer").json()["options"]["month"]


def test_designer_orders_total_new_and_repeat(client):
    name, rows = busy_designer(client)
    new = designer_table(client, designer=name, order_type="NEW")[name]["Design Count"]
    rep = designer_table(client, designer=name, order_type="REPEAT")[name]["Design Count"]
    r = ask(client, f"How many orders does {name.title()} have?")
    assert r["intent"] == "orders"
    assert f"**{rows[name]['Design Count']:,} orders**" in r["answer"]
    assert f"{new:,}" in r["answer"] and f"{rep:,}" in r["answer"]
    r = ask(client, f"how many repeat orders does {name} have")
    assert f"{rep:,} repeat order" in r["answer"]
    r = ask(client, f"how many new orders does {name} have")
    assert f"{new:,} new order" in r["answer"]


def test_repeat_total_and_percentage(client):
    rows = designer_table(client)
    rep = designer_table(client, order_type="REPEAT")["TOTAL"]["Design Count"]
    total = rows["TOTAL"]["Design Count"]
    assert f"{rep:,} repeat orders" in ask(client, "What is the total number of repeat orders?")["answer"]
    assert f"{rep / total * 100:.2f}%" in ask(client, "What percentage of total orders are repeat orders?")["answer"]


def test_highest_repeat_customer(client):
    name, rows = busy_designer(client, "REPEAT")
    r = ask(client, "Which customer has the highest number of repeat orders?")
    assert f"**{name}**" in r["answer"] and f"**{rows[name]['Design Count']:,}**" in r["answer"]


def test_customer_wise_table_lists_every_designer_and_total(client):
    rows = designer_table(client)
    r = ask(client, "Compare customer-wise orders")
    for name, v in rows.items():
        if name != "TOTAL" and v["Design Count"]:
            assert f"{name}: {v['Design Count']:,} order" in r["answer"]
    assert f"Total: {rows['TOTAL']['Design Count']:,} orders" in r["answer"]


def test_compare_two_designers(client):
    name, rows = busy_designer(client)
    other = next(k for k in sorted(rows, key=lambda k: -rows[k]["Design Count"]) if k != name and rows[k]["Design Count"])
    r = ask(client, f"Compare {name} and {other} orders")
    diff = rows[name]["Design Count"] - rows[other]["Design Count"]
    assert f"**{name}** has **{diff:,} more**" in r["answer"]


def test_two_month_change_with_formula_and_follow_ups(client):
    months = fy_months(client)
    name = next(n for n in busy_designer(client)[1] if True)
    pairs = [(a, b) for a, b in zip(months, months[1:])
             if designer_table(client, month=a, designer=name)[name]["Design Count"]
             and designer_table(client, month=b, designer=name)[name]["Design Count"]
             != designer_table(client, month=a, designer=name)[name]["Design Count"]]
    a, b = pairs[0]
    x = designer_table(client, month=a, designer=name)[name]["Design Count"]
    y = designer_table(client, month=b, designer=name)[name]["Design Count"]
    r1 = ask(client, f"How many designs did {name} have in {a}?")
    assert f"**{x:,} design" in r1["answer"]
    r2 = ask(client, f"And {b}?", r1["context"])
    assert f"**{y:,} design" in r2["answer"] and name in r2["answer"]
    r3 = ask(client, "How much decrease?" if y < x else "how much increase?", r2["context"])
    assert f"{abs(y - x):,}" in r3["answer"] and f"{abs((y - x) / x * 100):.2f}%" in r3["answer"]
    assert f"{abs(y - x):,} ÷ {x:,} × 100" in r3["answer"]
    r4 = ask(client, "What is the percentage change?", r3["context"])
    assert f"{abs((y - x) / x * 100):.2f}%" in r4["answer"]


def test_stated_numbers_are_checked_against_dashboard(client):
    months = fy_months(client)
    name = busy_designer(client)[0]
    r = ask(client, f"Total designs for {name} in {months[0]} is 999999 and {months[1]} is 5. How much decrease?")
    assert "you mentioned 999,999 and 5" in r["answer"]


def test_hinglish(client):
    name, rows = busy_designer(client)
    r = ask(client, f"{name.title()} ke kitne order hai?")
    assert f"**{rows[name]['Design Count']:,} orders**" in r["answer"]
    rep = designer_table(client, order_type="REPEAT")["TOTAL"]["Design Count"]
    assert f"{rep:,}" in ask(client, "Repeat order kitne hain?")["answer"]


def test_details_include_new_repeat_and_categories(client):
    name = busy_designer(client)[0]
    r = ask(client, f"Show {name.title()}'s order details")
    assert "Order details for" in r["answer"] and "New orders:" in r["answer"] and "Pcs by category" in r["answer"]


def test_other_orders_questions_still_use_other_pages(client):
    r = ask(client, "pending fabric po orders")
    assert r["intent"] != "orders"
