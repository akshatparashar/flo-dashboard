"""Page routing, page summaries and duplicate-heading checks, driven by the 16 regression questions.
Every expected value is read from the page's API in the same run (demo data); the page link is checked too."""
from __future__ import annotations

import re

import pytest

from app.assistant import fmt
from test_assistant_calc import client  # noqa: F401  (fixture)


def chat(client, message, conv=None):
    r = client.post("/api/chat", json={"message": message, "conversation_id": conv})
    assert r.status_code == 200, r.text
    return r.json()


def api(client, path, **params):
    return client.get(path, params=params).json()


def kpi(body, label):
    return next(k["value"] for k in body["kpis"] if k["label"] == label)


def no_repeated_headings(answer):
    heads = re.findall(r"^\*\*[^*\n]{4,70}\*\*", answer, re.M)
    assert len(heads) == len(set(heads)), f"a section title appears twice: {heads}"


# 1 / 16 ---------------------------------------------------------------------------------------------- Overview
@pytest.mark.parametrize("question", ["Give me the complete dashboard summary.", "Sabhi dashboard pages ka summary batao.",
                                      "Show everything", "Overview"])
def test_overview_summary_lists_every_section(client, question):
    body = api(client, "/api/overview")
    r = chat(client, question)
    assert r["understood"] and r["intent"] == "summary" and r["page"] == "/"
    for sec in body["sections"].values():
        for k in sec.get("kpis") or []:
            assert k["label"] in r["answer"]
    assert "**Designers**" in r["answer"]
    if body.get("alerts"):
        assert "Needs attention" in r["answer"]
    no_repeated_headings(r["answer"])


def test_all_pages_summary_also_names_the_pages_not_on_the_overview(client):
    r = chat(client, "Sabhi dashboard pages ka summary batao.")
    for label in ("Clients Order Status", "Vendor Rate", "In/Out Sale", "Designer Order Target"):
        assert label in r["answer"]
    sale = kpi(api(client, "/api/in-out-sale"), "Sale pcs")
    assert f"{sale:,.0f} pcs" in r["answer"]


# 2 / 3 ----------------------------------------------------------------------------------------------- Fabricators
def scorecard(client):
    body = api(client, "/api/fabricator")
    t = body["tables"]["scorecard"]
    cols = [c["label"] for c in t["columns"]]
    return body, cols, [r for r in t["rows"] if not re.match(r"^(TOTAL|ALL OVER)", str(r[0]), re.I)]


def test_fabricators_page_summary_reads_the_fabricator_report_not_production(client):
    body, cols, rows = scorecard(client)
    r = chat(client, "Show the Fabricators page summary.")
    assert r["page"] == "/fabricators" and r["intent"] == "summary"
    assert f"{kpi(body, 'Remaining'):,.0f} pcs" in r["answer"] and f"{kpi(body, 'Fabric issued'):,.0f} mtr" in r["answer"]
    assert "Production page" in r["answer"]                       # the note that keeps the two measures apart
    assert len(re.findall(r"^\| ALL OVER", r["answer"], re.M)) == 0     # the sheet's own total line is not a fabricator
    no_repeated_headings(r["answer"])


def test_highest_remaining_fabricator_skips_the_sheet_total_row(client):
    body, cols, rows = scorecard(client)
    top = max(rows, key=lambda r: r[cols.index("Remaining (Pcs)")])
    r = chat(client, "Which fabricator has the highest remaining pcs?")
    assert r["page"] == "/fabricators" and f"**{top[0]}**" in r["answer"]
    assert "ALL OVER" not in r["answer"]
    assert f"{top[cols.index('Remaining (Pcs)')]:,.0f} pcs" in r["answer"]


def test_fabricator_stock_comparisons_use_the_fabricators_page(client):
    body, cols, rows = scorecard(client)
    a, b = rows[0], rows[1]
    r = chat(client, f"Compare {a[0].title()} and {b[0].title()} remaining pcs")
    assert r["page"] == "/fabricators"
    for x in (a, b):
        assert f"{x[cols.index('Remaining (Pcs)')]:,.0f}" in r["answer"]
    top = max(rows, key=lambda r: r[cols.index("Pcs Under Production")])
    r = chat(client, "Which fabricator has the highest pcs under production?")
    assert r["page"] == "/fabricators" and f"**{top[0]}**" in r["answer"]


