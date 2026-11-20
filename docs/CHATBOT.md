# FLO Assistant

A chatbot on every page of the dashboard (the robot in the bottom-right corner). It answers questions about the
dashboard's numbers and pages, in English or Hinglish, and quotes exactly the figures the pages show.

## How it answers

- **Read-only, dashboard data only.** `POST /api/chat` calls the same functions as the dashboard endpoints
  (`/api/production`, `/api/fabric-po`, `/api/target`, …). It never touches Google Sheets directly and never
  writes anything.
- **Rules first, no AI needed.** `backend/app/assistant/` learns its vocabulary from the dashboard itself: every KPI
  and table-column label, and every designer, client, vendor, fabricator, category, month and PO number in the
  filter lists. It pulls names, months and the answer style out of the question, then picks the best-matching
  figure (a KPI with filters applied, a table cell, a ranking, a month-by-month list or a comparison).
- **Optional Gemini fallback.** With `GEMINI_API_KEY` set, a question the rules cannot place is sent to a small
  Gemini model (`GEMINI_MODEL`, default `gemini-flash-lite-latest`) together with the list of labels. The model
  only returns which label / names / months were meant; the rules then fetch and phrase the answer. It never
  sees any figures. Without a key, or if the call fails, the assistant says it is not sure and suggests the
  closest labels.

## What people can ask

- A figure: "total PO count", "Rekha ka pending kitna hai", "fabric received in April", "this month revenue".
- Rankings: "top designer", "top 3 vendors by pending fabric", "sabse zyada pending kis fabricator ke paas hai".
- Month by month: "revenue month wise", "monthly target". Comparisons: "compare Rekha vs Anamika revenue",
  "April vs May revenue", and two measures side by side: "new vs repeat revenue", "pending vs received in April".
- Every row of a kind: "on-time rate of vendors", "har designer ka revenue", "category wise pending".
- Best / worst without a measure: "worst vendor", "best fabricator" rank by on-time rate (ties are all named).
- One month of a yearly figure: "this month target", "target for November".
- One PO: "status of FPO/2648", "po 2648".
- Counts and lists: "how many designers", "list vendors".
- The dashboard itself: "what does the Fabric PO page show", "where can I see delayed POs", "how do I download".
- Answer style: add "in one word" for just the number, or "in detail" for a breakdown.
- Follow-ups keep the subject: "total samples" → "and for May?".

### FLO Future (this month's promises)

The FLO Future page is one more page the assistant reads, so its figures work like any other: "kitne samples pending
hai flo future me", "Keerti ka completion rate", "Team A pending samples", "longest overdue", "how many visits and
meetings done", "which designer has most pending promises", "har team ka pending". A few things are specific to it:

- Words: *promise / promised / vaada / commitment*, *outsource*, *visits / meetings*, *not updated*, *due soon /
  this week / is hafte*. "Team A" / "Team B" / "Team C" work as names and as a ranking.
- FLO Future answers only when the question is about promises / FLO Future (or names a team): "Keerti pending" still
  means Production. Pending, overdue, due or promised **samples** go to FLO Future (the Samples page only has
  approval figures).
- "Which / kaun se / list" + overdue, due, not updated or pending names the **items** themselves, worst first, with
  designer, pcs and how late: "which samples are overdue", "kaun se items is hafte due hai",
  "Charu ke kaun se samples pending hai", "list overdue promises for Team B".
- Answers say which month's sheet they come from ("… (November 2026 promises)"), not "all months so far".

### Vendor Rate (fabric rates)

Price questions about fabric go to the Vendor Rate page and are answered from its rate list:

- **Cheapest / dearest** for a fabric: "crepe ka sabse sasta vendor kaun hai", "cheapest 44 inch muslin",
  "most expensive organza". 60" width unless the question says 44, 36 or per piece.
- **A vendor's rates**: "Varsha ki rate list", "BSK rates"; one vendor and one fabric: "RV ka crepe rate".
- **All rates for a fabric**: "russian silk rates", "chanderi kitne ka milta hai" (musline / lilen / russion and
  other spellings map to the same fabric category).
- Page figures work as usual: "lowest 60 inch rate", "lowest 44 inch rate", "pending rates".
- "Fabric pending", "approval rate" and "on time rate of vendors" still go to Fabric PO / Samples as before.

## Files

| Part | Where |
|---|---|
| API route | `backend/app/main.py` → `POST /api/chat` |
| Engine (rules) | `backend/app/assistant/engine.py`, `text.py` (English / Hinglish words), `pages.py` (page and feature descriptions), `fmt.py` (number formats, same as the frontend) |
| Gemini helper | `backend/app/assistant/gemini.py` |
| Chat widget | `frontend/src/components/assistant/` (mounted once in `App.tsx`) |
| Tests | `backend/tests/test_assistant.py`, `frontend/src/components/assistant/Assistant.test.tsx` |

The API endpoints listed in `/api/openapi.json` are unchanged.
