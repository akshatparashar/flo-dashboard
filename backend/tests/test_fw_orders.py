"""FW ORDER'S table (master sheet DASHBOARD tab) and the client pie chart."""
from app.dashboards import fw_orders as fwo
from tests.test_api import make_client

REAL = [
    ["FW", "", "", "", "", "", "MB"] + [""] * 11 + ["FW ORDER'S", "", "", "", ""],
    [""] * 18 + ["MONTH", "ORDER  PC'S", "DISPATCHED PC'S", "PENDING PC'S", "OVERALL DISPATCHED PC'S"],
    [""] * 18 + ["Apr-2026", "32,065", "32065", "0", "23273"],
    [""] * 18 + ["May-2026", 48620, 48620, 0, 31069],
    [""] * 18 + ["Jun-2026", 97365, 87965, 9400, 26027],
    [""] * 18 + ["", 178050, 168650, 9400, 80369],
    [""] * 18 + ["", "", "", "", ""],
    [""] * 18 + ["Later", 5, 5, 5, 5],          # below the blank line: not part of the table
]


def test_parse_finds_table_by_title_and_header():
    p = fwo.parse_fw_orders(REAL)
    assert [r["month"] for r in p["rows"]] == ["Apr-2026", "May-2026", "Jun-2026"]
    assert p["rows"][0]["order"] == 32065
    assert p["sheet_total"]["order"] == 178050


def test_dashboard_totals_and_chart():
    d = fwo.fw_orders_dashboard(fwo.parse_fw_orders(REAL))
    assert d["table"]["rows"][-1][:3] == ["TOTAL", 178050, 168650]
    assert d["table"]["meta"][-1]["kind"] == "total"
    assert [s["name"] for s in d["chart"]["series"]] == ["Order pcs", "Dispatched pcs", "Pending pcs"]
    assert d["totals"]["pending"] == 9400 and d["checks"] == []


def test_total_mismatch_is_flagged():
    g = [list(r) for r in REAL]
    g[5][19] = 999
    d = fwo.fw_orders_dashboard(fwo.parse_fw_orders(g))
    assert d["checks"] and "Order pcs" in d["checks"][0]["text"]


def test_missing_table_gives_none():
    assert fwo.fw_orders_dashboard(fwo.parse_fw_orders([["x", "y"]])) is None
    assert fwo.fw_orders_dashboard(fwo.parse_fw_orders([])) is None


def test_client_endpoint_has_fw_orders_and_pie(monkeypatch):
    client, _ = make_client(monkeypatch)
    body = client.get("/api/client").json()
    fw = body["fw_orders"]
    # Jan-Mar 2026 are left out: only April onwards is shown
    assert fw["totals"]["order"] == 360268 - 32065 - 48620 - 97365 and fw["totals"]["overall"] == 361482 - 23273 - 31069 - 26027
    assert fw["table"]["rows"][-1][0] == "TOTAL"
    pie = body["charts"]["client_share"]
    assert pie and len(pie) <= 8
    assert abs(sum(p["value"] for p in pie) - next(k["value"] for k in body["kpis"] if k["id"] == "qty")) < 1


def test_chart_months_are_short():
    d = fwo.fw_orders_dashboard(fwo.parse_fw_orders(REAL))
    assert d["chart"]["categories"] == ["Apr-26", "May-26", "Jun-26"]


def test_delivery60_buckets_and_tables():
    import pandas as pd
    from app.dashboards import master as mst
    d = pd.DataFrame({
        "client": ["FW", "FW", "MB", "MB", "FW"],
        "pending": [100, 50, 30, 0, 20],
        "due60": pd.to_datetime(["2026-11-01", "2026-11-25", "2026-12-30", "2026-11-01", None]),
    })
    r = mst.delivery60(d, "2026-11-21")
    k = {x["id"]: x["value"] for x in r["kpis"]}
    assert k == {"total": 200, "overdue": 100, "due7": 50, "due30": 0, "later": 30, "nodate": 20}
    months = r["tables"]["months"]["rows"]
    assert months[0][:4] == ["November-26", 2, 150, 100] and months[-1][0] == "TOTAL"
    clients = {row[0]: row for row in r["tables"]["clients"]["rows"]}
    assert clients["FW"][2] == 170 and clients["FW"][3] == 100 and clients["FW"][4] == "01/11/2026"
    assert r["chart"]["series"][0]["values"] == [100.0, 0.0] and r["chart"]["series"][1]["values"] == [50.0, 30.0]


def test_delivery60_none_when_nothing_pending():
    import pandas as pd
    from app.dashboards import master as mst
    assert mst.delivery60(pd.DataFrame({"pending": [0], "due60": [pd.NaT], "client": ["FW"]}), "2026-11-21") is None


def test_only_april_onwards_is_shown():
    g = [list(r) for r in REAL]
    g[2][18] = "Mar-2026"
    d = fwo.fw_orders_dashboard(fwo.parse_fw_orders(g))
    assert d["chart"]["categories"] == ["May-26", "Jun-26"]
    assert d["table"]["rows"][-1][:2] == ["TOTAL", 48620 + 97365] and d["checks"] == []
