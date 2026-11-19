"""Parity: the FLO Future page must show exactly what the old Streamlit "FLO Future" tab showed
(github.com/design355/sample-production-dashboard, kept as legacy/streamlit_app.py).

The old tab runs headless (conftest.legacy) next to the new dashboard function on the same grids, the same "today"
and the same filters. Compared: every KPI tile, every cell of the designer table (same rows, same order), the sample
list order and totals, and the visits & meetings summary. Runs on the demo grids, or on the real sheet with
PARITY_SOURCE=google.
"""
from __future__ import annotations

import pandas as pd
import pytest

from app.config import SHEET_REGISTRY
from app.dashboards import flo_future as ff
from app.store import DataStore
from app.config import Settings
from tests.conftest import TODAY, set_widgets
from tests.test_parity import assert_table

SID = SHEET_REGISTRY["flo_future"]["id"]


@pytest.fixture(scope="module")
def grids(demo):
    tabs = DataStore(demo, Settings()).source_tabs("flo_future")
    return {part: (demo.get_values(SID, t) if t else []) for part, t in zip(("samples", "visits", "outsource"), tabs)}


def run_legacy(legacy, values):
    """Runs the old FLO Future tab; returns what it drew."""
    seen = {}
    legacy.ff_item_table = lambda x, **kw: seen.setdefault("items", x.copy())
    legacy._ff_designer_chart = lambda dsc, x_nd: seen.setdefault("chart", dsc.copy())
    legacy._ff_visits_chart = lambda va, vb, vtab, vs=None: seen.setdefault("visits", vs)
    set_widgets(legacy, values)
    cfg = next(c for c in legacy.SHEET_REGISTRY.values() if c.get("type") == "flo_future")
    legacy._ff_body("FLO Future", cfg, legacy.resolve_source_tab(cfg, name_regex=ff.SAMPLE_TAB_REGEX))
    return seen


def old_tiles(p):
    """The new payload written the way the old tab wrote its KPI tiles."""
    s = p["summary"]

    def f(v):
        return f"{v:,.0f}"
    mp, lo, vt = s["most_pending"], s["longest_overdue"], s["visits"]
    tiles = [("Target Qty (Promised)", f"{f(s['target'])} Pcs"), ("Completed", f"{f(s['completed'])} Pcs"),
             ("Pending", f"{f(s['pending'])} Pcs"), ("Completion %", f"{s['done_pct']:.1f}%"),
             ("Overdue (Date Passed)", f"{s['overdue_items']} Items · {f(s['overdue_pcs'])} Pcs"),
             ("Due in Next 3 Days", f"{s['due_soon']} Items · {f(s['due_soon_pcs'])} Pcs"),
             ("⚠ Most Pending", f"{mp['designer']} ({f(mp['pending'])} Pcs)" if mp else "None"),
             ("⏰ Longest Overdue", f"{lo['days']} Days · {lo['designer']}" if lo else "None")]
    if vt["required"]:
        tiles.append(("Visits & Meetings Done", f"{vt['done']} / {vt['required']}"))
    return tiles


def cases(parsed):
    d = parsed["samples"]
    team_order, des_order, statuses = ff.orders(d)
    return [
        {},
        {"Designer": des_order[:1]},
        {"Designer": des_order[1:3]},
        {"Team": team_order[:1]},
        {"Status": statuses[:2]},
        {"Due Status": ["Overdue"]},
        {"Due Status": ["Due in 4-7 Days", "No Due Date"]},
        {"Team": team_order[-1:], "Status": statuses[-1:]},
        {"Designer": ["Nobody"]},
    ]


def test_samples_rows_identical(legacy, grids):
    old, _ = legacy.build_ff_samples(grids["samples"], TODAY)
    new = ff.parse_flo_future(grids, TODAY)["samples"]
    pd.testing.assert_frame_equal(old, new[old.columns], check_dtype=False)


def test_visits_identical(legacy, grids):
    oa, ob = legacy.build_ff_visits(grids["visits"], TODAY)
    p = ff.parse_flo_future(grids, TODAY)
    pd.testing.assert_frame_equal(ob, p["blocks"], check_dtype=False)
    pd.testing.assert_frame_equal(legacy.ff_visit_summary(oa, ob), ff.ff_visit_summary(p["visits"], p["blocks"]),
                                  check_dtype=False)


def test_dashboard_matches_old_tab(legacy, grids):
    parsed = ff.parse_flo_future(grids, TODAY)
    for case in cases(parsed):
        f = {"designer": case.get("Designer", []), "team": case.get("Team", []), "status": case.get("Status", []),
             "due": case.get("Due Status", [])}
        legacy.rec.kpis.clear()
        legacy.rec.tables.clear()
        seen = run_legacy(legacy, case)
        mine = ff.flo_future_dashboard(parsed, f)
        where = f"FLO Future {case}"
        if mine["no_match"]:
            assert not legacy.rec.kpis, where
            continue
        assert legacy.rec.kpis == [old_tiles(mine)], where
        assert_table(legacy.rec.tables[0], mine["tables"]["designers"], where + " designer table")
        items = mine["tables"]["items"]
        old_items = seen["items"]
        assert [r[0] for r in items["rows"][:-1]] == list(old_items["item"]), where + " sample order"
        assert [r[1] for r in items["rows"][:-1]] == list(old_items["designer"]), where + " sample designers"
        s = legacy.ff_stats(old_items)
        tot = items["rows"][-1]
        assert tot[0] == "TOTAL" and (tot[5], tot[6], tot[7]) == (s["Target Qty"], s["Completed"], s["Pending"])
        chart = mine["charts"]["designers"]
        exp = seen["chart"].sort_values(["Target Qty", "Designer"], ascending=[False, True])
        assert chart["categories"] == list(exp["Designer"]), where + " chart order"
        total = [sum(v) for v in zip(*[s_["values"] for s_ in chart["series"]])]
        assert total == pytest.approx(list(exp["Completed"] + exp["Pending"])), where + " chart stacks = target"
        if seen.get("visits") is not None:
            assert_table(seen["visits"], mine["visits"]["summary"], where + " visits")
