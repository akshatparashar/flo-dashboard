"""Hard questions on Daily Delegation, Designers and Production, and greetings. Every expected figure is read from the
page's own endpoint in the same run (made-up demo rows)."""
from __future__ import annotations

import pytest

from app.assistant import fmt
from test_assistant_calc import client  # noqa: F401  (fixture)


def talk(client, *messages):
    conv = ctx = None
    out = []
    for m in messages:
        j = client.post("/api/chat", json={"message": m, "conversation_id": conv, "context": ctx}).json()
        conv = j["conversation_id"]
        ctx = j["context"] if j["understood"] else ctx
        out.append(j)
    return out


def ask(client, message):
    return talk(client, message)[-1]


def text(reply):
    return reply["answer"].replace("**", "")


def table(client, page, name, **params):
    t = client.get(f"/api/{page}", params=params).json()["tables"][name]
    return [c["label"] for c in t["columns"]], [r for r in t["rows"] if r[0] != "TOTAL"]


def persons(client):
    cols, rows = table(client, "daily-delegation", "persons")
    return {r[0]: dict(zip(cols, r)) for r in rows}


def tasks(client):
    cols, rows = table(client, "daily-delegation", "tasks")
    return [dict(zip(cols, r)) for r in rows]


def designers(client, **params):
    cols, rows = table(client, "designer", "designers", **params)
    return {r[0]: dict(zip(cols, r)) for r in rows}


# ------------------------------------------------------------------------------------------------ greetings
@pytest.mark.parametrize("message,start", [
    ("hi", "Hi!"), ("hello ji", "Namaste!"), ("good morning", "Good morning!"), ("good morning sir", "Good morning!"),
    ("good evening team", "Good evening!"), ("namaste", "Namaste!"), ("suprabhat", "Suprabhat!"),
    ("how are you", "I'm doing well"), ("kaise ho", "Main badhiya"), ("who are you", "I'm"), ("tum kaun ho", "Main"),
    ("bye", "Goodbye"), ("good night", "Goodbye"), ("great job", "Thank you"), ("bahut badhiya", "Shukriya"),
])
def test_greetings(client, message, start):
    a = ask(client, message)
    assert a["understood"] and a["intent"] in ("greet", "chat")
    assert text(a).startswith(start), a["answer"][:100]


def test_a_greeting_before_a_question_still_answers_it(client):
    a, plain = ask(client, "good morning, oldest open task"), ask(client, "oldest open task")
    assert text(a).startswith("Good morning!") and a["page"] == "/daily-delegation"
    assert plain["answer"] in a["answer"]


# ------------------------------------------------------------------------------------------------ Daily Delegation
def test_a_person_only_this_sheet_has(client):
    who = next(p for p in persons(client) if "Sir" in p or "Mam" in p)
    done = int(persons(client)[who]["Completed"])
    a = ask(client, f"{who.split()[0].lower()} ne kitne complete kiye")
    assert a["page"] == "/daily-delegation" and who in text(a), a["answer"][:200]
    assert (f"{done} task" in text(a)) if done else ("no Completed task" in text(a))


def test_who_completed_nothing_and_who_is_involved(client):
    everyone = persons(client)
    none = [n for n, r in everyone.items() if not r["Completed"]]
    a = text(ask(client, "kisne ek bhi task complete nahi kiya"))
    assert all(n in a for n in none) if none else "Everyone" in a
    involved = text(ask(client, "kitne log involved hai"))
    assert f"{len(everyone)} people" in involved and all(n in involved for n in everyone)


def test_one_task_by_words_of_its_title(client):
    task = max(tasks(client), key=lambda t: len(t["Task"]))
    words = [w for w in task["Task"].replace("–", " ").split() if len(w) > 3 and w.lower() not in ("from", "with", "that")][:3]
    a = ask(client, f"{' '.join(words)} ka status")
    assert a["page"] == "/daily-delegation" and task["Task"] in text(a), a["answer"][:250]
    assert task["Responsible"] in text(a) and task["Status"] in text(a)


def test_dates_yesterday_and_an_unknown_person(client):
    cols, rows = table(client, "daily-delegation", "dates")
    a = text(ask(client, "date wise tasks"))
    assert all(r[0] in a for r in rows)
    busiest = max(rows, key=lambda r: r[cols.index("Tasks")])
    assert busiest[0] in text(ask(client, "which day has most tasks"))
    assert "yesterday" in text(ask(client, "kal ke tasks")) or ask(client, "kal ke tasks")["page"] == "/daily-delegation"
    unknown = text(ask(client, "Rahul ke tasks"))
    assert "don't find Rahul" in unknown or "Rahul" in unknown


