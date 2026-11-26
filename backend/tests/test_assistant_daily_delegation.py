"""Daily Delegation (the 12th page) through FLO Assistant. Every expected figure is read from /api/daily-delegation in the
same run (demo data when no Google sheet is configured); the page link is checked as well."""
from __future__ import annotations

import re

import pytest

from test_assistant_calc import client  # noqa: F401  (fixture)

PATH = "/daily-delegation"


def chat(client, message, conv=None):
    r = client.post("/api/chat", json={"message": message, "conversation_id": conv})
    assert r.status_code == 200, r.text
    return r.json()


def api(client, **params):
    return client.get("/api/daily-delegation", params=params).json()


def kpi(body, label):
    return next(k for k in body["kpis"] if k["label"] == label)


def persons(body):
    t = body["tables"]["persons"]
    cols = [c["label"] for c in t["columns"]]
    return cols, [r for r in t["rows"] if r[0] != "TOTAL"]


def short(name):                      # "Arihant Sir" -> a question that uses the first name only
    return name.split()[0]


def test_page_is_registered_with_its_route_and_aliases():
    from app.assistant.pages import NEW_PAGES, PAGES
    p = PAGES["daily-delegation"]
    assert p.path == PATH and p.label == "Daily Delegation" and "daily-delegation" in NEW_PAGES
    assert {"person", "status"} <= set(p.filters)


def test_api_is_wired_into_the_assistant():
    from app import main
    assert "daily-delegation" in main._ASSISTANT_PAGES
    out = main._assistant_fetch("daily-delegation", {"person": [], "status": ["Pending"], "q": ["x"]})
    assert "kpis" in out or out.get("no_match")


# ---- 1. page summary ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("question", ["Show the Daily Delegation page summary.", "Delegation", "Daily Delegation page"])
def test_page_summary_has_every_kpi_and_the_person_table(client, question):
    body = api(client)
    r = chat(client, question)
    assert r["page"] == PATH and r["understood"]
    for k in body["kpis"]:
        assert k["label"] in r["answer"]
    cols, rows = persons(body)
    assert all(row[0] in r["answer"] for row in rows)
    assert f"{kpi(body, 'Tasks')['value']:,.0f}" in r["answer"]
    assert "one row of the Daily Schedule tab" in r["answer"]                    # the unit is explained: tasks, not pcs
    heads = re.findall(r"^\*\*[^*\n]{4,70}\*\*", r["answer"], re.M)
    assert len(heads) == len(set(heads))


# ---- 2. counts by status, English and Hinglish -------------------------------------------------------------------------
@pytest.mark.parametrize("question,status", [("How many tasks are pending?", "Pending"),
                                             ("How many tasks are in progress?", "In Progress"),
                                             ("Kitne tasks awaiting approval hain?", "Awaiting Approval"),
                                             ("How many tasks are completed?", "Completed")])
def test_counts_by_status_match_the_status_filter(client, question, status):
    if status not in api(client)["options"]["status"]:
        pytest.skip(f"no {status} tasks in this data")
    want = api(client, status=status)["summary"]["tasks"]
    r = chat(client, question)
    assert r["page"] == PATH and f"**{want:,.0f} task" in r["answer"] and status in r["answer"]


# ---- 3. a person -------------------------------------------------------------------------------------------------------
def test_person_questions_use_the_person_filter(client):
    body = api(client)
    name = body["options"]["person"][0]
    want = api(client, person=name)["summary"]
    r = chat(client, f"{short(name)} ke tasks")
    assert r["page"] == PATH and name in r["answer"] and f"**{want['tasks']:,.0f} task" in r["answer"]
    assert f"{want['open']:,.0f} open" in r["answer"]
    r = chat(client, f"How many tasks are open for {name}?")
    assert f"**{want['open']:,.0f} task" in r["answer"]


def test_list_of_tasks_for_a_person_and_status(client):
    body = api(client)
    for name in body["options"]["person"]:
        for status in ("Pending", "In Progress"):
            rows = api(client, person=name, status=status)
            if rows.get("kpis"):
                r = chat(client, f"Which tasks are {status.lower()} for {name}?")
                first = rows["tables"]["tasks"]["rows"][0][2]                 # Task column
                assert first in r["answer"] and r["page"] == PATH
                return
    pytest.skip("no person with pending / in-progress tasks")


# ---- 4. rankings -------------------------------------------------------------------------------------------------------
def test_who_has_the_most_open_tasks_and_the_best_completion(client):
    cols, rows = persons(api(client))
    top = max(rows, key=lambda r: (r[cols.index("Open")], r[cols.index("Tasks")]))
    r = chat(client, "Who has the most open tasks?")
    assert r["page"] == PATH and f"**{top[0]}**" in r["answer"]
    assert f"{top[cols.index('Open')]:,.0f} tasks" in r["answer"]
    best = max(rows, key=lambda r: (r[cols.index("Done %")], r[cols.index("Tasks")]))
    r = chat(client, "Who has the highest completion percentage in delegation?")
    assert f"**{best[0]}**" in r["answer"] and f"{best[cols.index('Done %')]:.1f}%" in r["answer"]


