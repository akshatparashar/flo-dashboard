"""Stock Ageing and Unsold Inventory through FLO Assistant. Every expected figure is read from /api/stock-ageing in the
same run (made-up demo rows, which carry sales history)."""
from __future__ import annotations

import pytest

from app.assistant import fmt, stock
from test_assistant_calc import client  # noqa: F401  (fixture)


@pytest.fixture(autouse=True)
def no_snapshot(monkeypatch):
    monkeypatch.delenv("SQL_SNAPSHOT_DIR", raising=False)
    monkeypatch.delenv("EASYTRADE_MCP_URL", raising=False)


def page(client, **params):
    return client.get("/api/stock-ageing", params=params).json()


def table(body):
    t = body["unsold"]["table"]
    return [c["label"] for c in t["columns"]], t["rows"]


def talk(client, *messages):
    conv = ctx = None
    out = []
    for m in messages:
        j = client.post("/api/chat", json={"message": m, "conversation_id": conv, "context": ctx}).json()
        conv = j["conversation_id"]
        if j["understood"]:
            ctx = j["context"]
        out.append(j)
    return out


def ask(client, message):
    return talk(client, message)[-1]


def text(reply):
    return reply["answer"].replace("**", "")


def over(body, days):
    cols, rows = table(body)
    hit = [r for r in rows if (r[cols.index("Days without sale")] or 0) > days]
    return len(hit), sum(r[cols.index("Pcs")] for r in hit)


@pytest.mark.parametrize("question,days", [("90 din se kitne designs nahi bike", 90), ("1 saal se kya nahi bika", 365),
                                           ("6 mahine se nahi bika stock", 180), ("45 din se nahi bika", 45),
                                           ("180 din se na bikne wale designs ki list", 180),
                                           ("not sold in 30 days", 30)])
def test_no_sale_for_n_days(client, question, days):
    n, pcs = over(page(client), days)
    a = ask(client, question)
    assert a["page"] == "/stock-ageing", a["answer"][:150]
    assert f"{n:,} designs" in text(a) and fmt.fmt_int(pcs) in text(a)


def test_never_sold(client):
    never = page(client)["unsold"]["never"]
    for q in ("never sold designs", "kabhi nahi bike wale kitne hain"):
        a = ask(client, q)
        assert a["page"] == "/stock-ageing" and f"{never['designs']:,} designs" in text(a)
        assert fmt.fmt_int(never["pcs"]) in text(a)


def test_unsold_overview_lists_every_threshold(client):
    cards = page(client)["unsold"]["cards"]
    a = text(ask(client, "unsold stock kitna hai"))
    for c in cards:
        assert f"{c['days']} days" in a and f"{c['no_sale']['designs']:,} designs" in a


def test_longest_unsold_and_oldest_stock_name_the_designs(client):
    cols, rows = table(page(client))
    a = ask(client, "kaunsa design sabse zyada din se nahi bika")
    assert rows[0][0] in text(a) and a["page"] == "/stock-ageing"
    oldest = max(r[cols.index("Oldest piece (days)")] for r in rows)
    assert f"{fmt.fmt_int(oldest)} days" in text(ask(client, "sabse purana stock kaunsa hai"))


def test_series_questions(client):
    body = page(client)
    series = next(o for o in body["options"]["type"] if o.startswith("Series "))
    n, _ = over(page(client, type=series), 90)
    a = ask(client, f"{series.lower()} me kitne designs 90 din se nahi bike")
    assert series in text(a) and f"{n:,} designs" in text(a)
    wise = ask(client, "series wise stock")["answer"]
    assert all(r[0] in wise for r in body["tables"]["types"]["rows"][:-1])
    ranked = ask(client, "kis series me sabse zyada unsold stock hai")
    assert ranked["page"] == "/stock-ageing" and "90" in text(ranked)


