"""FLO Future: the old dashboard's rules on hand-made rows (the full side-by-side check with the old Streamlit tab is
tests/test_parity_flo_future.py), plus the API route, the Overview highlights and the extra sections."""
from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import main
from app.config import Settings
from app.dashboards import flo_future as ff
from app.sources.demo import DemoSheetSource
from app.store import DataStore

TODAY = pd.Timestamp("2026-11-19")
D = {d: (pd.Timestamp(f"2026-11-{d:02d}") - pd.Timestamp("1899-12-30")).days for d in range(1, 31)}  # serials

SAMPLES = [
    ["Designer", "Team", "Collection / Sample", "Vendor", "Season", "Qty Promised", "Completed", "Pending", "Status",
     "Due Date", "Overdue", "Promised To", "Contact", "Remark", "Key (auto)"],
    ["Keerti", "Team A", "Indigo K2P Muslin", "RV", "", 8, 0, 8, "Not Started", D[28], "", "Rai Sir", "", "", "K|1"],
    ["Keerti", "Team A", "Patola 2 Pc Russian Silk", "RV", "", 5, 5, 0, "Complete", D[10], "", "Rai Sir"],
    ["Charu", "Team A", "Vrij Bhumi Concept", "RV", "Summer", 11, 0, 11, "", D[19], "", "Rai Sir"],
    ["Ayushi", "Team A", "Madhubani Collection Co-ord", "Gokul", "", "", 0, "", "In Progress", D[27], "", "Rai Sir",
     "", "Qty missing in source"],
    ["Ayushi", "Team A", "Hand Block Collection Shirt", "Gokul", "", 11, 0, 11, "Not Updated", "", "", "Rai Sir"],
    ["Deepika", "Team A", "Farshi 3 Pc", "RV", "", 4, 0, 4, "IN-HOUSE  PROCESS", D[16], "Overdue", "Rai Sir"],
    ["jyoti", "team b", "Vrij Bhumi Co-ord Set", "RV", "Summer", 6, 6, 0, "Corrections", D[17], "", "Ayushi"],
    ["Krishna", "", "Sanskruti Flower Print Co-ord Set", "Niharika", "", 2, 0, 2, "Waiting fabric", D[20]],
    ["Jagriti", "Team C", "AI Collection Mughal Sheet 1", "RV", "Summer", 15, 2, 13, "Complete", D[28]],
    ["Anjali", "Team C", "AI Collection Mughal Sheet 1", "RV", "Summer", 15, 2, 13, "Sampling Ordered", D[22]],
    ["", "", "Orphan row", "", "", 3, 0, 3, "", D[20]],                       # no designer -> skipped (old rule)
    ["Pooja", "Team C", "", "", "", "", "", "", "", ""],                       # nothing promised -> skipped
]
OUTSOURCE = [
    ["Designer", "Project / Collection", "Outsource Vendor", "Season", "Qty Promised", "Completed", "Pending", "Status",
     "Due Date", "Overdue", "Promised To", "Remark"],
    ["Ayushi", "Gauri Dayal OG 3 Pcs", "BSK", "Summer", 6, 0, 6, "PP Sample In Process", D[30], "", "Rai Sir"],
]
VISITS = [
    ["VISITS & MEETINGS"],
    ["Causative Milestone", "WE HAVE DONE MARKET VISIT FOR ACCESSORIES ONCE IN A MONTH"],
    ["Sr", "Promised Action ", "SEASON WISE", "QTY.", "", "(Promised) By Whom", "(Promised) to Whom",
     "(Promised) By When-Date", "Complete (marked as ‘X’ )", "STATUS", "REMARK"],
    [1], [2],
    ["Causative Milestone", "FACTORY/STORE VISIT SCHEDULE "],
    ["Sr", "Promised Action ", "TWICE IN MONTH", "QTY.", "", "(Promised) By Whom", "(Promised) to Whom",
     "(Promised) By When-Date", "Complete (marked as ‘X’ )", "STATUS", "REMARK"],
    [1, "WOMART", "", "", "", "MADHU", "Rai Sir", D[2], "X", "Done"],
    ["Causative Milestone", "MEETING "],
    ["Sr", "Promised Action ", "", "QTY.", "", "(Promised) By Whom", "(Promised) to Whom", "(Promised) By When-Date",
     "Complete (marked as ‘X’ )", "STATUS", "REMARK"],
    [1, "FLO JURY + FLO FUTURE MEETING", "EVERY SATURDAY", "", "", "AYUSHI", "Rai Sir", D[14], "", ""],
    [2, "FLO JURY + FLO FUTURE MEETING", "EVERY SATURDAY", "", "", "AYUSHI", "Rai Sir", D[19], "", ""],
    [3, "FLO JURY + FLO FUTURE MEETING", "EVERY SATURDAY", "", "", "AYUSHI", "Rai Sir", D[21], "", "Rescheduled"],
]


