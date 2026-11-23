"""In/Out Sale dashboard: parsing the "2026-27" tab of the IN/OUT/SALE sheet (real grid copied from the sheet) and the API."""
import json
import pathlib

import pytest

from app.dashboards import in_out_sale as ios
from tests.test_api import make_client

GRID = json.loads((pathlib.Path(__file__).parent / "real_in_out_sale_grid.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def parsed():
    return ios.parse_in_out_sale(GRID)


def kp(d):
    return {k["id"]: k["value"] for k in d["kpis"]}


def test_month_label_parsing():
    assert ios.month_label_of(46138) == "April-26"           # a date cell (Google serial)
    assert ios.month_label_of("January-27") == "January-27"
    assert ios.month_label_of("Mar 2027") == "March-27"
    assert ios.month_label_of("TOTAL") is None


def test_month_table(parsed):
    mt = parsed["months"]
    assert mt["years"] == ["2026-27", "2025-26"]
    assert len(mt["rows"]) == 12
    apr = mt["rows"][0]
    assert (apr["month"], apr["order"], apr["incoming"], apr["pcs"], apr["amount"], apr["net"]) == \
        ("April-26", 56135, 38281, 42555, 47050512.0, 43761363.0)
    assert (apr["ly_pcs"], apr["ly_net"]) == (15193, 19981793.68)
    assert mt["total"]["pcs"] == 302678


def test_fabricator_blocks(parsed):
    names = {r["fabricator"] for r in parsed["fab"]}
    assert len(names) == 13 and {"RFS", "MEERA ETHNIC", "AMBRAEE", "FUSION STUDIO"} <= names
    assert not any("(" in n or n != n.strip() for n in names)
    fus = {r["month"]: r for r in parsed["fab"] if r["fabricator"] == "FUSION STUDIO"}
    assert fus["April-26"]["incoming"] == 24442 and fus["April-26"]["promised"] is None
    assert fus["May-26"]["promised"] == 30000 and fus["July-26"]["incoming"] == 34565
    assert fus["November-26"]["incoming"] == 4093
    assert parsed["block_totals"]["October-26"] == 28399


def test_dashboard_kpis_and_comparison(parsed):
    d = ios.in_out_sale_dashboard(parsed, {})
    k = kp(d)
    assert k["sale_pcs"] == 302678 and k["net_sale"] == 330321806 and len(d["kpis"]) == 7
    assert d["options"]["month"][0] == "April-26" and d["options"]["month"][-1] == "November-26"   # months with data only
    assert "▲" in next(x for x in d["kpis"] if x["id"] == "sale_pcs")["hint"]
    comp = d["tables"]["compare"]["rows"]
    assert comp[0][:3] == ["April-26", 42555, 15193] and comp[-1][0] == "TOTAL"
    assert d["charts"]["sale_pcs"]["series"][1]["name"] == "Sale pcs 2025-26"


def test_month_filter_applies_everywhere(parsed):
    d = ios.in_out_sale_dashboard(parsed, {"month": ["April-26", "May-26"]})
    assert kp(d)["sale_pcs"] == 42555 + 44001
    assert d["charts"]["fab_heat"]["columns"] == ["April-26", "May-26"]
    assert d["tables"]["fabricators"]["rows"][-1][-2] == 38281 + 42956


def test_fabricator_and_type_filters(parsed):
    d = ios.in_out_sale_dashboard(parsed, {"fabricator": ["FUSION STUDIO"]})
    assert d["fabricators"]["count"] == 1 and kp(d)["sale_pcs"] == 302678      # money part is not fabricator-wise
    out = ios.in_out_sale_dashboard(parsed, {"type": ["Outsource"]})
    names = [r[0] for r in out["tables"]["fabricators"]["rows"][:-1]]
    assert "RFS" in names and "FUSION STUDIO" not in names


def test_promise_math(parsed):
    d = ios.in_out_sale_dashboard(parsed, {"month": ["May-26"]})
    rows = {r[1]: r for r in d["tables"]["promises"]["rows"]}
    assert rows["FUSION STUDIO"][2:5] == [30000, 25397, 4603]
    assert rows["AMBRAEE"][4] == 5193


def test_sheet_inconsistency_is_flagged(parsed):
    d = ios.in_out_sale_dashboard(parsed, {})
    assert any("November-26" in c["text"] and "8,985" in c["text"] for c in d["checks"])


def test_empty_tab():
    d = ios.in_out_sale_dashboard(ios.parse_in_out_sale([["nothing here"]]), {})
    assert d["empty"] and d["notices"]


def test_api(monkeypatch):
    client, _ = make_client(monkeypatch)
    r = client.get("/api/in-out-sale")
    assert r.status_code == 200
    body = r.json()
    assert body["tables"]["flow"]["rows"][-1][0] == "TOTAL" and body["fabricators"]["count"] > 0
    assert client.get("/api/in-out-sale", params={"month": body["options"]["month"][:1], "type": "Outsource"}).status_code == 200
    assert "in_out_sale" in client.get("/api/status").json()["sources"] if "sources" in client.get("/api/status").json() else True
