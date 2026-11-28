"""Daily Delegation dashboard: the "Daily Schedule" tab. The grid is made up but has the quirks of the real tab
(dates as text, odd casing and stray spaces, blank statuses, empty template rows below the data)."""
import pytest

from app.dashboards import daily_delegation as ddl
from tests.test_api import make_client

HEAD = ["Date", "Day", "Task / Meeting / Follow-up", "Responsible Person", "Status", "Remarks"]
GRID = [
    ["SIR'S DAILY SCHEDULE"], ["One row per time slot."], ["Today:", 46350], HEAD,
    ["20-11-2026", "", "Prepare sheet", "Asha", "Completed", ""],
    ["20-11-2026", "", " Appointment   letters ", "rajni mam", "Awaiting Approval", "needs a signature"],
    ["20-11-2026", "", "Book tickets", "Monu Sir", "in progress", ""],
    ["22-11-2026", "", "Order supplies", "arihant sir", "Pending", ""],
    ["22-11-2026", "", "Follow up with lot", "Arihant Sir", "Pending", ""],
    ["22-11-2026", "", "Print material", "Arihant Sir ", "Completed", ""],
    ["25-11-2026", "", "Today's call", "Asha", "Pending", ""],
    ["", "", "", "", "", ""], ["", "", "", "", "", ""],
]
TODAY = "2026-11-25"


@pytest.fixture(scope="module")
def parsed():
    return ddl.parse_daily_schedule(GRID)


def kp(d):
    return {k["id"]: k for k in d["kpis"]}


def test_cleaning(parsed):
    d = parsed["rows"]
    assert len(d) == 7                                              # empty template rows are skipped
    assert sorted(d["person"].unique()) == ["Arihant Sir", "Asha", "Monu Sir", "Rajni Mam"]   # casing / stray spaces
    assert "Appointment letters" in set(d["task"])                  # whitespace collapsed
    assert set(d["status"]) == {"Completed", "Awaiting Approval", "In Progress", "Pending"}
    assert str(d["date"].iloc[0].date()) == "2026-11-20"            # text dd-mm-yyyy


def test_kpis_and_ageing(parsed):
    r = ddl.daily_delegation_dashboard(parsed, {}, today=TODAY)
    k = kp(r)
    assert k["total"]["value"] == 7 and k["completed"]["value"] == 2 and k["pending"]["value"] == 3
    assert k["in_progress"]["value"] == 1 and k["awaiting"]["value"] == 1 and k["people"]["value"] == 4
    assert k["oldest"]["value"] == 5 and "today" in k["total"]["hint"]
    ageing = {a["label"]: a["value"] for a in r["charts"]["ageing"]}
    assert ageing == {"Today": 1, "1-2 days": 0, "3-5 days": 4, "6+ days": 0}
    assert r["summary"]["done_pct"] == pytest.approx(28.6, abs=0.1) and r["summary"]["today"] == 1


def test_person_and_date_tables(parsed):
    r = ddl.daily_delegation_dashboard(parsed, {}, today=TODAY)
    persons = {row[0]: row for row in r["tables"]["persons"]["rows"]}
    assert persons["Arihant Sir"][1:3] == [3, 1] and persons["Arihant Sir"][6] == 2          # tasks, completed, open
    assert r["tables"]["persons"]["rows"][-1][0] == "TOTAL"
    dates = r["tables"]["dates"]["rows"]
    assert [x[0] for x in dates] == ["20 Nov 2026", "22 Nov 2026", "25 Nov 2026", "TOTAL"] and dates[0][1] == "Fri"
    assert r["charts"]["by_person"]["categories"][0] == "Arihant Sir"                        # most tasks first


def test_attention_lists_old_open_and_awaiting(parsed):
    r = ddl.daily_delegation_dashboard(parsed, {}, today=TODAY)
    tasks = [row[0] for row in r["tables"]["attention"]["rows"]]
    assert "Appointment letters" in tasks and "Today's call" not in tasks and "Prepare sheet" not in tasks
    assert r["tables"]["tasks"]["rows"][0][4] != "Completed"                                  # open tasks first


def test_filters(parsed):
    day = ddl.daily_delegation_dashboard(parsed, {"date": ["22 Nov 2026"]}, today=TODAY)
    assert kp(day)["total"]["value"] == 3
    who = ddl.daily_delegation_dashboard(parsed, {"person": ["Asha"], "status": ["Pending"]}, today=TODAY)
    assert kp(who)["total"]["value"] == 1
    text = ddl.daily_delegation_dashboard(parsed, {"q": ["signature"]}, today=TODAY)
    assert kp(text)["total"]["value"] == 1
    assert ddl.daily_delegation_dashboard(parsed, {"q": ["zzz"]}, today=TODAY)["no_match"] is True


def test_insights_are_sentences(parsed):
    r = ddl.daily_delegation_dashboard(parsed, {}, today=TODAY)
    assert r["insights"][0].startswith("2 of 7 tasks are completed")
    assert any("Arihant Sir carries the most work" in s for s in r["insights"])
    assert any("wait for Sir's approval" in s for s in r["insights"])