# 4 / 5 / 6 / 7 --------------------------------------------------------------------------------------- Designers
def test_designers_page_summary_is_the_designers_api_not_in_out_sale_or_flo_future(client):
    body = api(client, "/api/designer")
    for q in ("Show the Designers page summary.", "Designers", "Show all designers summary"):
        r = chat(client, q)
        assert r["page"] == "/designers" and r["intent"] == "summary"
        assert f"{kpi(body, 'Total quantity'):,.0f} pcs" in r["answer"] and "Design Count" in r["answer"]
        assert "In/Out Sale" not in r["answer"] and "FLO Future" not in r["answer"]
        no_repeated_headings(r["answer"])


def repeat_rows(client):
    t = api(client, "/api/designer", order_type="REPEAT")["tables"]["designers"]
    cols = [c["label"] for c in t["columns"]]
    rows = [r for r in t["rows"] if r[0] != "TOTAL" and r[cols.index("Design Count")]]
    return sorted(rows, key=lambda r: (-r[cols.index("Design Count")], -r[cols.index("Total Volume (Pcs)")])), cols


def test_highest_repeat_orders_and_top_five(client):
    rows, cols = repeat_rows(client)
    for q in ("Who has the highest repeat orders?", "Show top 5 designers by repeat orders."):
        r = chat(client, q)
        assert r["page"] == "/designers" and f"**{rows[0][0]}**" in r["answer"]
        assert len(re.findall(r"^\d\. ", r["answer"], re.M)) == min(5, len(rows))


def test_compare_two_designers_uses_the_designers_page_only(client):
    names = [x[0] for x in api(client, "/api/designer")["tables"]["designers"]["rows"] if x[0] != "TOTAL"][:2]
    t = api(client, "/api/designer")["tables"]["designers"]
    cols = [c["label"] for c in t["columns"]]
    want = {x[0]: x[cols.index("Design Count")] for x in t["rows"]}
    r = chat(client, f"Compare {names[0].title()} and {names[1].title()}.")
    assert r["page"] == "/designers" and "In/Out Sale" not in r["answer"]
    assert all(f"{want[n]:,}" in r["answer"] for n in names)


def test_designer_monthly_performance_is_per_month_from_the_designers_api(client):
    names = [x[0] for x in api(client, "/api/designer")["tables"]["designers"]["rows"] if x[0] != "TOTAL"]
    name = names[0]
    months = api(client, "/api/designer")["options"]["month"]
    r = chat(client, f"Monthly performance of {name.title()}")
    assert r["page"] == "/designers" and "In/Out Sale" not in r["answer"]
    for m in months:
        t = api(client, "/api/designer", designer=name, month=m)["tables"]["designers"]
        cols = [c["label"] for c in t["columns"]]
        row = next((x for x in t["rows"] if x[0] == name), None)
        if row and row[cols.index("Design Count")]:
            assert f"| {m} | {row[cols.index('Design Count')]:,} |" in r["answer"]


# 8 / 9 --------------------------------------------------------------------------------------------------- Fabric PO
def test_fabric_po_pending_is_metres_and_pcs_is_explained(client):
    body = api(client, "/api/fabric-po")
    r = chat(client, "How much fabric is pending in Fabric PO?")
    assert r["page"] == "/fabric-po" and f"{kpi(body, 'Pending fabric'):,.0f} mtr" in r["answer"]
    r = chat(client, "How many pcs are pending in Fabric PO?")
    assert r["page"] == "/fabric-po" and "does not record **pending pcs**" in r["answer"] and "mtr" in r["answer"]
    assert f"{kpi(body, 'Total pcs'):,.0f} pcs" in r["answer"]            # the only pcs figure, named for what it is


# 10 ------------------------------------------------------------------------------------------ Expected deliveries
def test_expected_deliveries_in_a_month_use_delivery60(client):
    d = api(client, "/api/client").get("delivery60")
    if not d:
        pytest.skip("no delivery data")
    rows = [r for r in d["tables"]["months"]["rows"] if r[0] != "TOTAL"]
    m = rows[-1]
    r = chat(client, f"How many pcs are expected to be delivered in {m[0].split('-')[0]}?")
    assert r["page"] == "/clients" and f"{m[2]:,.0f}" in r["answer"] and m[0] in r["answer"]
    prod_over = kpi(api(client, "/api/production"), "Overdue pcs")
    assert f"{prod_over:,.0f}" not in r["answer"].split("What the pending figures mean")[0]
    r = chat(client, "Overdue deliveries kitne hain?")
    over = next(k["value"] for k in d["kpis"] if k["label"] == "Overdue")
    assert f"{over:,.0f} pcs" in r["answer"] and r["page"] == "/clients"
    r = chat(client, "Which client has the most overdue pcs in expected deliveries?")
    top = max([x for x in d["tables"]["clients"]["rows"] if x[0] != "TOTAL"], key=lambda x: x[3])
    assert top[0] in r["answer"]


