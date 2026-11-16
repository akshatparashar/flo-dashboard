# FLO Operations Dashboard

Live production, orders, samples, fabric and revenue for FLO, read straight from the five FLO Google Sheets and
refreshed every minute. Works on phones and PCs.

```
backend/    Python FastAPI API — reads the sheets (read-only), does every calculation, returns JSON
frontend/   React + TypeScript web app (Vite) — the dashboard
legacy/     The original Streamlit app, kept only so tests can prove the new numbers match it
assets/     Logo files
docs/       Notes for other developers (AI assistant integration)
```

## What it shows

Eight views, the same as the original dashboard: **Overview**, **Production**, **Fabricators**, **Fabric PO**,
**Designers**, **Clients**, **Samples** and **Target & revenue**. Every filter lives in the page address, so a
filtered view can be bookmarked or shared.

## How the data flows

1. The API reads the sheets through the Google Sheets API with the `spreadsheets.readonly` scope only. It can read
   the sheets it has been shared with and can never change them.
2. Each sheet is read at most once a minute, however many people have the dashboard open. If Google fails to answer,
   the last good copy is shown and the header turns from "Live" to "Delayed".
3. All calculations happen in the API (`backend/app/dashboards/`), ported line for line from the original app.
4. The web app asks the API again every minute; numbers that change animate to their new value and the data-flow
   view on the Overview sends a pulse along the wire of the sheet that changed.

## Run it locally (Windows, PowerShell)

Needs Python 3.11+ and Node 20+.

```powershell
# 1. API
cd backend
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
copy .env.example .env          # then edit .env (see below)
uvicorn app.main:app --reload --port 8000

# 2. Web app (second terminal)
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The API's own docs are at http://localhost:8000/api/docs.

Without a Google key the API uses built-in **demo data** laid out exactly like the real sheets, and the header says
"Demo data". Names and numbers in demo mode are invented.

## Connect the real Google Sheets

1. In Google Cloud Console, enable the **Google Sheets API** and create a **service account** with a JSON key.
2. Share each of the five sheets with the service account's `client_email` as **Viewer**.
3. Put the key in `backend/.env` (never commit it):
   - `GOOGLE_SERVICE_ACCOUNT_FILE=C:\keys\flo-sa.json` (a path outside the repo), or
   - `GOOGLE_SERVICE_ACCOUNT_JSON={...the whole JSON on one line...}`
4. Set `DATA_SOURCE=google` and restart the API.

The sheet IDs and tab names are in `backend/app/config.py` (`SHEET_REGISTRY`).

### Optional sign-in

Set `DASHBOARD_PASSCODE` and a long random `TOKEN_SECRET` in `.env`. The dashboard then asks for the passcode
before showing any data. Use this before putting the dashboard on a public address.

## Tests

```powershell
cd backend;  .venv\Scripts\python -m pytest        # 94 tests
cd frontend; npm test                              # unit tests
cd frontend; npm run typecheck; npm run build
cd frontend; npx playwright test                   # browser tests, desktop + phone, against the real API
```

- **Parity tests** (`backend/tests/test_parity.py`) run the original Streamlit dashboards headless on the same sheet
  grids as the new API and compare every table cell and every KPI, across many filter combinations.
- **Filter tests** (`backend/tests/test_api_filters.py`) check that every filter of every endpoint reaches its
  calculation over HTTP.
- **API tests** cover sign-in, the refresh limit, the one-read-per-minute cache, stale data when Google fails, and the
  parsing of messy cells (text dates, `24/04/2026+15/05/2026` part lots, `(50)`, `1,234`).
- **Browser tests** open every page in Chrome at desktop and phone size and fail on any console error or failed API
  call; they also check that on-screen numbers equal the API's, and exercise filters, the phone menu, the theme
  switch, the intro and CSV export.

## Not yet done

- Deployment to Vercel and a live domain.
- The React Native phone app (planned after the website is signed off; it will use the same API).
- The AI assistant (built separately; see `docs/CHATBOT.md`).
