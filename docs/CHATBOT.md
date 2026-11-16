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
- Month by month: "revenue month wise". Comparisons: "compare Rekha vs Anamika revenue", "April vs May revenue".
- One PO: "status of FPO/2648", "po 2648".
- Counts and lists: "how many designers", "list vendors".
- The dashboard itself: "what does the Fabric PO page show", "where can I see delayed POs", "how do I download".
- Answer style: add "in one word" for just the number, or "in detail" for a breakdown.
- Follow-ups keep the subject: "total samples" → "and for May?".

## Files

| Part | Where |
|---|---|
| API route | `backend/app/main.py` → `POST /api/chat` |
| Engine (rules) | `backend/app/assistant/engine.py`, `text.py` (English / Hinglish words), `pages.py` (page and feature descriptions), `fmt.py` (number formats, same as the frontend) |
| Gemini helper | `backend/app/assistant/gemini.py` |
| Chat widget | `frontend/src/components/assistant/` (mounted once in `App.tsx`) |
| Tests | `backend/tests/test_assistant.py`, `frontend/src/components/assistant/Assistant.test.tsx` |

The API endpoints listed in `/api/openapi.json` are unchanged.