@pytest.fixture
def parsed():
    return ff.parse_flo_future({"samples": SAMPLES, "outsource": OUTSOURCE, "visits": VISITS}, TODAY)


def kpis(d):
    return {k["id"]: k["value"] for k in d["kpis"]}


def test_rows_follow_the_old_rules(parsed):
    s = parsed["samples"].set_index("item")
    assert len(parsed["samples"]) == 10                              # no-designer and empty rows skipped
    assert s.loc["Farshi 3 Pc", "status"] == "In-House Process"      # case / spaces ignored
    assert s.loc["Sanskruti Flower Print Co-ord Set", "status"] == "Waiting Fabric"  # unknown -> title case
    assert s.loc["Vrij Bhumi Concept", "status"] == "Not Updated"    # blank -> Not Updated
    assert s.loc["Sanskruti Flower Print Co-ord Set", "team"] == "(No Team)"
    assert s.loc["Vrij Bhumi Co-ord Set", "designer"] == "Jyoti" and s.loc["Vrij Bhumi Co-ord Set", "team"] == "Team B"
    mad = s.loc["Madhubani Collection Co-ord"]
    assert mad["qty_blank"] and mad["pending"] == 0
    # Complete by status but 13 pcs still open: pending stays 13, never overdue (old rule)
    jag = parsed["samples"][parsed["samples"]["designer"] == "Jagriti"].iloc[0]
    assert jag["is_complete"] and jag["pending"] == 13 and jag["due_bucket"] == "Completed"
    # Completed >= qty counts as complete even with another status
    assert s.loc["Vrij Bhumi Co-ord Set", "due_bucket"] == "Completed"


def test_due_buckets(parsed):
    b = parsed["samples"].set_index("item")["due_bucket"]
    assert b["Farshi 3 Pc"] == "Overdue"
    assert b["Vrij Bhumi Concept"] == "Due Today"
    assert b["Sanskruti Flower Print Co-ord Set"] == "Due in 1-3 Days"
    assert b["Indigo K2P Muslin"] == "Due Later (> 7 Days)"
    assert b["Hand Block Collection Shirt"] == "No Due Date"


def test_kpis(parsed):
    d = ff.flo_future_dashboard(parsed, {})
    k = kpis(d)
    assert k["target"] == 77 and k["completed"] == 15 and k["pending"] == 62
    assert k["overdue"] == 1 and k["due_soon"] == 3 and k["longest_overdue"] == "3 days"
    assert k["most_pending"] in ("Jagriti", "Anjali")              # both 13 pcs; first in designer order wins
    assert k["visits_done"] == "1 / 6"     # market 1 + factory 2 + meetings 3 planned; done: Womart


