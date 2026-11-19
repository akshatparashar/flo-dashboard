"""API behaviour: every route, filters, auth, refresh rate limit, caching and failure handling."""
from __future__ import annotations

import time

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import main
from app.config import Settings
from app.core import FY_MONTH_LABELS, inr, inr_short, num, parse_dates
from app.dashboards.fabric_po import parse_rcvd_cell
from app.sources.demo import DemoSheetSource
from app.sources.google import SheetAccessError
from app.store import DataStore


def make_client(monkeypatch, source=None, **overrides):
    settings = Settings(**{"data_source": "demo", **overrides})
    store = DataStore(source or DemoSheetSource(), settings)
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    monkeypatch.setattr(main, "get_store", lambda: store)
    return TestClient(main.app), store


ROUTES = ["/api/overview", "/api/designer", "/api/client", "/api/production", "/api/samples", "/api/fabricator",
          "/api/fabric-po", "/api/target", "/api/flo-future", "/api/vendor-rate", "/api/context", "/api/status"]


@pytest.mark.parametrize("path", ROUTES)
def test_routes_ok(monkeypatch, path):
    client, _ = make_client(monkeypatch)
    r = client.get(path)
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store"
    body = r.json()
    if path != "/api/status":
        assert body["meta"]["source"] == "demo"
        assert body["meta"]["ttl"] == 60
        assert body["meta"]["synced_at"]


def test_health(monkeypatch):
    client, _ = make_client(monkeypatch)
    assert client.get("/api/health").json()["ok"] is True


def test_multi_value_filters(monkeypatch):
    client, _ = make_client(monkeypatch)
    all_ = client.get("/api/production").json()
    one = client.get("/api/production", params={"month": FY_MONTH_LABELS[1]}).json()
    two = client.get("/api/production", params=[("month", FY_MONTH_LABELS[1]), ("month", FY_MONTH_LABELS[2])]).json()
    val = {k["id"]: k["value"] for k in all_["kpis"]}
    v1 = {k["id"]: k["value"] for k in one["kpis"]}
    v2 = {k["id"]: k["value"] for k in two["kpis"]}
    assert v1["production"] <= v2["production"] <= val["production"]
    # "All" and blanks mean no filter
    same = client.get("/api/production", params=[("month", "All"), ("month", "")]).json()
    assert {k["id"]: k["value"] for k in same["kpis"]} == val


def test_totals_add_up(monkeypatch):
    """Totals shown on screen are the sum of the rows shown."""
    client, _ = make_client(monkeypatch)
    body = client.get("/api/client").json()
    t = body["tables"]["monthly"]
    rows = [r for r, m in zip(t["rows"], t["meta"]) if m["kind"] != "total"]
    total = [r for r, m in zip(t["rows"], t["meta"]) if m["kind"] == "total"][0]
    for j in range(1, len(t["columns"])):
        assert abs(sum(r[j] for r in rows) - total[j]) < 1e-6
    k = {x["id"]: x["value"] for x in body["kpis"]}
    assert k["qty"] == total[1]
    assert k["production"] == total[2]


def test_target_annual_input(monkeypatch):
    client, _ = make_client(monkeypatch)
    a = client.get("/api/target", params={"annual_target_cr": 10}).json()
    b = client.get("/api/target", params={"annual_target_cr": 20}).json()
    ka = {k["id"]: k["value"] for k in a["tracker"]["kpis"]}
    kb = {k["id"]: k["value"] for k in b["tracker"]["kpis"]}
    assert ka["target"] == 10e7 and kb["target"] == 20e7
    assert ka["achieved"] == kb["achieved"]
    assert client.get("/api/target", params={"annual_target_cr": -1}).status_code == 422


def test_auth_flow(monkeypatch):
    client, _ = make_client(monkeypatch, passcode="flo-2026", token_secret="s3cret")
    assert client.get("/api/overview").status_code == 401
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/auth/status").json() == {"required": True, "signed_in": False}
    assert client.post("/api/auth/login", json={"passcode": "nope"}).status_code == 401
    tok = client.post("/api/auth/login", json={"passcode": "flo-2026"}).json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert client.get("/api/overview", headers=h).status_code == 200
    assert client.get("/api/auth/status", headers=h).json()["signed_in"] is True
    bad = tok[:-2] + ("AA" if not tok.endswith("AA") else "BB")
    assert client.get("/api/overview", headers={"Authorization": f"Bearer {bad}"}).status_code == 401


def test_login_rate_limited(monkeypatch):
    client, _ = make_client(monkeypatch, passcode="right")
    main._failed_logins.clear()
    codes = [client.post("/api/auth/login", json={"passcode": "wrong"}).status_code for _ in range(11)]
    assert codes[:10] == [401] * 10 and codes[10] == 429
    main._failed_logins.clear()