# 11 / 13 ------------------------------------------------------------------------------------ Designer Order Target
def test_designer_target_questions_and_the_yearly_target(client):
    tr = api(client, "/api/target")["tracker"]
    tgt = next(k["value"] for k in tr["kpis"] if k["label"].startswith("Yearly target"))
    r = chat(client, "Show the yearly target.")
    assert r["page"] == "/target" and fmt.inr_short(tgt) in r["answer"]
    r = chat(client, "Which designer has the lowest target achievement?")
    assert r["page"] == "/target" and "no target per designer" in r["answer"]
    t = api(client, "/api/target")["filtered"]["tables"]["designers"]
    cols = [c["label"] for c in t["columns"]]
    low = min([x for x in t["rows"] if x[0] not in ("TOTAL", "(NOT ASSIGNED)")], key=lambda x: x[cols.index("New Revenue")])
    assert f"**{low[0]}**" in r["answer"]


# 12 ------------------------------------------------------------------------------------------------- Vendor Rate
def test_complete_vendor_rate_list_is_the_benchmark_table(client):
    body = api(client, "/api/vendor-rate")
    r = chat(client, "Show the complete Vendor Rate list.")
    assert r["page"] == "/vendor-rate"
    vendors = [x[0] for x in body["tables"]["benchmark"]["rows"] if x[0] != "TOTAL"]
    assert all(v in r["answer"] for v in vendors)
    no_repeated_headings(r["answer"])


# 14 / 15 ------------------------------------------------------------------------------------------------ In/Out Sale
def test_november_net_sale_and_in_house_vs_outsource_incoming(client):
    months = api(client, "/api/in-out-sale")["options"]["month"]
    m = months[-1]
    r = chat(client, f"Show {m.split('-')[0]} net sale.")
    assert r["page"] == "/in-out-sale" and fmt.inr_short(kpi(api(client, "/api/in-out-sale", month=m), "Net sale")) in r["answer"]
    totals = {}
    for typ in ("In-house", "Outsource"):
        t = api(client, "/api/in-out-sale", type=typ)["tables"]["fabricators"]
        cols = [c["label"] for c in t["columns"]]
        totals[typ] = sum(x[cols.index("Total")] for x in t["rows"] if x[0] != "TOTAL")
    r = chat(client, "Compare In-house and Outsource incoming pcs.")
    assert r["page"] == "/in-out-sale"
    assert f"{totals['In-house']:,.0f}" in r["answer"] and f"{totals['Outsource']:,.0f}" in r["answer"]


def test_in_out_sale_keeps_the_incoming_discrepancy_as_a_warning(client):
    body = api(client, "/api/in-out-sale")
    t = body["tables"]["fabricators"]
    cols = [c["label"] for c in t["columns"]]
    fab_total = sum(x[cols.index("Total")] for x in t["rows"] if x[0] != "TOTAL")
    month_total = kpi(body, "Incoming pcs")
    r = chat(client, "What is the total incoming pcs?")
    assert f"{month_total:,.0f} pcs" in r["answer"]
    if abs(month_total - fab_total) > 0.5:
        assert f"{fab_total:,.0f}" in r["answer"] and "apart in the sheet itself" in r["answer"]
    else:
        assert "apart in the sheet itself" not in r["answer"]


# duplicate output -------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("question", ["Show the Vendor Rate and Designer Order Target pages.", "Show vendor rate, designer order target",
                                      "Vendor rate list and designer order target summary"])
def test_a_multi_question_never_prints_a_section_title_twice(client, question):
    r = chat(client, question)
    assert r["intent"] == "multi"
    no_repeated_headings(r["answer"])
    assert not re.search(r"^\*\*\d\. [^*]+\*\*\n\*\*", r["answer"], re.M)        # "1. Show vendor rate" + the answer's own title


