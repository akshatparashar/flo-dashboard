"""FLO Future sheet: parsing (real layout and its quirks), the dashboard numbers, filters, the API route and the
Overview alert."""
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
    ["Keerti", "Team A", "Patola 2 Pc Russian Silk", "RV", "", 5, 5, 0, "Complete", D[10], "", "Rai Sir", "", ""],
    ["Charu", "Team A", "Vrij Bhumi Concept", "RV", "Summer", 11, 0, 11, "Not Updated", D[26], "", "Rai Sir"],
    ["Ayushi", "Team A", "Madhubani Collection Co-ord", "Gokul", "", "", 0, "", "In Progress", D[27], "", "Rai Sir",
     "", "Qty missing in source"],
    ["Ayushi", "Team A", "Hand Block Collection Shirt", "Gokul", "", 11, 0, 11, "Not Updated", "", "", "Rai Sir"],
    ["Deepika", "Team A", "Farshi 3 Pc", "RV", "", 4, 0, 4, "IN-HOUSE  PROCESS", D[16], "Overdue", "Rai Sir"],
    ["Jyoti", "Team B", "Vrij Bhumi Co-ord Set", "RV", "Summer", 6, 0, 6, "In-House Process", D[17], "", "Ayushi"],
    ["Krishna", "Team B", "Sanskruti Flower Print Co-ord Set", "Niharika", "", 2, 0, 2, "In-House Process", D[20]],
    ["Jagriti", "Team C", "AI Collection Mughal Sheet 1", "RV", "Summer", 15, 2, 13, "In-House Process", D[28], "",
     "Ayushi", "", "6 samples on 04-Nov-26"],
    ["Anjali", "Team C", "AI Collection Mughal Sheet 1", "RV", "Summer", 15, 2, 13, "Sampling Ordered", D[28], "",
     "Ayushi", "", "Same item also listed under Jagriti"],
    ["Pooja", "Team C", "Chateau Botanique Series", "", "", 8, 0, 8, "CAD In Process", D[28], "", "Ayushi"],
    ["", "", "", "", "", "", "", "", "", "", "", "", "", "", ""],
]
OUTSOURCE = [
    ["Designer", "Project / Collection", "Outsource Vendor", "Season", "Qty Promised", "Completed", "Pending", "Status",
     "Due Date", "Overdue", "Promised To", "Remark"],
    ["Ayushi", "Gauri Dayal OG 3 Pcs", "BSK", "Summer", 6, 0, 6, "PP Sample In Process", D[30], "", "Rai Sir"],
    ["Pooja", "Embroidery Collection 2", "Radhika", "Summer", 2, 0, 2, "Outsource Process", D[18], "", "Ayushi"],
]
VISITS_BLOCKS = [
    ["VISITS & MEETINGS"],
    ["Causative Milestone", "WE HAVE DONE MARKET VISIT FOR ACCESSORIES ONCE IN A MONTH"],
    ["Sr", "Promised Action ", "SEASON WISE", "QTY.", "", "(Promised) By Whom", "(Promised) to Whom",
     "(Promised) By When-Date", "Complete (marked as ‘X’ )", "STATUS", "REMARK"],
    [1], [2],
    ["Causative Milestone", "FACTORY/STORE VISIT SCHEDULE "],
    ["Sr", "Promised Action ", "TWICE IN MONTH", "QTY.", "", "(Promised) By Whom", "(Promised) to Whom",
     "(Promised) By When-Date", "Complete (marked as ‘X’ )", "STATUS", "REMARK"],
    [1, "WOMART", "", "", "", "MADHU/REETA JI/SUNITA JI", "Rai Sir", D[2], "X", "Done"],
    [2],
    ["Causative Milestone", "MEETING "],
    ["Sr", "Promised Action ", "", "QTY.", "", "(Promised) By Whom", "(Promised) to Whom", "(Promised) By When-Date",
     "Complete (marked as ‘X’ )", "STATUS", "REMARK"],
    [1, "FLO JURY + FLO FUTURE MEETING", "EVERY SATURDAY", "", "", "AYUSHI", "Rai Sir", D[14], "", ""],
    [2, "FLO JURY + FLO FUTURE MEETING", "EVERY SATURDAY", "", "", "AYUSHI", "Rai Sir", D[21], "", ""],
]
VISITS_FLAT = [
    ["Activity", "Type", "Frequency", "Owner", "Promised To", "Due Date", "Done", "Remark"],
    ["Womart factory / store visit", "Factory / Store Visit", "Twice a month", "Madhu", "Rai Sir", D[2], True, ""],
    ["FLO Jury + FLO Future meeting", "Meeting", "Every Saturday", "Ayushi", "Rai Sir", D[14], False, ""],
    ["Surat sampling visit", "Surat Visit", "Once a month", "", "", "", False, "Not planned yet"],
]


@pytest.fixture
def parsed():
    return ff.parse_flo_future({"samples": SAMPLES, "outsource": OUTSOURCE, "visits": VISITS_BLOCKS})


def kpis(d):
    return {k["id"]: k["value"] for k in d["kpis"]}


def test_parse_rows_and_quirks(parsed):
    s = parsed["samples"]
    assert len(s) == 11                                  # blank row dropped
    assert s["status"].tolist().count("In-House Process") == 4       # "IN-HOUSE  PROCESS" standardised
    mad = s[s["item"] == "Madhubani Collection Co-ord"].iloc[0]
    assert mad["qty"] == 0 and mad["qty_missing"]
    assert parsed["outsource"].set_index("designer").loc["Ayushi", "team"] == "Team A"   # team borrowed from samples


