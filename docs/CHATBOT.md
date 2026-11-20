# FLO Assistant

A chatbot on every page of the dashboard (the robot in the bottom-right corner). It answers questions about the
dashboard's numbers and pages, in English, Hinglish or Hindi, and quotes exactly the figures the pages show.

## How it answers

- **Read-only, dashboard data only.** `POST /api/chat` calls the same functions as the dashboard endpoints
  (`/api/production`, `/api/fabric-po`, `/api/target`, …). It never touches Google Sheets directly and never
  writes anything.
- **Rules first, no AI needed.** `backend/app/assistant/` learns its vocabulary from the dashboard itself: every KPI
  and table-column label, and every designer, client, vendor, fabricator, category, month and PO number in the
  filter lists. It pulls names, months and the answer style out of the question, then picks the best-matching
  figure (a KPI with filters applied, a table cell, a ranking, a month-by-month list or a comparison).
- **A calculation layer** (`calc.py` + `Assistant._calc*`). The words of a question are read for growth,
  difference, sum, average, share ("X as % of Y") and plain arithmetic; the figures themselves are still fetched
  from the dashboard, so the maths always starts from what the pages show. The only arithmetic code is a small
  safe evaluator (numbers and `+ - * / ^ ( )` only, no names or calls).
- **Optional Gemini (`GEMINI_API_KEY`).** A small model (`GEMINI_MODEL`, default `gemini-flash-lite-latest`) does
  three jobs. Without a key, or when a call fails or times out, the rules' own answer is used.
  1. **Understanding.** A question the rules cannot place, or where part of the question matched nothing in the
     rules' answer, is read by Gemini (English, Hinglish, Hindi in Devanagari, spelling mistakes). It receives the
     question and the dashboard's labels, **never any figures**, and returns which label / names / months /
     operation were meant; the rules then fetch the figures and do the maths. Gemini's reading replaces the rules'
     answer only if it explains at least as much of the question. Hindi (Devanagari) questions always go through it,
     because the rules read Roman letters only.
  2. **Small talk.** Greetings and off-topic questions get a short friendly reply (no figures).
  3. **Fluent answers.** The finished answer is rewritten in the language of the question (the language is
     detected by rules and passed in). **This is the one step that sends figures to Google** (the answer text, e.g.
     "Total revenue is ₹1.88 Cr in November-26"). Every number in the rewrite is checked against the original; if
     any figure differs, the plain answer is used instead. One-word answers are never rewritten. Switch this step
     off with `ASSISTANT_GEMINI_PHRASING=off`. Check Google's terms for the key you use: free-tier API content
     may be used to improve Google's products.

## What people can ask

- **Change between months:** "sales growth percentage this month vs last month", "pichle mahine aur is mahine ki
  sales me kitna fark hai", "is mahine sales kitne percent badhi", "October vs November pending pcs". Gives both the
  difference and the % change, and says when the current month is still running (so it is not a full-month
  comparison). Rates (approval %) show a change in points.
- **Sums, averages, shares, maths:** "Rekha aur Anamika ki revenue milake kitni hai", "average monthly revenue"
  (completed months, with the running month counted separately), "pending pcs ka percentage kitna hai total
  production me", "10% of total revenue", "total revenue divided by 12", "12*5", "(120+30)/5".
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

## Files

| Part | Where |
|---|---|
| API route | `backend/app/main.py` → `POST /api/chat` |
| Engine (rules) | `backend/app/assistant/engine.py`, `text.py` (English / Hinglish words), `pages.py` (page and feature descriptions), `fmt.py` (number formats, same as the frontend) |
| Calculations | `backend/app/assistant/calc.py` (reads the words, safe arithmetic); `engine.py` → `_calc_*` |
| Gemini helper | `backend/app/assistant/gemini.py` (understanding, small talk, fluent rewrite) |
| Chat widget | `frontend/src/components/assistant/` (mounted once in `App.tsx`) |
| Tests | `backend/tests/test_assistant.py`, `backend/tests/test_assistant_calc.py`, `frontend/src/components/assistant/Assistant.test.tsx` |

The API endpoints listed in `/api/openapi.json` are unchanged.