def test_today_heading_keeps_its_separators(client):
    assert "Delegation · everyone · " in text(ask(client, "today tasks"))


def test_delegation_follow_ups(client):
    everyone = persons(client)
    most = max(r["Tasks"] for r in everyone.values())
    leaders = [r for r in everyone.values() if r["Tasks"] == most]
    _, pending, rate = talk(client, "who has most tasks", "uske pending?", "uska completion rate")
    if len(leaders) == 1:
        assert leaders[0]["Person"] in text(pending), pending["answer"][:200]
        assert f"{leaders[0]['Done %']:.1f}%" in text(rate), rate["answer"][:200]
    else:                                                            # a tie: ask which one, don't pick silently
        assert "Which one" in text(pending) and all(r["Person"] in text(pending) for r in leaders)
    _, whose = talk(client, "open tasks", "kiske hain?")
    assert whose["page"] == "/daily-delegation" and "Person" in whose["answer"]


# ------------------------------------------------------------------------------------------------ Designers
def test_designer_categories(client):
    cols, rows = table(client, "designer", "categories")
    cat = cols[1]
    best = max((r for r in rows if not r[0].startswith("(")), key=lambda r: r[1] or 0)
    a = ask(client, f"which designer makes most {cat.lower()}")
    assert a["page"] == "/designers" and best[0] in text(a) and fmt.fmt_int(best[1]) in text(a), a["answer"][:200]
    first = rows[0]
    one = text(ask(client, f"{first[0].title()} ke {cat.lower()} kitne"))
    assert fmt.fmt_int(first[1] or 0) in one and cat in one


def test_designer_filters_average_profile_and_unknown(client):
    all_ = designers(client)
    real = {n: r for n, r in all_.items() if not n.startswith("(")}
    limit = sorted(r["Total Volume (Pcs)"] for r in real.values())[3]
    a = text(ask(client, f"designers with less than {int(limit)} pcs"))
    assert all(n in a for n, r in real.items() if r["Total Volume (Pcs)"] < limit)
    average = sum(r["Design Count"] for r in real.values()) / len(real)
    assert f"{average:,.1f} designs" in text(ask(client, "average order per designer"))
    name, row = next(iter(real.items()))
    profile = text(ask(client, f"{name.title()} ka pura data"))
    assert fmt.fmt_int(row["Total Volume (Pcs)"]) in profile and "Production:" in profile
    assert "don't find a designer called Priyanka" in text(ask(client, "Priyanka ke orders"))


def test_designer_follow_ups(client):
    names = [n for n in designers(client) if not n.startswith("(")]
    one, two = names[0], names[1]
    all_ = designers(client)
    _, new, repeat, other = talk(client, f"{one.title()} total quantity", "new?", "repeat?", f"aur {two.title()}?")
    assert fmt.fmt_int(all_[one]["New Orders (Pcs)"]) in text(new)
    assert fmt.fmt_int(all_[one]["Repeat Orders (Pcs)"]) in text(repeat)
    assert two in text(other) and fmt.fmt_int(all_[two]["Repeat Orders (Pcs)"]) in text(other)
    top = max((r for n, r in all_.items() if not n.startswith("(")), key=lambda r: r["Total Volume (Pcs)"])
    _, count = talk(client, "top designer", "uske design count?")
    assert f"{int(top['Design Count'])} designs" in text(count), count["answer"][:200]


# ------------------------------------------------------------------------------------------------ Production
def test_production_overdue_designs_share_and_months(client):
    body = client.get("/api/production").json()
    assert f"{body['summary']['overdue_designs']} designs are overdue" in text(ask(client, "overdue designs kitne"))
    assert f"{body['summary']['pending_pct']:.1f}%" in text(ask(client, "pending percentage"))
    cols, rows = table(client, "production", "monthly")
    months = ask(client, "month wise production")["answer"]
    assert all(r[0] in months for r in rows if r[cols.index("In Production")])


def test_production_status_and_fabricator_ranking(client):
    options = client.get("/api/production").json()["options"]
    a = ask(client, "status wise production")["answer"]
    assert all(s in a for s in options["status"])
    ranking = text(ask(client, "fabricator on time ranking"))
    assert all(f in ranking for f in options["fabricator"] if not f.startswith("("))
    assert ask(client, "late pcs")["page"] == "/production"


def test_category_breakdown_follow_up(client):
    cols, rows = table(client, "production", "categories")
    top = max(rows, key=lambda r: r[cols.index("Pending")])
    _, lead = talk(client, "category wise pending", "sabse zyada?")
    assert lead["page"] == "/production" and top[0] in text(lead), lead["answer"][:200]
