# Checkpoint — where the project stands

_Last updated: 2026-11-27 (phone app 2.0 with the new pages; assistant training from `more-sheets` merged). Read this first._

> [!IMPORTANT]
> **26 Nov: the owner moved everything to `main`** (the new tabs, the chatbot fixes and the FLO World UI). `main` is
> now the working branch and **every push to it redeploys the live site**. `more-sheets` got one more commit
> (`ce7404c`, Unsold Inventory Insights), merged into `main` the same evening. The **phone app (`mobile/`) was left as it is on
> purpose**: it will be rewritten later for the new version, and the new build handed to the owner then.

## Branches

| Branch | What is on it (26 Nov) |
|---|---|
| `more-sheets` | The new tabs, Stock Ageing, the 26 Nov chatbot fixes and Unsold Inventory Insights (`ce7404c`); all of it is on `main` too. |
| `feature/chatbot` | Chatbot work up to `a898a64` (merged into `more-sheets` on 26 Nov). Start from `more-sheets`: this branch lacks the later work. |
| `backup/more-sheets-2026-11-24` | `more-sheets` as it was before the first chatbot merge. |
| `main` | Everything: `more-sheets` plus the FLO World UI (pushed 26 Nov on the owner's instruction). Before that, `977b158` (the 17 Nov deploy). |

## New since 17 Nov

| Page / feature | Source | Notes |
|---|---|---|
| **FLO Future** `/flo-future` | `FLO_Future Nov 2026` (`1GFJRv_9…`) | Same rules as the old Streamlit tab (parity test). "Outsource Projects" is returned by the API and the chatbot but **not shown on the page** (left out when it was redrawn to the owner's screenshots). |
| **Vendor Rate** `/vendor-rate` | `FABRIC PO 11` (`1yIn6Gs5…`): `Rate_Data`, `NEW RATE SHEET` | Filters, fabric comparison chart, master price table (fabric × vendor), one vendor's rate table on selection, sheet checks. KPI tiles, benchmark and master rate sheet were removed on the owner's request. |
| **Clients Order Status** (was *Clients*) | Master sheet | Added: client pie, **FW ORDER'S** (`DASHBOARD` tab, April onwards), **expected deliveries by month** (pending `AU` by 60-day delivery date `AG`). |
| **Designer Order Target** | | Renamed from *Target & revenue*; URL `/target` unchanged. |
| **In/Out Sale** `/in-out-sale` | `IN/OUT/SALE 2026-27` (`1A6I90-k…`), tab `2026-27` | This year vs last year, animated running total, fabricator-wise incoming. "Share of incoming", "In-house and outsource" and "Promised against delivered" were removed from the page on request. |
| **Daily Delegation** `/daily-delegation` | `Sir_Daily_Delegation_Tracker` (`10bQHge7…`), **only** the `Daily Schedule` tab | Never falls back to another tab. "Today's pending work" in red lines with the responsible person. No deadline column, so "open for" counts from the task date. Contains personal tasks: keep the passcode on. |
| **Stock Ageing** `/stock-ageing` | **EasyTrade** (SQL Server), live through its MCP server, else a snapshot file (see below) | FIFO ageing of finished-goods pcs, by age band and design-code series, plus Unsold Inventory Insights. |

### Stock Ageing: live from EasyTrade (code ready, **not yet switched on**)

**To switch it on** (the owner has the address and token of EasyTrade's read-only MCP server):
1. `backend/.env` and Vercel → Settings → Environment Variables (Production + Preview):
   `EASYTRADE_MCP_URL=https://…ngrok-free.dev/ai/mcp` and `EASYTRADE_MCP_TOKEN=<token>`. The token is a secret:
   never in git, a chat or a screenshot.
2. Run one pull by hand and tie it to EasyTrade's as-on stock report:
   `cd backend; .venv\Scripts\python -m app.sources.easytrade --out C:\flo-sql-data`
   (prints designs, closing pcs, the ledger total and negative-stock items).
3. Redeploy on Vercel (env changes need a new deploy). The *Demo rows* warning goes and the source line reads
   "EasyTrade F2ETrade11 (live, via MCP)".

How it works (`backend/app/sources/easytrade.py`, tests in `tests/test_easytrade.py` against a fake MCP server):
- JSON-RPC over Streamable HTTP: initialize → `tools/call run_query` (SELECT only, 1,000 rows a page, 30 s).
- Yesterday's closing, pulled **about once a day**: 5–7 requests (connect, table list, ledger total, one query per
  1,000 designs), cached in memory and in `EASYTRADE_CACHE_DIR` (default the temp folder) for that date. The MCP
  server has a **monthly request limit**; on Vercel each new server instance may pull once more on a cold start.
- If EasyTrade cannot be reached (the PC behind the ngrok tunnel is off, a wrong token, the limit used up): the last
  good pull with a warning, then the `SQL_SNAPSHOT_DIR` file, then demo rows. After a failure it waits 10 minutes
  before asking again.
- The FIFO query is the one from the owner's `stock-ageing-report` skill, grouped by product + design.
- **Not verified on the real server yet:** this PC has no token, so the code was only run against a fake server.
  Check before relying on it: (a) the totals of the first pull match EasyTrade; (b) the sales fields. `ls`, `sa`
  and `s30`..`s365` are computed from `SL` vouchers (`s30` = pcs sold in the last 30 days, as-on day included) and
  `rop` from `OP` lots. **`rsr` / `radj` (sales return / adjustment lots) are not filled**: their EasyTrade voucher
  codes are not known here, so the "dated from returns / adjustments" note shows 0. Compare one pull with the 25 Nov
  snapshot (which has them) and adjust `fifo_sql` if any field differs.

Without the two variables nothing changes: the API reads `stock_ageing.json` from the folder in
`SQL_SNAPSHOT_DIR` (on the owner's PC: `E:\flo\flo-sql-data`, **outside the repo**), else shows made-up demo
rows and says so. The last snapshot file is as on **25 Nov 2026** closing.
- Rules: EasyTrade database `F2ETrade11`; PCS only (`sd_Mtrs = 0`); closing = yesterday; FIFO allocation of the
  closing balance to the newest inward lots across the year tables; value = inward rate before GST.
- File shape: `{as_on, source, control:{items, qty}, items:[{d, n, b, q1..q6, v1..v6, oi, li, wa}]}` (design code,
  description, balance, pcs and value per age band, oldest / last inward date, weighted age). `control.qty` is the
  ledger total; the page warns when the rows do not add up to it.
- The query that builds it is now in the repo (`easytrade.fifo_sql`), from the owner's `stock-ageing-report` skill.

**Unsold Inventory Insights** (section of the same page, `backend/app/dashboards/unsold.py`): two separate measures,
piece age (FIFO bands; "over 30 / 90 / 180 / 365 days" are nested) and no-sale days = as-on date minus the later of
the last sale and the arrival of the oldest piece still in stock. It needs the snapshot to carry `has_sales: true` and
per row `ls` (last `SL` sale date; absent = none since Apr 2023), `sa`, `s30`..`s365` (pcs sold), `fi` (first inward),
`rsr` / `radj` / `rop` (closing pcs whose lot is a sales return / stock count or journal entry / opening). Without them
only piece age is shown. On 26 Nov the 25 Nov snapshot was re-pulled with these fields: every earlier field was
identical, and the over-N and no-sale counts matched an independent SQL calculation.

### Not built: FIFO creditors ageing

Parked on the owner's instruction (26 Nov). The SQL database does not hold creditor bills (only vouchers pushed to
Tally since 1 Oct); the owner's FIFO register is built from **Tally Prime**'s pending bills.

## FLO Assistant: English and Hinglish (26 Nov late)

The owner wants **English and Hinglish only** (no Devanagari replies). The reply follows the question.
- With Gemini (the key is set on Vercel): Gemini rewrites the answer in Hinglish, every figure checked. Its prompt
  now asks for English or Hinglish only, office-WhatsApp style, never Devanagari.
- Without Gemini, or when it fails / times out / changes a figure: `backend/app/assistant/hinglish.py` rewrites the
  common answer shapes line by line ("Total POs **170 POs** hai (ab tak ke sabhi mahine)", "Sabse zyada Pending Pcs
  **MAHI EXPORTS** (fabricator) ke paas hai", growth / decline, top-N, month-wise, "X page par dikhega", stock lines,
  target achievement). Tables and long explanations stay in English. "namaste" / "shukriya" get Hinglish replies.
- A question in Devanagari is still read by Gemini (on Vercel) and answered in Hinglish; without Gemini it is asked
  to type in English or Hinglish.
- Hinglish detection words were widened (`_HINDI_WORDS` in `text.py`: kahan, purana, sasta, dikhega, dono, …).
- Checked on demo data with 40 English and Hinglish questions from the tests and docs: all understood; Hinglish
  replies keep the same figures as the English ones. Tests: `tests/test_assistant_hinglish.py` (33).
- To teach a new answer shape: add a pattern to `_LINES` in `hinglish.py` and a case to `CASES` in the test.

## FLO World UI (26 Nov evening, on `main`)

A brand front door in front of the dashboard. Files: `frontend/src/world/` (new), `frontend/public/brand/world/`
(22 label logos cut from `LOGOS/`), `frontend/public/brand/flo-letters-hi.png`; routes in `frontend/src/App.tsx`.

| Route | What it is |
|---|---|
| `/welcome` | Landing page. The preloader fades into it; a needle stitches a thread through the FLO letters (`NeedleFLO.tsx`, `STITCH` = 5.2 s), then live KPI cards, the design-to-delivery thread, the label marquee and a navy **footer** (page links, the house address, © FLO India). |
| `/world` | FLO World hub: the Dashboard card in the middle of a 7 x 4 grid, the 22 labels in the cells around it, each stitched to its neighbour nearer the core. Below 900 x 500 px it becomes a simple card grid. |
| `/world/:slug` | "Coming soon" room for a label. |
| `/` | Goes to `/welcome` once per browser session, then straight to the dashboard. `/?nointro` skips it (used by the e2e tests). |

Fixed on 26 Nov evening, after the owner's review:
- Needle and thread: about twice as slow (3.1 s to 6.2 s) and twice as thick, with a soft shadow; the headline comes in as the needle leaves the O.
- FLO World: the two overlapping ellipses of labels were replaced by the grid, so nothing overlaps and every gap is the same.
- New footer on the landing page.
- Preloader: lets go after **3.2 s at most** (was 9 s; it waited for every sheet). On the landing page the bracket
  **opens out to the edges of the screen** like a box (`exit="page"`), the same move that opens into the dashboard frame.
- Needle: hidden until it starts moving, sets off at once, and starts at the screen's left edge (the thread begins
  far off-screen, so the needle used to travel unseen for about 2.5 s). Stitch takes 5.2 s.
- "Enter the FLO world" dive into the O: zooms the letters' box as one GPU layer (`will-change` in `world.css`)
  instead of scaling the SVG, switches off the thread's shadow and glint first, and no longer re-renders the page on
  the click. It measured smooth (no frame over 30 ms) in the 2nd and 3rd test runs.
- **Overview → data-flow diagram:** the box was 232 px high for nine sheets, so the bottom wires ran off into empty space. Its height now follows the number of sheets (`frontend/src/components/DataFlow.tsx`).

Screenshots: `node e2e/world-shots.mjs <outdir>` with the dev server running. It takes these env vars: `BASE=http://localhost:5173`,
`CHANNEL=chrome` (when Playwright's own browser is not installed), `TOKEN=<token from POST /api/auth/login>` (when the
passcode is on) and `ONLY=1` (desktop light only).
Checked: typecheck clean, 19 unit tests pass, no console errors on any page (desktop light and dark, phone).
Playwright: 46 passed, 6 skipped by design (desktop + phone); production build clean.
`LOGOS/` (the source PDFs and a .rar, 107 MB) is git-ignored: the site only needs the PNGs in `public/brand/world/`.

## Status at a glance

| Part | State | Verified how (26 Nov, demo data unless said) |
|---|---|---|
| API (`backend/`) | Working | 409 pytest tests pass; every page endpoint answers 200 |
| Website (`frontend/`) | Working | Playwright 42 passed, 8 skipped by design (desktop + phone, includes the new tabs); 19 unit tests; typecheck and build clean |
| FLO Assistant | Answers for every new tab | Tested in English + Hinglish against copies of the real sheets and the stock snapshot |
| New sheets on the live Google API | **Not verified** | No Google key on the development PC; checked against downloaded copies of the sheets |
| Phone app (`mobile/`) | **2.0 (27 Nov):** screens for FLO Future, Vendor Rate, In/Out Sale, Daily Delegation, Stock Ageing (+ Unsold); FLO World (welcome with needle, hub, label rooms; `mobile/src/world/`); Clients and Overview additions; chat sends `conversation_id` | typecheck, lint, tests, expo-doctor pass; every screen rendered on demo data (web) without errors; APK built on EAS (preview profile) |
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
5. ✅ Merged to `main` on the owner's say-so (26 Nov).

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

## Chatbot follow-ups (27 Nov)

`backend/app/assistant/followups.py` rebuilds a short follow-up ("uska received?", "April me?", "kiske hain?") into a
full question from notes kept after each answer (topic, the name that came top, figure, months); `resolve` returns
None for anything else. The browser's context now wins over an older server memory (several server instances).
Tests: `backend/tests/test_assistant_followups.py`.

**Stock and Unsold Inventory** (`backend/app/assistant/stock.py`, tests `test_assistant_unsold.py`): no sale for N
days, never sold, longest unsold, oldest stock, by series, average age, count / journal and return pieces, one design
by its code, where the section is; their follow-ups travel in the context (`stock` intent).

**Other words and opposites** (`backend/app/assistant/synonyms.py`): inventory / maal / godown = stock, non-moving =
unsold, best selling = the opposite, supplier = vendor, passed / failed samples, unfinished / closed tasks, undelivered
= pending, and so on. Add a rule there (with its condition) when people use a new word.

**Daily Delegation, Designers, Production** (`focus.py`, tests `test_assistant_focus.py`) are the owner's most
important tabs: a task by words of its title, people only the delegation sheet has, who has completed nothing, tasks by
date, a designer's categories / profile / "under N pcs", overdue designs, production by status and month, fabricators
by on-time rate, and their follow-ups. **Greetings** are in `greetings.py`. Still ambiguous by design: "Deepika" is in
both Designers and Delegation, so say "task" for the delegation one.

**Not-a-figure questions** (`shortcuts.py`): urgent items (Overview alerts), where a page is, FLO World, team wise
status, a fabric's rate by name ("no fabric called X" instead of another rate). Tests: `test_assistant_synonyms.py`.
The other failures from the 27 Nov audit (oldest open task, Hinglish "sabse bada" / "sabse kharab", most overdue) are
fixed. Synonym coverage is a list, so a word not in it can still be missed.

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

- **27 Nov:** `more-sheets` (assistant follow-ups, synonyms, greetings, stock / unsold questions) fast-forwarded into
  `main`. Phone app 2.0: the five new pages under More (grouped), Clients (client share, expected deliveries, FW
  ORDER'S), FLO Future on Overview, chat memory via `conversation_id`, Expo SDK 58 patch updates.
- **26 Nov late:** merged `more-sheets` (Unsold Inventory Insights); chatbot replies in English or Hinglish
  without needing Gemini; Stock Ageing can read EasyTrade live through its MCP server (needs the two env vars).
- **26 Nov evening:** FLO World UI (landing, hub, coming-soon rooms), footer, data-flow height fix; see above.
- **18–26 Nov:** the new tabs above, chatbot answers for them, merged on `more-sheets`, then (26 Nov) on `main`.
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
| Hinglish replies | `backend/app/assistant/hinglish.py` (patterns), `text.py` (`_HINDI_WORDS`, `language_of`) |
| EasyTrade (Stock Ageing) | `backend/app/sources/easytrade.py` (MCP client, FIFO SQL, daily cache) |
| Landing / FLO World / label rooms | `frontend/src/world/` (labels list in `brands.ts`) |
| Phone screen | `mobile/src/app/` (tabs in `(tabs)/`), shared UI in `mobile/src/components/` |
| Deploy config | `vercel.json`, `.vercelignore`, `backend/.python-version`, `mobile/eas.json` |
| Code map | `graphify-out/` (knowledge graph of the repo — see README → *Working on this project*) |
