"""Every filter parameter of every endpoint reaches its dashboard.

The parity tests prove the dashboard functions match the original app; this file proves the HTTP layer passes each
query parameter to the right filter (a regression test: a shared Query() default once bound every list parameter
to the first parameter's name, so only ?month= worked).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import main
from app.config import Settings
from app.core import today_ist
from app.dashboards import fabric_po as fpo
from app.dashboards import fabricator as fab
from app.dashboards import master as mst
from app.dashboards import samples as smp
from app.dashboards import target as tgt
from app.sources.demo import DemoSheetSource
from app.store import DataStore

CASES = [
    ("/api/designer", "tracker", ["month", "designer", "order_type"]),
    ("/api/client", "tracker", ["month", "client", "order_type", "category"]),
    ("/api/production", "tracker", ["month", "fabricator", "status", "category", "designer"]),
    ("/api/samples", "sample_summary", ["month", "designer", "status", "vendor"]),
    ("/api/fabricator", "overview_fabricators", ["fabricator", "month"]),
    ("/api/fabric-po", "fabric_po", ["month", "vendor", "order_type", "client", "designer", "item", "status"]),
    ("/api/target", "target_revenue", ["month", "designer", "item", "order_by", "source"]),
]


@pytest.fixture(scope="module")
def env():
    settings = Settings(data_source="demo")
    store = DataStore(DemoSheetSource(), settings)
    mp = pytest.MonkeyPatch()
    mp.setattr(main, "get_settings", lambda: settings)
    mp.setattr(main, "get_store", lambda: store)
    yield TestClient(main.app), store
    mp.undo()


def direct(path, data, f):
    if path == "/api/designer":
        return mst.designer_dashboard(data, f)["kpis"]
    if path == "/api/client":
        return mst.client_dashboard(data, f)["kpis"]
    if path == "/api/production":
        return mst.production_dashboard(data, {**f, "risk": ""})["kpis"]
    if path == "/api/samples":
        return smp.samples_dashboard(data, f)["kpis"]
    if path == "/api/fabricator":
        return fab.fabricator_dashboard(data, f)["kpis"]
    if path == "/api/fabric-po":
        return fpo.fabric_po_dashboard(data, f).get("kpis")
    return tgt.target_dashboard(data, f, today=today_ist())["filtered"].get("kpis")


def api_kpis(path, body):
    return body["filtered"].get("kpis") if path == "/api/target" else body.get("kpis")


@pytest.mark.parametrize("path,kind,params", CASES, ids=[c[0] for c in CASES])
def test_each_filter_reaches_its_dashboard(env, path, kind, params):
    client, store = env
    options = client.get(path).json()["options"]
    data = store.dataset(kind).data
    narrowed = 0
    for p in params:
        opts = [o for o in options[p] if not str(o).startswith("(")]
        assert opts, f"{path}: no options for {p}"
        value = opts[min(1, len(opts) - 1)]
        body = client.get(path, params={p: value}).json()
        got = api_kpis(path, body)
        want = direct(path, data, {p: [value]})
        assert got == want, f"{path}?{p}={value}: API and dashboard disagree"
        all_ = api_kpis(path, client.get(path).json())
        narrowed += got != all_
    assert narrowed == len(params), f"{path}: {len(params) - narrowed} filters did not change anything"


def test_production_risk_filter(env):
    client, store = env
    for risk in ("Overdue", "On time"):
        got = client.get("/api/production", params={"risk": risk}).json()["kpis"]
        assert got == mst.production_dashboard(store.dataset("tracker").data, {"risk": risk})["kpis"]


def test_fabricator_metric_param(env):
    client, _ = env
    body = client.get("/api/fabricator", params={"metric": "RCVD (Pcs)"}).json()
    assert body["metric"] == "RCVD (Pcs)"