# ---- 5. calculations ---------------------------------------------------------------------------------------------------
def test_completion_percentage_is_completed_over_tasks(client):
    s = api(client)["summary"]
    r = chat(client, "What is the task completion percentage?")
    assert f"{s['done_pct']:.1f}%" in r["answer"] and f"{s['completed']:,.0f} completed ÷ {s['tasks']:,.0f} tasks" in r["answer"]


def test_two_people_comparison_has_the_same_figures_as_the_person_table(client):
    cols, rows = persons(api(client))
    if len(rows) < 2:
        pytest.skip("need two people")
    a, b = rows[0], rows[1]
    r = chat(client, f"Compare {a[0]} and {b[0]} tasks")
    assert r["page"] == PATH and r["intent"] == "compare"
    for row in (a, b):
        assert row[0] in r["answer"]
        assert f"{row[cols.index('Tasks')]:,.0f}" in r["answer"]
    if a[cols.index("Done %")] != b[cols.index("Done %")]:
        diff = abs(a[cols.index("Done %")] - b[cols.index("Done %")])
        assert f"{diff:.1f} percentage points" in r["answer"]


# ---- 6. oldest / today / date / search ---------------------------------------------------------------------------------
def test_oldest_open_task(client):
    body = api(client)
    old = kpi(body, "Oldest open task")
    r = chat(client, "What is the oldest open task?")
    assert r["page"] == PATH and old["hint"][:30] in r["answer"] and f"{old['value']:.0f} days" in r["answer"]


def test_today_has_a_clear_answer_when_nothing_is_dated_today(client):
    body = api(client)
    r = chat(client, "What are today's pending tasks?")
    tp = body["today_pending"]
    assert r["page"] == PATH and f"**{tp['today_total']}**" in r["answer"]
    assert f"**{len(tp['carried'])}**" in r["answer"]


def test_a_date_and_a_search_word_filter_the_tasks(client):
    body = api(client)
    label = body["options"]["date"][0]                                          # "20 Nov 2026"
    day = int(label.split()[0])
    mon = label.split()[1]
    want = api(client, date=label)["summary"]["tasks"]
    r = chat(client, f"Show tasks dated {day} {mon}")
    assert f"**{want:,.0f} task" in r["answer"] and label in r["answer"]
    word = re.findall(r"[A-Za-z]{5,}", api(client)["tables"]["tasks"]["rows"][0][2])[0].lower()
    hits = client.get("/api/daily-delegation", params={"q": word}).json()
    r = chat(client, f"Tasks about {word}")
    assert f"**{hits['summary']['tasks']:,.0f} task" in r["answer"] if hits.get("summary") else "No task matches" in r["answer"]


# ---- 7. follow-ups and multi-question ------------------------------------------------------------------------------------
def test_follow_up_questions_keep_the_page_the_person_and_the_status(client):
    body = api(client)
    names = body["options"]["person"]
    first = chat(client, f"{short(names[0])} ke tasks")
    cid = first["conversation_id"]
    second = chat(client, f"What about {short(names[1])}?", cid)
    assert second["page"] == PATH and names[1] in second["answer"]
    status = next((s for s in ("Pending", "In Progress") if api(client, person=names[1], status=s).get("kpis")), None)
    if status:
        third = chat(client, f"Now show {status.lower()}", cid)
        assert names[1] in third["answer"] and status in third["answer"]
    fourth = chat(client, f"Compare with {short(names[0])}", cid)
    assert fourth["intent"] == "compare" and names[0] in fourth["answer"] and names[1] in fourth["answer"]


def test_multi_question_mixes_the_new_page_with_others_and_prints_each_title_once(client):
    r = chat(client, "Show the Daily Delegation page summary and the Vendor Rate page summary")
    assert r["intent"] == "multi"
    assert "Daily Delegation" in r["answer"] and "Vendor Rate" in r["answer"]
    heads = re.findall(r"^\*\*\d\. [^*\n]+\*\*", r["answer"], re.M)
    assert len(heads) == 2


# ---- 8. the new page in the all-pages summary, and no leakage into other answers ----------------------------------------
def test_all_pages_summary_names_daily_delegation_with_real_figures(client):
    r = chat(client, "Sabhi dashboard pages ka summary batao.")
    assert "Daily Delegation" in r["answer"]
    assert f"Tasks {kpi(api(client), 'Tasks')['value']:,.0f}" in r["answer"]


@pytest.mark.parametrize("question,page", [("How many pending pcs in production?", "/production"),
                                           ("Which designer has the highest repeat orders?", "/designers"),
                                           ("How much is Completed in FLO Future?", "/flo-future"),
                                           ("How many samples are approved?", "/samples")])
def test_other_pages_do_not_pick_up_the_tasks_cards(client, question, page):
    r = chat(client, question)
    assert r["page"] == page and "task" not in r["answer"].lower().split("daily delegation")[0]
