# Checkpoint — where the project stands

_Last updated: 2026-11-17. Read this first when picking the work up._

**Live at https://flo-dashboardd.vercel.app** (deployed 17 Nov on a personal Vercel account, not the floworker team).
**Phone app:** first Android build (preview APK, 17 Nov) — Expo project `flo-ais-team/flo`,
https://expo.dev/accounts/flo-ais-team/projects/flo/builds/cfb7cb1a-d9c8-475f-b385-097f39fdadc8 (signing key kept by EAS).
**Left:** check that APK on a real phone, then hand it to the owner ([Part B](#part-b--the-phone-app)).

## Status at a glance

| Part | State | Verified how |
|---|---|---|
| **API** (`backend/`, FastAPI) | Working on the real Google Sheets | 128 pytest tests pass on demo data |
| **Numbers vs the old Streamlit app** | Identical on the real sheets | Old app and new `/api` compared end to end on the live sheets (17 Nov): all 98 headline figures on all 8 pages match |
| **Website** (`frontend/`, React + Vite) | Working | 31 Playwright tests; 19 unit tests; typecheck and build clean |
| **FLO Assistant** (chatbot, `POST /api/chat`) | Working in English + Hinglish | Tested on real data; optional Gemini fallback tested with a real key |
| **Live site** (Vercel) | **Deployed** — https://flo-dashboardd.vercel.app | 17 Nov: passcode required, `source: google`, all 5 sheets `ok`, all 8 pages answer, chatbot "total PO count" = 514 = *Total POs* |
| **Phone app** (`mobile/`, Expo SDK 58) | Working, **not yet tried on a real phone** | Typecheck, tests and expo-doctor clean; Android + iOS bundles compile; builds point at the live site (`eas.json`) |

> [!IMPORTANT]
> **Why the new dashboard can look "wrong":** without a Google key the API serves built-in **demo data** (the top
> bar shows a *Demo data* badge, and e.g. Total POs reads 170 instead of the real figure). That is not a calculation
> bug. Check `GET /api/health` → `"source": "google"` before comparing numbers with the sheets.

## Part A — Deploy the dashboard on Vercel ✅ done 17 Nov

Kept for redeploys. Env vars were imported from a local, git-ignored `.env.vercel` (built from `backend/.env`).
**Still to do:** the Google key in use is the old shared one (`7b269e58…`) — make a new key, replace
`GOOGLE_SERVICE_ACCOUNT_JSON` in Vercel, redeploy, then delete the old key. A longer `DASHBOARD_PASSCODE` is advised.

**Who:** whoever owns the Vercel account. **Needs:** access to this GitHub repo, a Google service-account key with
Viewer access to the five sheets, a team passcode. Full steps: README → [Deploy to Vercel](README.md#deploy-to-vercel).

1. **Make fresh keys first.** The current Google service-account key and Gemini key have been shared in chats.
   - Google Cloud Console → *IAM → Service accounts* → `streamlit-dashboard-master@…` → *Keys* → **Add key (JSON)**,
     then **delete the old key** (`7b269e58…`).
   - Gemini (optional): Google AI Studio → *API keys* → create a new key, delete the old one.
2. **Vercel → Add New → Project →** import `akshatparashar/flo-dashboard`, root = repo root (Vercel reads `vercel.json`).
3. **Settings → Environment Variables** (Production and Preview):

   | Variable | Value | Required? |
   |---|---|---|
   | `DATA_SOURCE` | `google` | yes |
   | `GOOGLE_SERVICE_ACCOUNT_JSON` | the new key file as **one line** of JSON | yes |
   | `DASHBOARD_PASSCODE` | a long team passcode | **yes** — without it the site is public: orders, clients and revenue |
   | `TOKEN_SECRET` | a long random string (e.g. `openssl rand -hex 32`) | recommended |
   | `GEMINI_API_KEY` | the new Gemini key | optional (chatbot fallback) |

4. **Deploy**, then check:
   - [ ] The site asks for the passcode.
   - [ ] No *Demo data* badge in the top bar.
   - [ ] `https://<project>.vercel.app/api/status` (after signing in) shows `"ok": true` for all five sheets.
   - [ ] Overview → Fabric PO → *Total POs* equals the number of POs in the Fabric PO sheet's INDEX tab.
   - [ ] Robot button → "total PO count" answers with the same number.
5. **Send the phone developer** the Vercel address and the passcode (not the Google key — the app never needs it).

Expect the first page after an idle period to take **~12–15 s** (all five sheets are read on a cold start). After
that, data is cached for 60 s.

## Part B — The phone app

**Who:** the mobile developer. **Needs:** the Vercel address and passcode from Part A, Node.js 22+, Expo Go on a
phone, an Expo account (for builds), an Apple developer account (only for iPhone store builds).
Full guide: [`mobile/README.md`](mobile/README.md) and [`mobile/AGENTS.md`](mobile/AGENTS.md).

1. **Run it on a real phone** (not done yet):
   ```bash
   cd mobile && npm install && npx expo start      # scan the QR code with Expo Go
   ```
   On the sign-in screen enter `flo-dashboardd.vercel.app` and the passcode. Check every tab in light and dark mode.
2. ✅ **Builds point at the live API:** `mobile/eas.json` has `EXPO_PUBLIC_API_URL=https://flo-dashboardd.vercel.app`
   in both profiles, so the built app only asks for the passcode.
3. **Build:**
   ```bash
   npx eas-cli@latest login
   npx eas-cli@latest build --profile preview --platform android    # .apk link for the owner
   npx eas-cli@latest build --profile production --platform ios     # TestFlight / App Store
   ```
4. App id is `com.floindia.operations` (`mobile/app.json`); change it before the first store upload if needed.

**Rules for the phone app**
- It reads the **same API** as the website; never calculate figures on the phone. The API is documented at
  `/api/docs` on the deployed site and in README → [API reference](README.md#api-reference).
- Response types are copied by hand in `mobile/src/lib/types.ts` (from `frontend/src/api/types.ts`). If an API
  response changes, update both.
- It is read-only: it can never change a sheet. The sign-in token lives in the phone's secure storage.

**Done 17 Nov:** yearly-target editor on the Target tab (kept on the phone) and a *CSV* link under every table (opens
the share sheet with a `.csv` file; same file as the website). **Still open:** not yet tested on a real Android or
iPhone.

## Known issues

- **6 real-sheet parity tests fail on purpose** — `PARITY_SOURCE=google pytest tests/test_parity.py` →
  `test_fabric_po_dashboard[0–5]`. The new API shows the placeholder text "CLIENT NAME" (PO **RV 1316**) and
  "DESIGNER NAME" (PO **SVV 12**) as *(BLANK)*; the old app showed them as names. No totals change. Fix: type the
  real client / designer into those two rows of the Fabric PO sheet (or teach the parity test the new rule).
  The demo-data test run (128 tests) is unaffected.
- **Sign-in is one shared passcode**, not personal logins. The 10-tries-a-minute lock is per server instance, so on
  Vercel keep the passcode long.
- **Chatbot** is rule based; `GEMINI_API_KEY` adds a fallback that only maps a question to dashboard labels (it
  never sees figures). Ambiguous wording ("supplier") can pick fabricators instead of fabric vendors.
- `legacy/` (old Streamlit app) is kept only for the parity tests; remove once the old dashboard is retired.

## How to run everything locally

```bash
# API on the real sheets (reads backend/.env — see README → Configuration)
cd backend
.venv/Scripts/python -m uvicorn app.main:app --port 8000      # Windows
.venv/bin/python -m uvicorn app.main:app --port 8000          # macOS / Linux
# Website
cd frontend && npx vite --port 5173                           # http://localhost:5173
# Phone app in the browser (needs CORS for 8081 on the API: CORS_ORIGINS=http://localhost:8081)
cd mobile && EXPO_PUBLIC_API_URL=http://localhost:8000 npx expo start --web --port 8081
```

Demo data instead of the sheets: start the API with `DATA_SOURCE=demo`. Keep key files **outside** the repo and
point `GOOGLE_SERVICE_ACCOUNT_FILE` at them.

## Checks before every push

```bash
cd backend  && python -m pytest                                 # 128 tests (demo data)
cd frontend && npm run typecheck && npm test && npx playwright test
cd mobile   && npm run typecheck && npm run lint && npm test && npx expo-doctor
# after changing a calculation, also on the real sheets:
cd backend  && PARITY_SOURCE=google python -m pytest tests/test_parity.py
```

## Recent history

- **17 Nov — real-sheet check:** the old Streamlit app (`legacy/streamlit_app.py`, identical to the
  `design355/sample-production-dashboard` app) and the new API were run on the same live sheets: all headline
  figures match. Reports of "wrong numbers" were the demo-data mode. This file and the README were updated as a
  hand-over for deployment and the phone app.
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
