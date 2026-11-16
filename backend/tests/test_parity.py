"""Parity: the new API must show exactly what the original Streamlit dashboards showed.

Each test runs a legacy dashboard headless (see conftest.legacy) and the new dashboard function on the same sheet
grids and the same filters, then compares every table cell (same rows, same order, same values) and every KPI.
Column titles were rewritten in plain English, so tables are compared by position.
"""
from __future__ import annotations

import math
import re

import numpy as np
import pandas as pd
import pytest

from app.config import SHEET_REGISTRY
from app.core import FY_MONTH_LABELS, inr, inr_short
from app.dashboards import fabric_po as fpo
from app.dashboards import fabricator as fab
from app.dashboards import master as mst
from app.dashboards import overview as ovw
from app.dashboards import samples as smp
from app.dashboards import target as tgt
from tests.conftest import TODAY, set_widgets

IDS = {k: v["id"] for k, v in SHEET_REGISTRY.items()}


# ------------------------------------------------------------------------------------------------ comparison
def _same(a, b):
    if isinstance(a, pd.Timestamp):
        return b == (None if pd.isna(a) else a.strftime("%d/%m/%Y"))
    if isinstance(a, (int, float, np.integer, np.floating)) and not isinstance(a, bool):
        if a is None or (isinstance(a, float) and math.isnan(a)) or (isinstance(a, np.floating) and np.isnan(a)):
            return b is None
        if b is None or isinstance(b, str):
            return False
        return math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=1e-6)
    if a is None or (isinstance(a, float) and math.isnan(a)):
        return b is None or b == ""
    return str(a) == str(b)


def assert_table(legacy_df, mine, where):
    if legacy_df is None or len(legacy_df) == 0:
        assert not mine["rows"], f"{where}: legacy shows no table, new one has {len(mine['rows'])} rows"
        return
    assert len(mine["columns"]) == len(legacy_df.columns), f"{where}: column count"
    assert len(mine["rows"]) == len(legacy_df), f"{where}: row count {len(mine['rows'])} != {len(legacy_df)}"
    for i, (lrow, mrow) in enumerate(zip(legacy_df.itertuples(index=False), mine["rows"])):
        for j, (a, b) in enumerate(zip(lrow, mrow)):
            assert _same(a, b), f"{where}: row {i} ({lrow[0]}) col {legacy_df.columns[j]!r}: legacy {a!r} != new {b!r}"