def test_each_answer_is_one_chat_message_not_two(client):
    first = chat(client, "Show the Designer Order Target page summary.")
    second = chat(client, "Show the Vendor Rate page summary.", first["conversation_id"])
    for r in (first, second):
        no_repeated_headings(r["answer"])
    stored = client.get(f"/api/chat/{second['conversation_id']}").json()["messages"]
    assert [m["role"] for m in stored] == ["user", "assistant", "user", "assistant"]


# Fabricators "Monthly incoming" (stock sheet) vs In/Out Sale "Incoming pcs" ------------------------------------------
def test_monthly_incoming_is_the_fabricators_page_and_incoming_pcs_is_in_out_sale(client):
    fab = api(client, "/api/fabricator")
    r = chat(client, "What is the monthly incoming of fabricators?")
    assert r["page"] == "/fabricators" and "Monthly Incoming (Pcs)" in r["answer"]
    t = fab["tables"]["scorecard"]
    cols = [c["label"] for c in t["columns"]]
    top = max([x for x in t["rows"] if not re.match(r"^(TOTAL|ALL OVER)", str(x[0]), re.I)],
              key=lambda x: x[cols.index("Monthly Incoming (Pcs)")])
    assert f"{top[cols.index('Monthly Incoming (Pcs)')]:,.0f} pcs" in r["answer"]
    assert f"{kpi(fab, 'Monthly incoming'):,.0f} pcs" in r["answer"]                 # the TOTAL row
    ios = api(client, "/api/in-out-sale")
    r2 = chat(client, "Show incoming pcs by fabricator")
    assert r2["page"] == "/in-out-sale" and f"{kpi(ios, 'Incoming pcs'):,.0f}" in r2["answer"] or "pcs" in r2["answer"]
    assert "Monthly incoming" in r2["answer"]                                           # the note that names the other figure
    one = chat(client, "Fabricator monthly incoming of " + top[0].title())
    assert one["page"] == "/fabricators" and f"{top[cols.index('Monthly Incoming (Pcs)')]:,.0f} pcs" in one["answer"]


# Page checks must be readable text (a real-data bug printed a pandas method instead of the item name) ----------------
def test_no_page_summary_contains_python_object_text(client):
    for q in ("Show the FLO Future page summary", "Show the Production page summary.", "Show the Samples page summary",
              "Show the Fabric PO page summary", "Show the Clients Order Status page summary",
              "Show the In/Out Sale page summary", "Show the Vendor Rate page summary.",
              "Show the Designer Order Target page summary."):
        r = chat(client, q)
        assert not re.search(r"<bound method|dtype:|object>|Name: \d+", r["answer"]), q
        assert len(r["answer"]) < 6000, q


def test_incoming_gap_between_month_table_and_fabricator_table_is_kept_as_a_warning():
    from app.assistant.extras import PageAnswers
    body = {"kpis": [{"label": "Incoming pcs", "value": 303407.0}],
            "checks": [{"kind": "warning", "text": "November-26: Incoming pieces is 8,985 in the month table but the "
                                                    "fabricator-wise table adds up to 9,131."}]}
    note = PageAnswers._incoming_gap(body, 303553.0)
    assert "303,407" in note and "303,553" in note and "146 pcs apart in the sheet itself" in note
    assert PageAnswers._incoming_gap(body, 303407.0) == ""            # nothing to warn about when the sheet agrees


def test_a_page_check_that_is_python_object_text_is_not_shown_to_the_user():
    """Whatever a page puts in its check notes, the chatbot never prints raw Python object text."""
    from app.assistant.extras import PageAnswers
    body = {"kpis": [{"label": "Target Qty (Promised)", "value": 310.0, "unit": "pcs", "format": "int"}],
            "tables": {}, "checks": [{"kind": "warning", "text": "Qty Promised is blank for 1 item(s): <bound method "
                                      "IndexOpsMixin.item of designer   Ayushi\nName: 26, dtype: object> (Ayushi)."},
                                     {"kind": "warning", "text": "A normal sheet note."}]}
    pa = PageAnswers(lambda page, f: body, {"flo-future": {}}, {"flo-future": "FLO Future"})
    text, _ = pa.page_summary("flo-future", [])
    assert "<bound method" not in text and "dtype" not in text
    assert "could not be shown as readable text" in text and "Note from the page: A normal sheet note." in text