def test_numbers(parsed):
    d = ff.flo_future_dashboard(parsed, {}, TODAY)
    k = kpis(d)
    assert k["promised"] == 85 and k["completed"] == 9 and k["pending"] == 76
    assert k["done_pct"] == pytest.approx(9 / 85 * 100)
    assert k["overdue"] == 2                              # Farshi (16 Nov) and Vrij Bhumi Co-ord (17 Nov)
    assert k["due_soon"] == 2                             # Krishna 20 Nov and Charu 26 Nov: open, within 7 days
    assert k["not_updated"] == 2
    assert k["out_promised"] == 8 and k["out_pending"] == 8
    assert d["period"] == "November 2026"
    rows = {r[0]: r for r in d["tables"]["designers"]["rows"]}
    cols = [c["label"] for c in d["tables"]["designers"]["columns"]]
    assert rows["TOTAL"][cols.index("Promised (Pcs)")] == 85
    assert rows["Ayushi"][cols.index("Outsource (Pcs)")] == 6
    assert d["attention"][0]["designer"] == "Deepika" and d["attention"][0]["level"] == "error"


def test_items_sorted_late_first_and_done_last(parsed):
    t = ff.flo_future_dashboard(parsed, {}, TODAY)["tables"]["items"]
    when = [r[[c["label"] for c in t["columns"]].index("When")] for r in t["rows"]]
    assert when[0] == "3 days late" and when[-1] == "Done"
    assert t["columns"][0]["label"] == "Collection / Sample"          # not "Designer": rows are items, not people


def test_checks(parsed):
    texts = " ".join(c["text"] for c in ff.flo_future_dashboard(parsed, {}, TODAY)["checks"])
    assert "Qty Promised is blank" in texts and "Madhubani" in texts
    assert "AI Collection Mughal Sheet 1" in texts and "Jagriti" in texts and "Anjali" in texts
    assert "no due date" in texts and "no vendor" in texts


def test_filters(parsed):
    d = ff.flo_future_dashboard(parsed, {"team": ["Team B"]}, TODAY)
    assert kpis(d)["promised"] == 8
    d = ff.flo_future_dashboard(parsed, {"designer": ["Keerti"]}, TODAY)
    assert kpis(d)["promised"] == 13 and kpis(d)["completed"] == 5
    assert len(d["tables"]["designers"]["rows"]) > 2                    # designer table ignores the designer filter
    d = ff.flo_future_dashboard(parsed, {"vendor": ["Niharika"]}, TODAY)
    assert kpis(d)["promised"] == 2
    assert d["options"]["month"] == ["November-26"]


def test_visits_block_layout(parsed):
    d = ff.flo_future_dashboard(parsed, {}, TODAY)
    k = kpis(d)
    assert k["visits_done"] == 1 and k["unplanned"] == 1
    rows = d["tables"]["visits"]["rows"]
    status = {(r[0], r[5]): r[6] for r in rows}
    assert status[("FLO Jury + FLO Future Meeting", "14/11/2026")] == "Not marked done"
    assert status[("FLO Jury + FLO Future Meeting", "21/11/2026")] == "Upcoming"
    assert status[("Womart", "02/11/2026")] == "Done"
    assert any(r[0] == "Market Visit for Accessories" and r[6] == "Not planned" for r in rows)


def test_visits_flat_layout():
    p = ff.parse_flo_future({"samples": SAMPLES, "visits": VISITS_FLAT})
    d = ff.flo_future_dashboard(p, {}, TODAY)
    status = {r[0]: r[6] for r in d["tables"]["visits"]["rows"]}
    assert status["Womart factory / store visit"] == "Done"
    assert status["FLO Jury + FLO Future meeting"] == "Not marked done"
    assert status["Surat sampling visit"] == "No date"


def test_columns_found_by_header_not_position():
    moved = [[r[i] if i < len(r) else "" for i in (2, 0, 1, 5, 6, 8, 9, 3)] for r in SAMPLES]
    d = ff.flo_future_dashboard(ff.parse_flo_future({"samples": moved}), {}, TODAY)
    assert kpis(d)["promised"] == 85 and kpis(d)["overdue"] == 2


def test_empty_and_missing_tabs():
    d = ff.flo_future_dashboard(ff.parse_flo_future({}), {}, TODAY)
    assert d["empty"] and d["notices"]
    d = ff.flo_future_dashboard(ff.parse_flo_future({"samples": [["no", "header"], [1, 2]]}), {}, TODAY)
    assert d["empty"]


@pytest.mark.parametrize("raw,want", [("COMPLETE", "Complete"), ("cad in-process", "CAD In Process"),
                                      ("IN-HOUSE  PROCESS", "In-House Process"), ("", "Not Updated"),
                                      ("Waiting on fabric", "Waiting on fabric")])
def test_status_names(raw, want):
    assert ff.canon_status(raw) == want


def test_overview_alert(parsed):
    a = ff.overview_alert(parsed, TODAY)            # 2 sample items + 1 outsource project (Pooja, 18 Nov) overdue
    assert a["area"] == "promises" and "3 promised items overdue" == a["title"] and "Farshi 3 Pc" in a["text"]


def test_api_route_and_overview(monkeypatch):
    settings = Settings(data_source="demo")
    store = DataStore(DemoSheetSource(), settings)
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    monkeypatch.setattr(main, "get_store", lambda: store)
    c = TestClient(main.app)
    body = c.get("/api/flo-future").json()
    assert body["meta"]["sources"][0]["source"] == "flo_future"
    assert {"designers", "teams", "vendors", "items", "outsource", "visits", "status"} <= set(body["tables"])
    team = body["options"]["team"][0]
    sub = c.get("/api/flo-future", params={"team": team}).json()
    assert kpis(sub)["promised"] <= kpis(body)["promised"]
    assert any(a["area"] == "promises" for a in c.get("/api/overview").json()["alerts"])
    assert store.status()["flo_future"]["ok"]
