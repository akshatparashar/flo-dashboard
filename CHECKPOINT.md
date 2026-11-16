# Checkpoint — where the project stands

_Last updated: 2026-11-17. Read this first when picking the work up again._

## Status at a glance

| Part | State | Verified how |
|---|---|---|
| **API** (`backend/`, FastAPI) | Working on the real Google Sheets | 128 pytest tests pass (incl. parity with the old Streamlit app) |
| **Website** (`frontend/`, React + Vite) | Working | 31 Playwright tests pass on real data; 19 unit tests; typecheck clean |
| **FLO Assistant** (chatbot, `POST /api/chat`) | Working in English + Hinglish | Tested on real data: figures, rankings, comparisons, month ranges, follow-ups, PO lookup |
| **Vercel config** (`vercel.json`) | Ready, **not deployed** | Full `vercel build` succeeded locally; `/api/*` → Python, rest → website |
| **Phone app** (`mobile/`, Expo SDK 58) | Working, **not yet tried on a real phone** | Driven end to end in a phone-size browser (light + dark); Android + iOS bundles compile; typecheck, lint, tests, expo-doctor clean |

Everything is committed and pushed to `origin/main` (github.com/akshatparashar/flo-dashboard).

## Next steps (in order)

1. **Deploy on Vercel** — import the repo, set env vars, deploy (README → *Deploy to Vercel*):
   `DATA_SOURCE=google`, `GOOGLE_SERVICE_ACCOUNT_JSON` (one line), `DASHBOARD_PASSCODE`, `TOKEN_SECRET`
   (optional `GEMINI_API_KEY`). Then check `https://<project>.vercel.app/api/status`.
2. **Try the phone app on a real phone** — `cd mobile && npm install && npx expo start`, scan with Expo Go.
3. **Build the app for the owner** — put the Vercel URL in `mobile/eas.json` (`EXPO_PUBLIC_API_URL`, both
   profiles), then `npx eas-cli@latest build --profile preview --platform android` → APK link.
4. **Sheet cleanup (team)** — Fabric PO sheet rows **SVV 12** and **RV 1316** have "DESIGNER NAME" / "CLIENT NAME"
   typed in as values. The dashboard treats them as blank; fix them at the source.

## Known gaps / ideas

- Phone app has no editor for the yearly target (uses the server default ₹50.2 Cr); the website has one.
- Phone app has no CSV export (the website does).
- First request after a cold start reads all five sheets (~12–15 s); later requests are cached for 60 s.
- Chatbot is rule based; `GEMINI_API_KEY` adds an optional fallback that only maps a question to dashboard
  labels (never sees figures).
- `legacy/` (old Streamlit app) is kept only for the parity tests; remove once the old dashboard is retired.

## How to run everything locally

```bash
# API on the real sheets (reads backend/.env)
cd backend && .venv/Scripts/python -m uvicorn app.main:app --port 8000
# Website
cd frontend && npx vite --port 5173                        # http://localhost:5173
# Phone app in the browser (needs CORS for 8081 on the API: CORS_ORIGINS=http://localhost:8081)
cd mobile && EXPO_PUBLIC_API_URL=http://localhost:8000 npx expo start --web --port 8081
```

Demo data instead of the sheets: start the API with `DATA_SOURCE=demo`.

## Checks before every push

```bash
cd backend  && .venv/Scripts/python -m pytest
cd frontend && npm run typecheck && npm test && npx playwright test
cd mobile   && npm run typecheck && npm run lint && npm test && npx expo-doctor
```

## Recent history (this round of work)

- Chatbot: fixed wrong answers found on real data — measure-vs-measure compare ("new vs repeat revenue"),
  "total orders", one month of a yearly figure ("this month target"), best/worst vendor by on-time rate with ties,
  "… of vendors" / "har designer ka …" lists, fabric questions → Fabric PO, table units, "client"/"vendor" never
  read as a name, "target kitna bacha hai" → remaining target.
- API: placeholder cells ("DESIGNER NAME") counted as blank; sign-in tokens never signed with a public default
  secret (derived from the service-account key when `TOKEN_SECRET` is unset).
- Vercel Services config + `.vercelignore` (no `.env`, keys, venvs, tests or legacy uploaded).
- New `mobile/` app; README and `docs/CHATBOT.md` updated; two e2e tests hardened for cold real-data loads.

## Where things live

| Need to change… | Look in |
|---|---|
| A calculation / KPI | `backend/app/dashboards/*.py` (parity tests will flag changes) |
| Chatbot understanding | `backend/app/assistant/engine.py`, `text.py` (words, Hinglish), `pages.py` |
| Sheet IDs / tabs | `backend/app/config.py` → `SHEET_REGISTRY` |
| Website page | `frontend/src/pages/` |
| Phone screen | `mobile/src/app/` (tabs in `(tabs)/`), shared UI in `mobile/src/components/` |
| Deploy config | `vercel.json`, `.vercelignore`, `backend/.python-version`, `mobile/eas.json` |
| Code map | `graphify-out/` (knowledge graph of the repo — see README → *Working on this project*) |
