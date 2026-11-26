"""Stock Ageing dashboard (FIFO pcs from the EasyTrade snapshot). All rows here are made up."""
import json

import pytest

from app.dashboards import stock_ageing as sta
from tests.test_api import make_client


def item(code, name, slot, qty, rate, wa):
    row = {"c": "1", "p": "x", "d": code, "n": name, "b": qty, "oi": "2026-01-01", "li": "2026-01-01", "wa": wa}
    row.update({k: 0 for k in sta.Q + sta.V})
    row[sta.Q[slot]], row[sta.V[slot]] = qty, qty * rate
    return row


ITEMS = [item("70- 1", "BLUE KURTA", 0, 10, 100, 10), item("70- 2", "RED DRESS", 4, 5, 200, 200),
         item("ODD", "OLD GOWN", 5, 2, 500, 700), item("70- 3", "NO RATE", 1, 3, 0, 40)]
SNAP = {"as_on": "2026-11-25", "source": "t", "items": ITEMS, "control": {"qty": 20}}


def kp(d):
    return {k["id"]: k["value"] for k in d["kpis"]}


def test_totals_and_ageing():
    d = sta.stock_ageing_dashboard(SNAP, {})
    k = kp(d)
    assert k["qty"] == 20 and k["value"] == 3000 and k["old_qty"] == 7 and k["old_value"] == 2000 and k["dead_qty"] == 2
    assert k["age"] == round((10 * 10 + 5 * 200 + 2 * 700 + 3 * 40) / 20)
    assert d["tables"]["ages"]["rows"][-1][:2] == ["TOTAL", 20]
    assert [c["value"] for c in d["charts"]["qty_by_age"]] == [10, 3, 0, 0, 5, 2]
    assert d["tables"]["stuck"]["rows"][0][0] == "ODD" or d["tables"]["stuck"]["rows"][0][0] == "70- 2"
    assert any("no inward rate" in n["text"] for n in d["notices"])


def test_series_grouping():
    assert sta.design_series("70- 10110/S") == "Series 70" and sta.design_series("09-9924") == "Series 09"
    assert sta.design_series("ABC") == "No series"


def test_filters():
    d = sta.stock_ageing_dashboard(SNAP, {"age": ["Over 365 days"]})
    assert kp(d)["qty"] == 2
    assert kp(sta.stock_ageing_dashboard(SNAP, {"q": ["dress"]}))["qty"] == 5
    assert sta.stock_ageing_dashboard(SNAP, {"q": ["zzz"]})["no_match"]


def test_control_total_mismatch_is_flagged():
    d = sta.stock_ageing_dashboard({**SNAP, "control": {"qty": 99}}, {})
    assert any("ledger total" in n["text"] for n in d["notices"])


def test_snapshot_folder_and_demo(monkeypatch, tmp_path):
    monkeypatch.delenv("SQL_SNAPSHOT_DIR", raising=False)
    assert sta.load_snapshot()["demo"] is True
    (tmp_path / "stock_ageing.json").write_text(json.dumps(SNAP), encoding="utf-8")
    monkeypatch.setenv("SQL_SNAPSHOT_DIR", str(tmp_path))
    s = sta.load_snapshot()
    assert s["demo"] is False and len(s["items"]) == 4


def test_api(monkeypatch):
    monkeypatch.delenv("SQL_SNAPSHOT_DIR", raising=False)
    client, _ = make_client(monkeypatch)
    body = client.get("/api/stock-ageing").json()
    assert body["demo"] and body["summary"]["qty"] > 0
    assert client.get("/api/stock-ageing", params={"age": "Over 365 days", "q": "demo"}).status_code == 200