def test_average_age_adjustments_and_location(client):
    body = page(client)
    a = ask(client, "average age of stock")
    assert a["page"] == "/stock-ageing" and f"{body['summary']['avg_age']} days" in text(a)
    adj = ask(client, "stock count adjustment wale pcs kitne")
    assert adj["page"] == "/stock-ageing" and "journal" in text(adj)
    for q in ("stock ageing page kaha hai", "unsold inventory kaha dikhta hai"):
        where = ask(client, q)
        assert where["page"] == "/stock-ageing" and "sidebar" in text(where)


def test_one_design_by_its_code(client):
    cols, rows = table(page(client))
    code = rows[0][0]
    a = ask(client, f"design {code} kab bika tha")
    assert code in text(a) and f"{fmt.fmt_int(rows[0][cols.index('Days without sale')])} days without a sale" in text(a)


def test_older_than_30_is_not_the_0_to_30_band(client):
    older = page(client)["unsold"]["cards"][0]
    a = text(ask(client, "30 din se purana stock"))
    assert fmt.fmt_int(older["pcs"]) in a
    assert fmt.fmt_int(page(client)["charts"]["qty_by_age"][1]["value"]) in text(ask(client, "31-60 din ka stock"))


def test_unsold_follow_ups_keep_the_subject(client):
    body = page(client)
    n180, _ = over(body, 180)
    replies = talk(client, "kitne designs 90 din se nahi bike", "aur 180 din?", "unki value kitni hai?",
                   "kaunse designs hain?", "never sold kitne hain?")
    assert all(r["page"] == "/stock-ageing" for r in replies)
    for r in replies[1:4]:
        assert f"{n180:,} designs" in text(r)
    assert "•" in replies[3]["answer"]
    assert f"{body['unsold']['never']['designs']:,} designs" in text(replies[4])


def test_series_follow_ups(client):
    series = next(o for o in page(client)["options"]["type"] if o.startswith("Series "))
    n365, _ = over(page(client, type=series), 365)
    replies = talk(client, "unsold stock kitna hai", f"{series.lower()} me?", "1 saal wale?", "kaunse?")
    assert all(r["page"] == "/stock-ageing" for r in replies)
    assert series in text(replies[1])
    for r in replies[2:]:
        assert series in text(r) and f"{n365:,} designs" in text(r)


def test_a_new_subject_leaves_stock(client):
    _, designers, production = talk(client, "closing stock kitna hai", "which designer has most orders",
                                    "production pending kitna hai")
    assert designers["page"] == "/designers" and production["page"] == "/production"


@pytest.mark.parametrize("question", ["net sale this year", "fabric po pending", "fabricator remaining stock kitna hai",
                                      "flo future overdue batao", "total po count", "arihant sir ke pending task",
                                      "samples pending kitne hai", "which designer has most orders"])
def test_other_pages_are_not_taken_over(question):
    assert not stock.matches(question, None)


@pytest.mark.parametrize("words,days", [("90 din", 90), ("1 saal", 365), ("ek saal", 365), ("6 mahine", 180),
                                        ("three months", 90), ("180 se purana", 180), ("series 90", None),
                                        ("31-60 din", None), ("design 70- 71144/S", None)])
def test_days_are_read_correctly(words, days):
    assert stock.days_in(words) == days


def test_without_sales_history_nothing_is_claimed(client, monkeypatch, tmp_path):
    import json
    from app.dashboards import stock_ageing as sta
    snap = sta.demo_snapshot()
    snap["has_sales"] = False
    for item in snap["items"]:
        for k in ("ls", "sa", "s90"):
            item.pop(k, None)
    (tmp_path / "stock_ageing.json").write_text(json.dumps(snap), encoding="utf-8")
    monkeypatch.setenv("SQL_SNAPSHOT_DIR", str(tmp_path))
    a = text(ask(client, "90 din se kitne designs nahi bike"))
    assert "Sales history is not in this stock snapshot" in a and "No sale for over" not in a