def test_refresh_cooldown(monkeypatch):
    client, _ = make_client(monkeypatch, refresh_cooldown=30)
    assert client.post("/api/refresh").json()["refreshed"] is True
    assert client.post("/api/refresh").json()["refreshed"] is False


class CountingSource(DemoSheetSource):
    def __init__(self):
        super().__init__()
        self.calls = 0
        self.fail = False

    def get_values(self, sheet_id, tab, formatted=False):
        self.calls += 1
        if self.fail:
            raise SheetAccessError("Google API 503")
        return super().get_values(sheet_id, tab, formatted)


def test_cache_reads_once_per_ttl(monkeypatch):
    src = CountingSource()
    client, store = make_client(monkeypatch, source=src)
    for _ in range(5):
        assert client.get("/api/designer").status_code == 200
    assert src.calls == 1


def test_stale_data_served_when_google_fails(monkeypatch):
    src = CountingSource()
    client, store = make_client(monkeypatch, source=src, live_ttl=0)
    first = client.get("/api/designer").json()
    src.fail = True
    time.sleep(0.01)
    second = client.get("/api/designer")
    assert second.status_code == 200
    body = second.json()
    assert body["meta"]["stale"] is True
    assert body["kpis"] == first["kpis"]


def test_error_without_cache_is_503(monkeypatch):
    src = CountingSource()
    src.fail = True
    client, _ = make_client(monkeypatch, source=src)
    r = client.get("/api/samples")
    assert r.status_code == 503
    assert "503" in r.json()["detail"]
    ov = client.get("/api/overview").json()     # overview still loads and lists the failures
    assert len(ov["errors"]) == 5                # four original sheets + FLO Future


def test_unknown_metric_falls_back(monkeypatch):
    client, _ = make_client(monkeypatch)
    assert client.get("/api/fabricator", params={"metric": "bogus"}).json()["metric"] == "Fabric Issue (mtr)"


# ------------------------------------------------------------------------------------------------ parsing units
def test_num_handles_sheet_text():
    s = pd.Series([1, "1,234", "(50)", "12%", "5 Days", "", None, "−7", "1.2.3", "abc"])
    assert num(s).tolist() == [1, 1234, -50, 12, 5, 0, 0, -7, 0, 0]


def test_parse_dates_serial_and_text():
    out = parse_dates(pd.Series([46143, "15/04/2026", "2026-04-15", "", "junk"]))
    assert out[0] == pd.Timestamp("2026-05-01")
    assert out[1] == out[2] == pd.Timestamp("2026-04-15")
    assert pd.isna(out[3]) and pd.isna(out[4])


def test_part_lot_receive_dates():
    assert parse_rcvd_cell("24/04/2026+15/05/2026") == [pd.Timestamp("2026-04-24"), pd.Timestamp("2026-05-15")]
    assert parse_rcvd_cell(46136) == [pd.Timestamp("2026-04-24")]
    assert parse_rcvd_cell("") == [] and parse_rcvd_cell(None) == []


def test_rupee_formatting():
    assert inr(5020000) == "₹50,20,000"
    assert inr(-1234.4) == "-₹1,234"
    assert inr_short(50.2e7) == "₹50.20 Cr"
    assert inr_short(329000) == "₹3.29 L"
    assert inr_short(4500) == "₹4,500"


def test_column_title_typed_in_a_cell_is_blank():
    from app.dashboards.fabric_po import build_fabric_po
    header = ["S.NO", "VENDOR NAME", "PO NO.", "ORDER DATE", "DELIVERY DATE", "RCVD DATE", "DELAY DAYS", "ORDER TYPE",
              "CLIENT NAME", "DESIGNER NAME", "COLLECTION NAME", "STATUS", "ACTUAL ORDER QTY.",
              "TOTAL MTR OF FABRIC ORDERED", "TOTAL MTR OF FABRIC RCVD", "PENDING"]
    row = [1, "RV", "RV 1", "01/05/2026", "", "", "", "NEW", "CLIENT NAME", "DESIGNER NAME", "", "PENDING", 10, 100, 0,
           100]
    d, _ = build_fabric_po([header, row])
    assert d.loc[0, "client"] == "(BLANK)" and d.loc[0, "designer"] == "(BLANK)"
    assert d.loc[0, "status"] == "PENDING"        # a real status that happens to match a number column's title


def test_token_secret_never_falls_back_to_a_public_value(monkeypatch):
    from app.config import _token_secret
    monkeypatch.setenv("TOKEN_SECRET", "change-me")
    derived = _token_secret({"private_key": "-----BEGIN PRIVATE KEY-----abc"})
    assert derived not in ("change-me", "dev-only-secret") and len(derived) == 64
    monkeypatch.setenv("TOKEN_SECRET", "a-long-random-value")
    assert _token_secret({"private_key": "x"}) == "a-long-random-value"
