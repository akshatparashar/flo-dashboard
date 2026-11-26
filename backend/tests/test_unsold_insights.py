"""Unsold Inventory Insights (the extra section of the Stock Ageing page). All rows here are made up, and every
expected figure is worked out by hand in the comments."""
import pytest

from app.dashboards import stock_ageing as sta
from tests.test_api import make_client

AS_ON = "2026-11-25"
# days before AS_ON: 10 -> 2026-11-15, 40 -> 2026-10-16, 100 -> 2026-08-17, 200 -> 2026-05-09, 400 -> 2025-10-21


def item(code, slot, pcs, rate, oi, ls=None, **extra):
    row = {"c": "1", "p": "x", "d": code, "n": code + " kurta", "b": pcs, "oi": oi, "li": oi, "wa": 1}
    row.update({k: 0 for k in sta.Q + sta.V})
    row[sta.Q[slot]], row[sta.V[slot]] = pcs, pcs * rate
    if ls:
        row.update({"ls": ls, "sa": 5, "s90": 2})
    row.update(extra)
    return row


ITEMS = [
    item("70- FRESH", 0, 10, 100, "2026-11-15"),                                    # never sold, waited 10 days
    item("70- SELLING", 5, 2, 100, "2025-10-21", ls="2026-11-15"),                  # old pieces, sold 10 days ago
    item("70- STUCK", 4, 5, 200, "2026-05-09", ls="2026-04-01", radj=3),            # in 200 days, no sale since
    item("70- DEAD", 5, 4, 500, "2025-10-21", rsr=1),                               # never sold, 400 days
    item("70- RESTOCKED", 0, 3, 300, "2026-11-15", ls="2025-01-01"),                # old sale, restocked 10 days ago
]
SNAP = {"as_on": AS_ON, "source": "t", "items": ITEMS, "has_sales": True, "control": {"qty": 24}}
# values: FRESH 1000, SELLING 200, STUCK 1000, DEAD 2000, RESTOCKED 900  -> 5100


def unsold(f=None, snap=SNAP):
    return sta.stock_ageing_dashboard(snap, f or {})["unsold"]


def rows(u):
    cols = [c["label"] for c in u["table"]["columns"]]
    return {r[0]: dict(zip(cols, r)) for r in u["table"]["rows"]}


def test_piece_age_cards_are_nested():
    cards = {c["days"]: c for c in unsold()["cards"]}
    # older than 30 days: SELLING 2 + STUCK 5 + DEAD 4 = 11 pcs, 3200
    assert (cards[30]["pcs"], cards[30]["value"], cards[30]["designs"]) == (11, 3200, 3)
    assert (cards[90]["pcs"], cards[180]["pcs"]) == (11, 11)
    assert (cards[365]["pcs"], cards[365]["value"]) == (6, 2200)                     # SELLING + DEAD
    assert cards[30]["pcs_pct"] == pytest.approx(11 / 24 * 100)


def test_no_sale_days_use_the_later_of_last_sale_and_arrival():
    r = rows(unsold())
    assert r["70- FRESH"]["Days without sale"] == 10
    assert r["70- SELLING"]["Days without sale"] == 10                               # its sale is what counts
    assert r["70- STUCK"]["Days without sale"] == 200                                # arrived after its last sale
    assert r["70- DEAD"]["Days without sale"] == 400
    assert r["70- RESTOCKED"]["Days without sale"] == 10                             # not 693: it was not in stock


def test_no_sale_cards_and_exclusive_bands():
    u = unsold()
    cards = {c["days"]: c["no_sale"] for c in u["cards"]}
    assert (cards[30]["designs"], cards[30]["pcs"], cards[30]["value"]) == (2, 9, 3000)     # STUCK + DEAD
    assert (cards[180]["designs"], cards[365]["designs"], cards[365]["value"]) == (2, 1, 2000)
    bands = {b["label"]: b for b in u["bands"]}
    assert bands["0-30 days"]["designs"] == 3 and bands["181-365 days"]["designs"] == 1
    assert bands["Over 365 days"]["designs"] == 1 and bands["31-90 days"]["designs"] == 0
    # each design is counted exactly once
    assert sum(b["designs"] for b in u["bands"]) == 5
    assert sum(b["pcs"] for b in u["bands"]) == 24 and sum(b["value"] for b in u["bands"]) == 5100
    assert [sum(col) for col in zip(*u["heat"]["values"])] == [b["pcs"] for b in u["bands"]]


def test_never_sold_and_lot_origin():
    u = unsold()
    assert (u["never"]["designs"], u["never"]["pcs"], u["never"]["value"]) == (2, 14, 3000)  # FRESH + DEAD
    assert u["dated_from"] == {"returns": 1.0, "adjustments": 3.0}
    assert rows(u)["70- DEAD"]["Last sale"] is None


def test_list_is_one_row_per_design_longest_waiting_first():
    u = unsold()
    names = [r[0] for r in u["table"]["rows"]]
    assert names[:2] == ["70- DEAD", "70- STUCK"] and len(names) == len(set(names)) == 5


def test_page_filters_apply():
    u = unsold({"q": ["stuck"]})
    assert u["totals"] == {"pcs": 5.0, "value": 1000.0, "designs": 1} and len(u["table"]["rows"]) == 1
    u = unsold({"age": ["0-30 days"]})
    assert u["totals"]["designs"] == 2 and all(c["pcs"] == 0 for c in u["cards"])


def test_without_sales_history_nothing_is_claimed_about_selling():
    old = {**SNAP, "has_sales": False,
           "items": [{k: v for k, v in i.items() if k not in ("ls", "sa", "s90", "rsr", "radj")} for i in ITEMS]}
    u = unsold(snap=old)
    assert u["has_sales"] is False and u["never"] is None and u["bands"] == [] and u["heat"] is None
    assert all(c["no_sale"] is None for c in u["cards"])
    cols = [c["label"] for c in u["table"]["columns"]]
    assert "Days without sale" not in cols and "Last sale" not in cols
    assert not any("sold" in line for line in u["insights"])
    assert {c["days"]: c["pcs"] for c in u["cards"]}[30] == 11


def test_the_rest_of_the_page_is_unchanged_by_the_sales_fields():
    plain = {**SNAP, "has_sales": False,
             "items": [{k: v for k, v in i.items() if k not in ("ls", "sa", "s90", "rsr", "radj")} for i in ITEMS]}
    a, b = sta.stock_ageing_dashboard(SNAP, {}), sta.stock_ageing_dashboard(plain, {})
    for key in ("kpis", "summary", "insights", "charts", "tables", "options", "notices"):
        assert a[key] == b[key], key


def test_api(monkeypatch):
    monkeypatch.delenv("SQL_SNAPSHOT_DIR", raising=False)
    client, _ = make_client(monkeypatch)
    u = client.get("/api/stock-ageing").json()["unsold"]
    assert u["has_sales"] and [c["days"] for c in u["cards"]] == [30, 90, 180, 365]
    assert sum(b["pcs"] for b in u["bands"]) == u["totals"]["pcs"]