def test_filters_and_designer_table(parsed):
    d = ff.flo_future_dashboard(parsed, {"team": ["Team C"]})
    assert kpis(d)["target"] == 30
    d = ff.flo_future_dashboard(parsed, {"designer": ["Keerti"]})
    assert kpis(d)["target"] == 13
    assert len(d["tables"]["designers"]["rows"]) > 2               # designer filter not applied to the comparison
    d = ff.flo_future_dashboard(parsed, {"due": ["Overdue"]})
    assert kpis(d)["target"] == 4 and d["follow_up"][0]["item"] == "Farshi 3 Pc"
    d = ff.flo_future_dashboard(parsed, {"designer": ["Nobody"]})
    assert d["no_match"]
    assert d["options"]["due"] == ff.FF_DUE_BUCKETS
    assert d["options"]["team"][-1] == "(No Team)"


def test_items_most_urgent_first(parsed):
    t = ff.flo_future_dashboard(parsed, {})["tables"]["items"]
    cols = [c["label"] for c in t["columns"]]
    first = [r[cols.index("Days Left")] for r in t["rows"][:3]]
    assert first == ["3 days late", "Due today", "1 day left"]
    assert t["rows"][-1][0] == "TOTAL" and t["rows"][-1][cols.index("Qty")] == 77
    assert t["rows"][[r[0] for r in t["rows"]].index("Madhubani Collection Co-ord")][cols.index("Qty")] is None


def test_visits(parsed):
    v = ff.flo_future_dashboard(parsed, {})["visits"]
    rows = {r[0]: r for r in v["summary"]["rows"]}
    assert rows["Market Visit (Accessories)"][1:3] == [1, 0]          # required 1, planned 0
    assert rows["Factory / Store Visit"][1:4] == [2, 1, 1]
    assert rows["Meetings"][1:6] == [3, 3, 0, 1, 1]                    # 14th missed, 19th today, 21st rescheduled
    assert v["chart"]["flags"][0] == "Not planned"


def test_checks_and_outsource(parsed):
    d = ff.flo_future_dashboard(parsed, {})
    text = " ".join(c["text"] for c in d["checks"])
    assert "Qty Promised is blank" in text and "AI Collection Mughal Sheet 1" in text and "no due date" in text
    out = d["tables"]["outsource"]
    assert out["rows"][0][0] == "Gauri Dayal OG 3 Pcs" and out["rows"][0][2] == "Team A"
    assert kpis(d)["target"] == 77                                    # outsource never changes the Samples numbers


def test_missing_tabs():
    d = ff.flo_future_dashboard(ff.parse_flo_future({}, TODAY), {})
    assert d["empty"] and len(d["notices"]) == 2
    p = ff.parse_flo_future({"samples": SAMPLES}, TODAY)
    assert "visits_done" not in kpis(ff.flo_future_dashboard(p, {}))


def test_overview_highlights(parsed):
    h = ff.overview_highlights(parsed)
    assert h["alert"]["area"] == "promises" and h["alert"]["title"] == "1 promised sample overdue"
    assert "Farshi 3 Pc" in h["alert"]["text"]
    assert {k["id"] for k in h["kpis"]} == {"target", "done_pct", "overdue", "due_soon", "visits_done"}
    page = ff.flo_future_dashboard(parsed, {})
    assert {k["id"]: k["value"] for k in h["kpis"]}["target"] == kpis(page)["target"]


def test_api_route_and_overview(monkeypatch):
    settings = Settings(data_source="demo")
    store = DataStore(DemoSheetSource(), settings)
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    monkeypatch.setattr(main, "get_store", lambda: store)
    c = TestClient(main.app)
    body = c.get("/api/flo-future").json()
    assert body["meta"]["sources"][0]["source"] == "flo_future"
    assert {"designers", "items", "outsource"} <= set(body["tables"])
    team = body["options"]["team"][0]
    sub = c.get("/api/flo-future", params={"team": team, "due": "Overdue"}).json()
    assert kpis(sub)["target"] <= kpis(body)["target"]
    ov = c.get("/api/overview").json()
    assert any(a["area"] == "promises" for a in ov["alerts"])
    assert ov["sections"]["flo_future"]["kpis"][0]["value"] == kpis(body)["target"]
    assert store.status()["flo_future"]["tabs"] == ["Samples", "Visits & Meetings", "Outsource Projects"]