def _alnum(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def expected_text(k):
    v, f = k["value"], k["format"]
    if f == "text":
        return None
    if f == "inr":
        return inr_short(v)
    if f == "inr_full":
        return inr(v)
    if f == "pct":
        return f"{v:.1f}%"
    if f == "dec1":
        return f"{v:.1f}"
    return f"{v:,.0f}"


def assert_kpis(legacy_items, mine, where):
    assert len(legacy_items) == len(mine), f"{where}: KPI count {len(mine)} != {len(legacy_items)}"
    for (label, text), k in zip(legacy_items, mine):
        exp = expected_text(k)
        if exp is not None:
            assert exp in text, f"{where}: KPI {label!r}: legacy {text!r} does not show {exp!r}"
            continue
        val = str(k["value"])
        if val in ("—", "None") or text in ("—", "N/A", "None"):
            assert _alnum(text) in ("", "na", "none") and val in ("—", "None"), f"{where}: KPI {label!r}: {text!r} vs {val!r}"
            continue
        assert _alnum(text).startswith(_alnum(val)), f"{where}: KPI {label!r}: legacy {text!r} vs new {val!r}"
        if k.get("hint"):
            nums = re.findall(r"\d[\d,]*\.?\d*", k["hint"])
            for n in nums:
                if "pcs" in k["hint"]:
                    assert n in text, f"{where}: KPI {label!r}: legacy {text!r} lacks {n}"


# ------------------------------------------------------------------------------------------------ master
@pytest.fixture()
def master_df(demo, tabs):
    d, err = mst.parse_master(demo.get_values(IDS["tracker"], tabs["tracker"][0]))
    assert err is None
    return d


def _pick(seq, i=0):
    seq = [s for s in seq if not str(s).startswith("(")]
    return seq[i % len(seq)]


def master_cases(d):
    opts = mst.master_options(d)
    return [
        {},
        {"month": [FY_MONTH_LABELS[1]]},
        {"month": FY_MONTH_LABELS[2:5]},
        {"designer": _pick(opts["designer"], 2)},
        {"order_type": "REPEAT"},
        {"client": _pick(opts["client"], 1), "category": "KURTA PANT"},
        {"fabricator": _pick(opts["fabricator"]), "risk": "Overdue (>0 days)"},
        {"status": "COMPLETED", "risk": "On-time (≤0 days)"},
        {"month": [FY_MONTH_LABELS[11]]},                      # a month with no data
        {"designer": "NOBODY"},
    ]


DASH_FIELDS = {
    "designer": ("month", "designer", "order_type"),
    "client": ("month", "client", "order_type", "category"),
    "production": ("month", "fabricator", "status", "category", "designer", "risk"),
}


def to_new_master(f, dash):
    out = {}
    for k, v in f.items():
        if k not in DASH_FIELDS[dash]:
            continue
        if k == "risk":
            out["risk"] = "Overdue" if v.startswith("Overdue") else "On time"
        elif k == "month":
            out["month"] = v
        else:
            out[k] = [v]
    return out


@pytest.mark.parametrize("case", range(10))
def test_designer_dashboard(legacy, master_df, case):
    f = master_cases(master_df)[case]
    set_widgets(legacy, f)
    legacy.designer_dashboard(master_df, "k")
    new = mst.designer_dashboard(master_df, to_new_master(f, "designer"))
    assert_table(legacy.rec.tables[0], new["tables"]["designers"], f"designers {f}")
    assert_table(legacy.rec.tables[1], new["tables"]["categories"], f"categories {f}")
    assert_kpis(legacy.rec.kpis[0], new["kpis"], f"designer KPIs {f}")


@pytest.mark.parametrize("case", range(10))
def test_client_dashboard(legacy, master_df, case):
    f = master_cases(master_df)[case]
    set_widgets(legacy, f)
    legacy.client_dashboard(master_df, "k")
    new = mst.client_dashboard(master_df, to_new_master(f, "client"))
    assert_table(legacy.rec.tables[0], new["tables"]["monthly"], f"client monthly {f}")
    assert_table(legacy.rec.tables[1], new["tables"]["categories"], f"client categories {f}")
    assert_kpis(legacy.rec.kpis[0], new["kpis"], f"client KPIs {f}")


@pytest.mark.parametrize("case", range(10))
def test_production_dashboard(legacy, master_df, case):
    f = master_cases(master_df)[case]
    set_widgets(legacy, f)
    legacy.production_dashboard(master_df, "k")
    new = mst.production_dashboard(master_df, to_new_master(f, "production"))
    tables = list(legacy.rec.tables)
    assert_table(tables.pop(0), new["tables"]["categories"], f"production categories {f}")
    if new["tables"]["fabricators"]["rows"]:
        assert_table(tables.pop(0), new["tables"]["fabricators"], f"production fabricators {f}")
    assert_table(tables.pop(0), new["tables"]["monthly"], f"production monthly {f}")
    assert not tables
    assert_kpis(legacy.rec.kpis[0], new["kpis"], f"production KPIs {f}")


def test_master_parsing_matches(legacy, demo, master_df, tabs):
    values = demo.get_values(IDS["tracker"], tabs["tracker"][0])
    raw, _ = legacy.build_raw(values)
    old = legacy.prepare(raw)
    pd.testing.assert_frame_equal(old, master_df)
    assert legacy.month_list(old) == mst.month_list(master_df)


# ------------------------------------------------------------------------------------------------ samples
def sample_cases(parsed):
    d = parsed["d"]
    des = sorted(n for n in d["designer"].unique() if not n.startswith("("))
    ven = sorted(n for n in d["vendor"].unique() if not n.startswith("("))
    return [
        {},
        {"month": [FY_MONTH_LABELS[0]]},
        {"Designer": [des[0], des[3]]},
        {"Status": ["Approved", "Rejected"]},
        {"Vendor": [ven[1]], "month": FY_MONTH_LABELS[3:7]},
        {"Designer": [des[2]], "Vendor": [ven[0]], "Status": ["In Process"]},
        {"month": [FY_MONTH_LABELS[11]]},
    ]


@pytest.mark.parametrize("case", range(7))
def test_samples_dashboard(legacy, demo, tabs, case):
    values = demo.get_values(IDS["sample_summary"], tabs["sample_summary"][0])
    parsed = smp.parse_samples(values)
    f = sample_cases(parsed)[case]
    set_widgets(legacy, f)
    legacy._sample_body("Sample Summary", SHEET_REGISTRY["sample_summary"], tabs["sample_summary"][0])
    new = smp.samples_dashboard(parsed, {"month": f.get("month", []), "designer": f.get("Designer", []),
                                         "status": f.get("Status", []), "vendor": f.get("Vendor", [])})
    assert_table(legacy.rec.tables[0], new["tables"]["monthly"], f"samples monthly {f}")
    assert_table(legacy.rec.tables[1], new["tables"]["designers"], f"samples designers {f}")
    assert_table(legacy.rec.tables[2], new["tables"]["vendors"], f"samples vendors {f}")
    assert_kpis(legacy.rec.kpis[0], new["kpis"], f"samples KPIs {f}")


# ------------------------------------------------------------------------------------------------ fabricator
def fab_cases(names):
    return [
        {},
        {"month": [FY_MONTH_LABELS[3]]},
        {"Fabricator": names[:2]},
        {"Fabricator": names[-1:], "month": FY_MONTH_LABELS[0:4], "metric": "RCVD (Pcs)"},
        {"metric": "Remaining (Pcs)"},
        {"month": [FY_MONTH_LABELS[11]], "metric": "Monthly Incoming (Pcs)"},
        {"Fabricator": ["NOT A FABRICATOR"]},
    ]


@pytest.mark.parametrize("case", range(7))
def test_fabricator_dashboard(legacy, demo, tabs, case):
    sid = IDS["overview_fabricators"]
    ft = tabs["overview_fabricators"][0]
    parsed = fab.parse_fabricator(demo.get_values(sid, ft, True), demo.get_values(sid, ft, False))
    f = fab_cases(fab.split_base(parsed["df"])[2])[case]
    set_widgets(legacy, f)
    legacy._fab_body("Fabricator Report", SHEET_REGISTRY["overview_fabricators"], ft)
    new = fab.fabricator_dashboard(parsed, {"fabricator": f.get("Fabricator", []), "month": f.get("month", []),
                                            "metric": f.get("metric")})
    assert_table(legacy.rec.tables[0], new["tables"]["monthly"], f"fab monthly {f}")
    assert_table(legacy.rec.tables[1], new["tables"]["scorecard"], f"fab scorecard {f}")
    if new["matrix"] is None:
        assert len(legacy.rec.tables) == 2, "legacy drew a matrix the new API did not"
    else:
        assert_table(legacy.rec.tables[2], new["matrix"]["table"], f"fab matrix {f}")
    assert_kpis(legacy.rec.kpis[0], new["kpis"], f"fab KPIs {f}")
    old_kinds = [k for k, _ in legacy.rec.notices]
    assert new["check"]["kind"] in old_kinds


# ------------------------------------------------------------------------------------------------ fabric PO
def po_cases(parsed):
    d = parsed["d"]
    return [
        {},
        {"month": [FY_MONTH_LABELS[2]]},
        {"Vendor": sorted(d["vendor"].unique())[:2]},
        {"Order Type": ["REPEAT"], "Client": sorted(d["client"].unique())[:3]},
        {"Designer": ["ANAMIKA"], "Item": ["KURTA", "DRESS", "TOP"]},
        {"Status": ["PENDING", "PARTIAL RCVD"]},
    ]


@pytest.mark.parametrize("case", range(6))
def test_fabric_po_dashboard(legacy, demo, tabs, case):
    values = demo.get_values(IDS["fabric_po"], tabs["fabric_po"][0])
    parsed = fpo.parse_fabric_po(values, TODAY)
    old_d, _ = legacy.build_fabric_po(values)
    pd.testing.assert_frame_equal(old_d, parsed["d"])
    f = po_cases(parsed)[case]
    set_widgets(legacy, f)
    legacy._fabpo_body("Fabric PO", SHEET_REGISTRY["fabric_po"], tabs["fabric_po"][0])
    keymap = {"Vendor": "vendor", "Order Type": "order_type", "Client": "client", "Designer": "designer",
              "Item": "item", "Status": "status", "month": "month"}
    new = fpo.fabric_po_dashboard(parsed, {keymap[k]: v for k, v in f.items()})
    if new.get("empty_filtered"):
        assert not legacy.rec.tables
        return
    assert_table(legacy.rec.tables[0], new["tables"]["monthly"], f"po monthly {f}")
    assert_table(legacy.rec.tables[1], new["tables"]["vendors"], f"po vendors {f}")
    assert_table(legacy.rec.tables[2], new["tables"]["vendor_share"], f"po vendor share {f}")
    assert_kpis(legacy.rec.kpis[0], new["kpis"], f"po KPIs {f}")


# ------------------------------------------------------------------------------------------------ target
def target_cases(parsed):
    d = parsed["d"]
    return [
        {},
        {"month": [FY_MONTH_LABELS[1], FY_MONTH_LABELS[4]]},
        {"Designer": sorted(d["designer"].unique())[:2]},
        {"Item Name": ["KURTA", "DRESS"], "Order Type": ["REPEAT"]},
        {"Order By": sorted(d["order_by"].unique())[:1], "annual_cr": 42.0},
        {"Order Type": ["NEW"], "annual_cr": 0.0},
    ]


def _target_parsed(demo, tabs):
    sid = IDS["target_revenue"]
    new, rep = tabs["target_revenue"]
    return tgt.parse_target([("NEW", new, demo.get_values(sid, new), []),
                             ("REPEAT", rep, demo.get_values(sid, rep), [])])


@pytest.mark.parametrize("case", range(6))
def test_target_dashboard(legacy, demo, tabs, case):
    parsed = _target_parsed(demo, tabs)
    old_d, old_notes, _ = legacy.load_target_data(SHEET_REGISTRY["target_revenue"])
    pd.testing.assert_frame_equal(old_d.drop(columns=["image"]), parsed["d"].drop(columns=["image"]))
    f = target_cases(parsed)[case]
    set_widgets(legacy, f)
    legacy._target_body("Designer Target", SHEET_REGISTRY["target_revenue"])
    keymap = {"Designer": "designer", "Item Name": "item", "Order By": "order_by", "Order Type": "source",
              "month": "month"}
    new = tgt.target_dashboard(parsed, {keymap[k]: v for k, v in f.items() if k in keymap},
                               annual_cr=f.get("annual_cr", 50.2), today=TODAY)
    tables = list(legacy.rec.tables)
    assert_table(tables.pop(0), new["tracker"]["table"], f"target tracker {f}")
    assert_kpis(legacy.rec.kpis[0], new["tracker"]["kpis"], f"target tracker KPIs {f}")
    fl = new["filtered"]
    if not fl.get("empty"):
        for name in ("monthly", "designers", "items", "order_by"):
            assert_table(tables.pop(0), fl["tables"][name], f"target {name} {f}")
        assert_kpis(legacy.rec.kpis[1], fl["kpis"], f"target KPIs {f}")
        lines = legacy.fake.dataframes[0].reset_index(drop=True)
        assert_table(lines, fl["tables"]["lines"], f"target lines {f}")
    q = new["quality"]["rows"]
    if q is not None:
        assert_table(tables.pop(0), q, f"target quality {f}")
    assert not tables


# ------------------------------------------------------------------------------------------------ overview
@pytest.mark.parametrize("months", [[], [FY_MONTH_LABELS[0]], FY_MONTH_LABELS[3:6], [FY_MONTH_LABELS[11]]])
def test_overview_dashboard(legacy, demo, tabs, months):
    sources = {
        "tracker": (mst.parse_master(demo.get_values(IDS["tracker"], tabs["tracker"][0]))[0], None),
        "sample_summary": (smp.parse_samples(demo.get_values(IDS["sample_summary"], tabs["sample_summary"][0])), None),
        "overview_fabricators": (fab.parse_fabricator(
            demo.get_values(IDS["overview_fabricators"], tabs["overview_fabricators"][0], True),
            demo.get_values(IDS["overview_fabricators"], tabs["overview_fabricators"][0], False)), None),
        "fabric_po": (fpo.parse_fabric_po(demo.get_values(IDS["fabric_po"], tabs["fabric_po"][0]), TODAY), None),
    }
    set_widgets(legacy, {"month": months})
    legacy._overview_body()
    new = ovw.overview_dashboard(sources, months)
    sec = new["sections"]
    tables = list(legacy.rec.tables)
    kpis = list(legacy.rec.kpis)
    if "orders" in sec:
        for name in ("fabricators", "categories", "clients"):
            if name == "fabricators" and not sec["orders"]["tables"][name]["rows"]:
                continue                      # legacy shows a notice instead of an empty table here
            assert_table(tables.pop(0), sec["orders"]["tables"][name], f"overview orders {name} {months}")
        assert_kpis(kpis.pop(0), sec["orders"]["kpis"], f"overview order KPIs {months}")
    if "designers" in sec:
        assert_table(tables.pop(0), sec["designers"]["table"], f"overview designers {months}")
    if "stock" in sec:
        assert_kpis(kpis.pop(0), sec["stock"]["kpis"], f"overview stock KPIs {months}")
        assert_table(tables.pop(0), sec["stock"]["table"], f"overview stock {months}")
    if "po" in sec:
        assert_kpis(kpis.pop(0), sec["po"]["kpis"], f"overview PO KPIs {months}")
        assert_table(tables.pop(0), sec["po"]["tables"]["vendors"], f"overview PO vendors {months}")
        if sec["po"]["overdue_total"]:
            assert_table(tables.pop(0), sec["po"]["tables"]["overdue"], f"overview PO overdue {months}")
    if "samples" in sec:
        assert_kpis(kpis.pop(0), sec["samples"]["kpis"], f"overview sample KPIs {months}")
        assert_table(tables.pop(0), sec["samples"]["table"], f"overview samples {months}")
    assert not tables and not kpis
    # every alert of the old page has a counterpart with the same severity, in the same order
    new_kinds = [a["kind"] for a in new["alerts"]]
    assert [k for k, _ in legacy.rec.notices][:len(new_kinds)] == new_kinds