def test_sheet_checks():
    g = [list(r) for r in GRID[:4]] + [
        ["", "", "No date task", "Asha", "Pending", ""],
        ["20-11-2026", "", "No status task", "Asha", "", ""],
        ["20-11-2026", "", "No person task", "", "Pending", ""],
        ["20-11-2026", "", "Dup", "Asha", "Pending", ""], ["20-11-2026", "", "Dup", "Asha", "Pending", ""],
        ["20-11-2026", "", "Odd status", "Asha", "Maybe", ""],
    ]
    r = ddl.daily_delegation_dashboard(ddl.parse_daily_schedule(g), {}, today=TODAY)
    text = " ".join(c["text"] for c in r["checks"])
    for part in ("no valid date", "no status", "no Responsible Person", "repeat the same date", "Unknown status"):
        assert part in text
    assert "(No date)" in r["options"]["date"] and "Status Not Set" in r["options"]["status"]


def test_empty_and_headerless():
    assert ddl.daily_delegation_dashboard(ddl.parse_daily_schedule([["nothing"]]), {})["empty"]
    assert ddl.daily_delegation_dashboard(ddl.parse_daily_schedule(GRID[:4]), {})["empty"]


def test_api(monkeypatch):
    client, _ = make_client(monkeypatch)
    body = client.get("/api/daily-delegation").json()
    assert body["summary"]["tasks"] > 0 and body["tables"]["tasks"]["rows"] and body["insights"]
    some = body["options"]["person"][0]
    r = client.get("/api/daily-delegation", params={"person": some, "q": "a"})
    assert r.status_code == 200
    assert "daily_delegation" in client.get("/api/status").json().get("sources", {"daily_delegation": 1})


def test_reads_only_the_daily_schedule_tab(monkeypatch):
    """The dashboard must never fall back to another tab of the sheet."""
    from app.config import Settings
    from app.sources.demo import DAILY_DELEGATION_ID, DemoSheetSource
    from app.store import DataStore

    class OnlyOtherTabs(DemoSheetSource):
        def list_tabs(self, sheet_id):
            return [("How to Use", 1), ("Daily Delegation Tracker", 2)] if sheet_id == DAILY_DELEGATION_ID else super().list_tabs(sheet_id)

    ds = DataStore(OnlyOtherTabs(), Settings(data_source="demo")).dataset("daily_delegation")
    assert ds.data is None and "Daily Schedule" in ds.error

    asked = []

    class Spy(DemoSheetSource):
        def get_values(self, sheet_id, tab, formatted=False):
            if sheet_id == DAILY_DELEGATION_ID:
                asked.append(tab)
            return super().get_values(sheet_id, tab, formatted)

    assert DataStore(Spy(), Settings(data_source="demo")).dataset("daily_delegation").data is not None
    assert set(asked) == {"Daily Schedule"}


def test_todays_pending_block(parsed):
    r = ddl.daily_delegation_dashboard(parsed, {}, today=TODAY)["today_pending"]
    assert r["date"] == "25 Nov 2026" and r["today_total"] == 1
    assert [(t["task"], t["person"], t["status"]) for t in r["today"]] == [("Today's call", "Asha", "Pending")]
    assert len(r["carried"]) == 4 and r["carried"][0]["age"] == 5                      # oldest first
    assert all(t["status"] != "Completed" for t in r["today"] + r["carried"])
    # the date and status filters must not hide today's work; the person filter still applies
    f = ddl.daily_delegation_dashboard(parsed, {"date": ["20 Nov 2026"], "status": ["Completed"], "person": ["Asha"]}, today=TODAY)
    assert [t["task"] for t in f["today_pending"]["today"]] == ["Today's call"] and f["today_pending"]["carried"] == []
    quiet = ddl.daily_delegation_dashboard(parsed, {}, today="2026-12-30")["today_pending"]
    assert quiet["today"] == [] and quiet["today_total"] == 0 and len(quiet["carried"]) == 5


# the layout since 28 Nov 2026: no "Date" header, the "Day" column holds the dates
DAY_HEAD = ["Day", "Task / Meeting / Follow-up", "Responsible Person", "Status", "Remarks"]


@pytest.mark.parametrize("first,second", [("20-Nov-2026", "27-Nov-2026"), (46346, 46353)])    # text, or sheet serials
def test_dates_under_a_day_header(first, second):
    parsed = ddl.parse_daily_schedule([["SIR'S SCHEDULE"], ["28-Nov-2026 (Saturday)", "0 item(s) scheduled for today"],
                                       DAY_HEAD, [first, "Prepare sheet", "Asha", "Completed"],
                                       [second, "Call the printer", "arihant sir", "Pending", "urgent"], [""] * 5])
    d = parsed["rows"]
    assert parsed["problems"] == [] and list(d["task"]) == ["Prepare sheet", "Call the printer"]
    assert [str(x.date()) for x in d["date"]] == ["2026-11-20", "2026-11-27"]
    r = ddl.daily_delegation_dashboard(parsed, {}, today="2026-11-28")
    assert r["options"]["date"] == ["20 Nov 2026", "27 Nov 2026"] and kp(r)["total"]["value"] == 2


def test_a_day_column_of_weekday_names_is_not_read_as_dates():
    parsed = ddl.parse_daily_schedule([DAY_HEAD, ["Fri", "Prepare sheet", "Asha", "Pending", ""]])
    assert len(parsed["rows"]) == 1 and parsed["rows"]["date"].isna().all()


def test_a_changed_layout_says_so():
    r = ddl.daily_delegation_dashboard(ddl.parse_daily_schedule([["When", "What", "Who"]]), {}, today=TODAY)
    assert r["empty"] and "header row was not found" in r["notices"][0]["text"]
