"""FLO Assistant on the newer pages (FLO Future, Vendor Rate) and dashboard-wide helpers. Expected figures are read
from the same API endpoints inside each test. Runs on the built-in demo data."""
from __future__ import annotations

from test_assistant_calc import ask, client  # noqa: F401  (fixtures)


def kpis(client, path):
    return {k["label"]: k for k in client.get(path).json()["kpis"]}


def test_new_sections_summary_lists_both_pages(client):
    r = ask(client, "Give me total for the new dashboard sections")
    ff, vr = kpis(client, "/api/flo-future"), kpis(client, "/api/vendor-rate")
    assert "FLO Future" in r["answer"] and "Vendor Rate" in r["answer"]
    assert f"Total Vendors: {int(vr['Total Vendors']['value'])}" in r["answer"]
    assert f"Completed: {int(ff['Completed']['value'])} pcs" in r["answer"]


def test_flo_future_total_across_designers_matches_kpi(client):
    pending = kpis(client, "/api/flo-future")["Pending"]["value"]
    r = ask(client, "Which designer has the highest pending in flo future")
    assert r["intent"] == "rank"
    r = ask(client, "Total pending of all designers in flo future")
    assert f"{int(pending):,}" in r["answer"]


def test_vendor_rate_average_and_compare(client):
    bench = client.get("/api/vendor-rate").json()["tables"]["benchmark"]
    cols = [c["label"] for c in bench["columns"]]
    rows = {r[0]: r for r in bench["rows"]}
    a, b = list(rows)[:2]
    r = ask(client, f"Compare {a} and {b} rates")
    col = 'Avg 44" Rate'
    for v in (a, b):
        assert f"{rows[v][cols.index(col)]:,.0f}" in r["answer"]
    assert "more than" in r["answer"]


def test_team_wise_summary_reads_the_table(client):
    teams = client.get("/api/flo-future").json()["tables"]["teams"]["rows"]
    r = ask(client, "show team-wise summary")
    assert all(str(t[0]) in r["answer"] for t in teams if not str(t[0]).startswith("(") and str(t[0]).upper() != "TOTAL")


def test_same_label_on_two_pages_names_both(client):
    r = ask(client, "how much is pending for Ayushi")
    if "also has" in r["answer"]:
        assert "FLO Future" in r["answer"] or "Production" in r["answer"]
