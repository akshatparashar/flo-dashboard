# Checkpoint — where the project stands

_Last updated: 2026-11-26. Read this first when picking the work up._

> [!IMPORTANT]
> **Work on `more-sheets`, not `main`.** `main` (`977b158`) has none of the new tabs and must not be merged into,
> committed to or rebased without the owner's say-so.

## Branches

| Branch | What is on it (26 Nov) |
|---|---|
| `more-sheets` | The integration branch: **everything below**, including Stock Ageing and the 26 Nov chatbot fixes. |
| `feature/chatbot` | Chatbot work up to `a898a64` (merged into `more-sheets` on 26 Nov). Start from `more-sheets`: this branch lacks the later work. |
| `backup/more-sheets-2026-11-24` | `more-sheets` as it was before the first chatbot merge. |
| `main` | Untouched; what the 17 Nov deploy was made from. |

## New since 17 Nov

| Page / feature | Source | Notes |
|---|---|---|
| **FLO Future** `/flo-future` | `FLO_Future Nov 2026` (`1GFJRv_9…`) | Same rules as the old Streamlit tab (parity test). "Outsource Projects" is returned by the API and the chatbot but **not shown on the page** (left out when it was redrawn to the owner's screenshots). |
| **Vendor Rate** `/vendor-rate` | `FABRIC PO 11` (`1yIn6Gs5…`): `Rate_Data`, `NEW RATE SHEET` | Filters, fabric comparison chart, master price table (fabric × vendor), one vendor's rate table on selection, sheet checks. KPI tiles, benchmark and master rate sheet were removed on the owner's request. |
| **Clients Order Status** (was *Clients*) | Master sheet | Added: client pie, **FW ORDER'S** (`DASHBOARD` tab, April onwards), **expected deliveries by month** (pending `AU` by 60-day delivery date `AG`). |
| **Designer Order Target** | | Renamed from *Target & revenue*; URL `/target` unchanged. |
| **In/Out Sale** `/in-out-sale` | `IN/OUT/SALE 2026-27` (`1A6I90-k…`), tab `2026-27` | This year vs last year, animated running total, fabricator-wise incoming. "Share of incoming", "In-house and outsource" and "Promised against delivered" were removed from the page on request. |
| **Daily Delegation** `/daily-delegation` | `Sir_Daily_Delegation_Tracker` (`10bQHge7…`), **only** the `Daily Schedule` tab | Never falls back to another tab. "Today's pending work" in red lines with the responsible person. No deadline column, so "open for" counts from the task date. Contains personal tasks: keep the passcode on. |
| **Stock Ageing** `/stock-ageing` | **SQL snapshot**, not a sheet (see below) | FIFO ageing of finished-goods pcs, by age band and design-code series. |

### Stock Ageing: it is a snapshot, not live

- The API does **not** connect to SQL. It reads `stock_ageing.json` from the folder in `SQL_SNAPSHOT_DIR`.
  The file holds company figures: keep it **outside the repo** (on the owner's PC: `E:\flo\flo-sql-data`).
  Without it the page and the chatbot show made-up demo rows and say so (that includes any Vercel deploy).
- Current snapshot: as on **25 Nov 2026** closing. It does not update by itself.
- Rules: EasyTrade database `F2ETrade11`; PCS only (`sd_Mtrs = 0`); closing = yesterday; FIFO allocation of the
  closing balance to the newest inward lots across the year tables; value = inward rate before GST.
- File shape: `{as_on, source, control:{items, qty}, items:[{d, n, b, q1..q6, v1..v6, oi, li, wa}]}` (design code,
  description, balance, pcs and value per age band, oldest / last inward date, weighted age). `control.qty` is the
  ledger total; the page warns when the rows do not add up to it.
- **Open:** the SQL query that builds the file is not in the repo (it is in the owner's `stock-ageing-report`
  Claude skill). A refresh job or a real read-only SQL source is the next step.

### Not built: FIFO creditors ageing

Parked on the owner's instruction (26 Nov). The SQL database does not hold creditor bills (only vouchers pushed to
Tally since 1 Oct); the owner's FIFO register is built from **Tally Prime**'s pending bills.

## Status at a glance

| Part | State | Verified how (26 Nov, demo data unless said) |
|---|---|---|
| API (`backend/`) | Working | 409 pytest tests pass; every page endpoint answers 200 |
| Website (`frontend/`) | Working | Playwright 42 passed, 8 skipped by design (desktop + phone, includes the new tabs); 19 unit tests; typecheck and build clean |
| FLO Assistant | Answers for every new tab | Tested in English + Hinglish against copies of the real sheets and the stock snapshot |
| New sheets on the live Google API | **Not verified** | No Google key on the development PC; checked against downloaded copies of the sheets |
| Phone app (`mobile/`) | Renames only; **no screens for the new tabs** | Not tested since 17 Nov (dependencies not installed) |
| Live site (Vercel) | Deployed 17 Nov from `main` | Not redeployed as part of this work; not re-checked |

Chatbot fixes of 26 Nov: Stock Ageing questions; "December me kitne pcs aane wale hai" (answered 0 before); "which
month has the most deliveries" (answered by client before); listing outsource projects; "visits and meetings"
answered twice; a person's open tasks when none is marked *Pending*. Tests: `tests/test_assistant_stock_and_gaps.py`.

> [!IMPORTANT]
> **Why the dashboard can look "wrong":** without a Google key the API serves built-in **demo data** (the top bar
> shows a *Demo data* badge). Check `GET /api/health` → `"source": "google"` before comparing numbers with the sheets.

## Before putting this live

1. Share the **new sheets** with the service account as Viewer: FLO Future, FABRIC PO 11, IN/OUT/SALE 2026-27,
   Sir_Daily_Delegation_Tracker (FLO Future and FABRIC PO 11 were reported shared; the other two are unconfirmed).
2. Compare each new page with its sheet on `DATA_SOURCE=google`.
3. Decide how Stock Ageing gets its data on the server (see above).
4. Decide on Gemini phrasing: with a key set, answer text (now including task names and stock values) is sent to
   Google unless `ASSISTANT_GEMINI_PHRASING=off`.
5. Merge to `main` only when the owner says so.

## Part A — Deploy the dashboard on Vercel ✅ done 17 Nov

Kept for redeploys. Env vars were imported from a local, git-ignored `.env.vercel` (built from `backend/.env`).
**Still to do:** the Google key in use is the old shared one (`7b269e58…`) — make a new key, replace
`GOOGLE_SERVICE_ACCOUNT_JSON` in Vercel, redeploy, then delete the old key. A longer `DASHBOARD_PASSCODE` is advised.

**Who:** whoever owns the Vercel account. **Needs:** access to this GitHub repo, a Google service-account key with
Viewer access to every sheet in `backend/app/config.py` (nine files now), a team passcode. Full steps: README → [Deploy to Vercel](README.md#deploy-to-vercel).

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

Expect the first page after an idle period to take **~12–15 s** (every sheet is read on a cold start). After
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
  The demo-data test run is unaffected.
- **Sign-in is one shared passcode**, not personal logins. The 10-tries-a-minute lock is per server instance, so on
  Vercel keep the passcode long.
- **Chatbot** is rule based and does growth %, differences, sums, averages, shares and basic arithmetic on dashboard
  figures (`docs/CHATBOT.md`). `GEMINI_API_KEY` adds Gemini for understanding Hindi / Hinglish / Devanagari and small
  talk (labels only) and for rewriting answers fluently (**this step sends the answer's figures to Google**; turn it
  off with `ASSISTANT_GEMINI_PHRASING=off`). Ambiguous wording ("supplier") can pick fabricators instead of fabric vendors.
- `legacy/` (old Streamlit app) is kept only for the parity tests; remove once the old dashboard is retired.
- "How many outsource projects" says the list is on the FLO Future page; the page does not show that table.

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
cd backend  && python -m pytest                                 # 409 tests (demo data), ~5 min
cd frontend && npm run typecheck && npm test && npx playwright test
cd mobile   && npm run typecheck && npm run lint && npm test && npx expo-doctor
# after changing a calculation, also on the real sheets:
cd backend  && PARITY_SOURCE=google python -m pytest tests/test_parity.py
```

## Recent history

- **18–26 Nov:** the new tabs above, chatbot answers for them, merged on `more-sheets` (never `main`).
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
