"""Shared fixtures.

`legacy` loads the original Streamlit app (legacy/streamlit_app.py) with its UI layer replaced by recorders, so its
dashboards can run headless on the same sheet grids the new API reads. Every table it would have drawn and every KPI
tile it would have shown is captured for comparison.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import warnings
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("DATA_SOURCE", "demo")

TODAY = pd.Timestamp("2026-11-16")


class _Ctx:
    """Stands in for any Streamlit element: callable, usable as a context manager, any attribute works."""

    def __init__(self, rec):
        self._rec = rec

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __getattr__(self, name):
        return getattr(self._rec, name)


class FakeState(dict):
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError as e:
            raise AttributeError(k) from e

    def __setattr__(self, k, v):
        self[k] = v


class FakeSt:
    def __init__(self):
        self.session_state = FakeState()
        self.dataframes = []

    def columns(self, spec, **kw):
        n = spec if isinstance(spec, int) else len(spec)
        return [_Ctx(self) for _ in range(n)]

    def number_input(self, label, key=None, **kw):
        return self.session_state.get(key, 0.0)

    def selectbox(self, label, options, key=None, **kw):
        return self.session_state.get(key, list(options)[0])

    def dataframe(self, df, **kw):
        self.dataframes.append(df.copy())

    def __getattr__(self, name):
        def anything(*a, **kw):
            return _Ctx(self)
        return anything


class Recorder:
    def __init__(self):
        self.tables, self.kpis, self.notices = [], [], []


class Snapshot:
    """Wraps a source and freezes every grid on first read, so both apps see the same data."""

    def __init__(self, src):
        self.src, self.memo = src, {}

    def _get(self, key, fn):
        if key not in self.memo:
            self.memo[key] = fn()
        return self.memo[key]

    def list_tabs(self, sheet_id):
        return self._get(("tabs", sheet_id), lambda: self.src.list_tabs(sheet_id))

    def get_values(self, sheet_id, tab, formatted=False):
        return self._get(("v", sheet_id, tab, formatted), lambda: self.src.get_values(sheet_id, tab, formatted))

    def get_formulas(self, sheet_id, tab, col):
        return self._get(("f", sheet_id, tab, col), lambda: self.src.get_formulas(sheet_id, tab, col))


@pytest.fixture(scope="session")
def demo():
    """The data both apps read: built-in demo grids, or the real sheets with PARITY_SOURCE=google."""
    if os.getenv("PARITY_SOURCE") == "google":
        from app.config import get_settings
        from app.sources.google import GoogleSheetSource
        os.environ["DATA_SOURCE"] = "google"
        get_settings.cache_clear()
        return Snapshot(GoogleSheetSource(get_settings().service_account_info))
    from app.sources.demo import DemoSheetSource
    return DemoSheetSource()


@pytest.fixture(scope="session")
def tabs(demo):
    """Data tab names, chosen with the same rules the API uses."""
    from app.config import Settings
    from app.store import DataStore
    store = DataStore(demo, Settings())
    return {k: store.source_tabs(k) for k in ("tracker", "sample_summary", "overview_fabricators", "fabric_po",
                                                "target_revenue")}


@pytest.fixture()
def legacy(demo, monkeypatch):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        spec = importlib.util.spec_from_file_location("legacy_app", ROOT / "legacy" / "streamlit_app.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

    rec = Recorder()
    fake = FakeSt()
    mod.st = fake
    mod.rec = rec
    mod.fake = fake

    def show_table(df, *a, key_col=None, sort=True, sort_abs=False, **kw):
        if df is None or df.empty:
            rec.tables.append(None)
            return
        if key_col not in df.columns:
            key_col = None
        rec.tables.append(mod.order_rows(df, key_col, sort, sort_abs).reset_index(drop=True))

    mod.show_table = show_table
    mod.metrics = lambda items: rec.kpis.append([(str(l), str(v)) for l, v in items])
    mod.notice = lambda text, kind="info": rec.notices.append((kind, text))
    for name in ("chart", "empty_card", "badge", "dash_title", "hero", "_html", "show_access_error"):
        monkeypatch.setattr(mod, name, lambda *a, **k: None)
    mod.run_live = lambda fn, *args: fn(*args)
    mod._prefetch_sources = lambda kinds: None
    mod._today_ist = lambda: TODAY

    def fetch_grid(sheet_id, tab, formatted=False):
        return {"values": demo.get_values(sheet_id, tab, formatted), "synced": "test"}

    mod.fetch_grid = fetch_grid
    mod.load_tab_raw = lambda sheet_id, tab: demo.get_values(sheet_id, tab, False)
    mod.list_tabs_meta = lambda sheet_id: demo.list_tabs(sheet_id)
    mod.list_tabs = lambda sheet_id: [t for t, _ in demo.list_tabs(sheet_id)]
    mod.fetch_image_urls = lambda *a: {}
    return mod


def set_widgets(mod, values: dict):
    """Makes the legacy filter widgets return `values` (by key / label)."""
    def month_filter(container, label, options, key, placeholder="All months"):
        return list(values.get("month", []))

    def multi(container, label, options, key, placeholder="All"):
        return list(values.get(label, []))

    def filter_row(spec, key_prefix):
        out = {}
        for field, label, options in spec:
            if field == "month":
                out[field] = list(values.get("month", []))
            else:
                out[field] = values.get(field, "All")
        return out

    mod.month_filter = month_filter
    mod.multi = multi
    mod.filter_row = filter_row
    mod.fake.session_state["fab_metric"] = values.get("metric", "Fabric Issue (mtr)")
    mod.fake.session_state["tgt_annual_cr"] = values.get("annual_cr", 50.2)
