# Graph Report - flo-dashboard  (2026-11-17)

## Corpus Check
- 148 files · ~89,656 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 9 file(s) not represented in the graph (top: (none) 4, .css 2, .example 1)

## Summary
- 1489 nodes · 4519 edges · 72 communities (60 shown, 12 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 131 edges (avg confidence: 0.85)
- Token cost: 89,465 input · 0 output

## Community Hubs (Navigation)
- Chatbot Engine (rules)
- Web Pages and Charts
- Core Parsing Helpers
- Web Chart Components
- Web Data Hooks and Live Sync
- Mobile Detail Screens
- Test Fixtures and Parity Harness
- Legacy UI Cards
- Legacy Target and Sheets API
- Legacy Chart Helpers
- Legacy Streamlit App Shell
- Rupee and Month Formatting
- API Routes (main.py)
- Chatbot Tests
- Mobile Sign-in, Overview, More
- Settings and Tab Resolution
- Mobile App Shell and Auth
- Mobile Overview and Data Layer
- Parity Tests: Parsers
- Web API Types
- Legacy Fabric PO Builder
- Web API Client and Sign-in
- Demo Data Source
- Overview Dashboard (API)
- Mobile App Config (app.json)
- Mobile Revenue Screen
- Web Filters and Formatting
- Mobile Assistant Chat
- Config and Secrets Loading
- API Tests and Fake Sources
- Web Dependencies
- Master Sheet Dashboards
- Gemini Fallback
- Web Dev Dependencies
- Web TypeScript Config
- Legacy Client Dashboard
- Legacy Master Loader
- Web Chat Widget
- Mobile Expo Dependencies
- Number Parsing and Fabricator
- Web E2E Tests
- Google Sheets Source
- Mobile Lint Config
- Mobile Package Manifest
- Package Inits and Filter Tests
- Docs: Security and Phone App
- Mobile Charts
- Vercel Services Config
- Table Ordering and Totals
- Project Checkpoint
- Docs: FLO Assistant
- Docs: Expo Guidelines
- Docs: Business Rules and Design
- Mobile Scripts
- Master Sheet Parser
- Web Test Tooling
- Web Scripts
- Docs: Known Gaps and Caching
- Docs: Code Location Map
- Docs: Data Pipeline and Config
- Mobile TypeScript Config
- Expo Package
- Bodoni Moda Font
- Instrument Sans Font
- Expo Haptics
- Expo Linking
- Expo Secure Store
- Expo Splash Screen
- React (mobile)
- TanStack Query (mobile)
- Docs: Tech Stack

## God Nodes (most connected - your core abstractions)
1. `useTheme()` - 44 edges
2. `T()` - 37 edges
3. `Assistant` - 33 edges
4. `_overview_body()` - 31 edges
5. `Bars()` - 29 edges
6. `DemoSheetSource` - 27 edges
7. `DataStore` - 27 edges
8. `overview_dashboard()` - 26 edges
9. `ask()` - 26 edges
10. `fmtInt()` - 26 edges

## Surprising Connections (you probably didn't know these)
- `Optional Gemini fallback (label mapping only)` --semantically_similar_to--> `Read-only by design (spreadsheets.readonly scope)`  [INFERRED] [semantically similar]
  docs/CHATBOT.md → README.md
- `Rules-first engine (vocabulary learned from dashboard labels)` --shares_data_with--> `Response shape (meta, options, kpis, tables, charts)`  [INFERRED]
  docs/CHATBOT.md → README.md
- `Roadmap` --conceptually_related_to--> `EAS build for the owner (APK / TestFlight)`  [INFERRED]
  README.md → mobile/README.md
- `Robot button (FLO Assistant on every screen)` --semantically_similar_to--> `Chat widget (robot button)`  [INFERRED] [semantically similar]
  mobile/README.md → docs/CHATBOT.md
- `by_month()` --indirect_call--> `months()`  [INFERRED]
  legacy/streamlit_app.py → backend/app/assistant/fmt.py

## Import Cycles
- 2-file cycle: `backend/app/assistant/__init__.py -> backend/app/assistant/engine.py -> backend/app/assistant/__init__.py`

## Hyperedges (group relationships)
- **Sheets -> cached API -> web, assistant and phone app** — readme_five_google_sheets, readme_one_minute_cache, readme_data_pipeline, docs_chatbot_api_chat_endpoint, mobile_readme_flo_operations_phone_app [EXTRACTED 1.00]
- **FLO Assistant answer flow (rules first, Gemini label fallback, Hinglish vocabulary)** — docs_chatbot_api_chat_endpoint, docs_chatbot_rules_first_engine, docs_chatbot_gemini_fallback, docs_chatbot_hinglish_support [EXTRACTED 1.00]
- **Release path: Vercel deploy -> EXPO_PUBLIC_API_URL -> EAS build** — readme_vercel_services, mobile_readme_expo_public_api_url, mobile_readme_eas_build, checkpoint_next_steps [INFERRED 0.85]

## Communities (72 total, 12 thin omitted)

### Community 0 - "Chatbot Engine (rules)"
Cohesion: 0.06
Nodes (40): Assistant, Candidate, col_unit(), DataUnavailable, Entity, _hint(), kpi_list(), walk() (+32 more)

### Community 1 - "Web Pages and Charts"
Cohesion: 0.26
Nodes (43): useDashboard(), Slice, Bars(), colorFor(), Legend(), HBars(), BarList(), Heatmap() (+35 more)

### Community 2 - "Core Parsing Helpers"
Cohesion: 0.10
Nodes (28): clean_delay_days(), clean_text(), idx_to_col(), is_number_text(), month_label(), norm_key(), num(), parse_dates() (+20 more)

### Community 3 - "Web Chart Components"
Cohesion: 0.10
Nodes (38): Alert, Kpi, Notice, SeriesChart, Props, ChartFrame(), labelStep(), niceScale() (+30 more)

### Community 4 - "Web Data Hooks and Live Sync"
Cohesion: 0.09
Nodes (37): REFRESH_MS, useFetchingReporter(), useRefreshAll(), Health, Meta, StatusData, ART, BRACKET (+29 more)

### Community 5 - "Mobile Detail Screens"
Cohesion: 0.24
Nodes (38): Clients(), GROUPS, KEYS, Designers(), GROUPS, KEYS, Fabricators(), GROUPS (+30 more)

### Community 6 - "Test Fixtures and Parity Harness"
Cohesion: 0.06
Nodes (9): _Ctx, demo(), FakeSt, anything(), FakeState, legacy(), Recorder, Snapshot (+1 more)

### Community 7 - "Legacy UI Cards"
Cohesion: 0.08
Nodes (30): _card(), chart(), designer_kpis(), empty_card(), entity_chart(), _fab_body(), top_of(), _fabpo_body() (+22 more)

### Community 8 - "Legacy Target and Sheets API"
Cohesion: 0.09
Nodes (23): _a1_tab(), _api(), build_target_orders(), _cfg_of(), fetch_grid(), fetch_image_urls(), find_tab(), idx_to_col() (+15 more)

### Community 9 - "Legacy Chart Helpers"
Cohesion: 0.08
Nodes (25): donut(), _esc(), _hex_to_rgba(), inr(), inr_short(), _is_pinned(), metrics(), month_filter() (+17 more)

### Community 10 - "Legacy Streamlit App Shell"
Cohesion: 0.08
Nodes (18): apply_theme(), _book_cached(), build_fab_data(), _cell(), detect_fab_blocks(), get_client(), _hide_splash(), _keep_widget_state() (+10 more)

### Community 11 - "Rupee and Month Formatting"
Cohesion: 0.10
Nodes (18): inr(), inr_short(), month_sort_key(), safe_div_pct(), today_ist(), _filter(), image_map(), img_url() (+10 more)

### Community 12 - "API Routes (main.py)"
Cohesion: 0.16
Nodes (21): now_ist(), _clean(), client(), context(), designer(), _envelope(), fabric_po(), fabricator() (+13 more)

### Community 13 - "Chatbot Tests"
Cohesion: 0.13
Nodes (30): ask(), bold(), FakeInterpreter, kpi(), test_best_and_worst_vendor_rank_by_on_time_rate(), test_compare(), test_compare_two_measures(), test_counts_lists_pages_and_help() (+22 more)

### Community 14 - "Mobile Sign-in, Overview, More"
Cohesion: 0.14
Nodes (30): SignIn(), AlertCard(), Icon, More(), PAGES, Row(), st, RepeatRow() (+22 more)

### Community 15 - "Settings and Tab Resolution"
Cohesion: 0.10
Nodes (12): Settings, find_tab(), pick_default_tab(), DataStore, load(), Entry, _iso(), _now() (+4 more)

### Community 16 - "Mobile App Shell and Auth"
Cohesion: 0.13
Nodes (25): How it is built (code layout), Navigation(), RootLayout(), st, api(), ApiError, configureApi(), DEFAULT_SERVER (+17 more)

### Community 17 - "Mobile Overview and Data Layer"
Cohesion: 0.09
Nodes (29): AREA_LINK, AREA_NAME, KEYS, Open(), SEVERITY, st, Chip(), FilterGroup (+21 more)

### Community 18 - "Parity Tests: Parsers"
Cohesion: 0.17
Nodes (24): parse_fabric_po(), parse_samples(), set_widgets(), _alnum(), assert_kpis(), assert_table(), expected_text(), fab_cases() (+16 more)

### Community 19 - "Web API Types"
Cohesion: 0.11
Nodes (26): Cell, ClientData, Column, DesignerData, Envelope, FabricatorData, FabricPoData, NoticeKind (+18 more)

### Community 20 - "Legacy Fabric PO Builder"
Cohesion: 0.10
Nodes (22): build_fabric_po(), build_raw(), build_samples(), col(), canon_category(), canon_series(), classify_status(), clean_delay_days() (+14 more)

### Community 21 - "Web API Client and Sign-in"
Cohesion: 0.13
Nodes (21): api(), ApiError, getToken(), Params, setToken(), toQuery(), useHealth(), useStatus() (+13 more)

### Community 22 - "Demo Data Source"
Cohesion: 0.15
Nodes (11): col_to_idx(), col(), col(), DemoSheetSource, tab(), dmy(), _now_date(), serial() (+3 more)

### Community 23 - "Overview Dashboard (API)"
Cohesion: 0.13
Nodes (19): fmt(), empty_notice(), overview_dashboard(), ovw_group(), _pcs(), po_stats(), _top(), _entity_chart() (+11 more)

### Community 24 - "Mobile App Config (app.json)"
Cohesion: 0.07
Nodes (28): backgroundColor, backgroundImage, foregroundImage, monochromeImage, adaptiveIcon, package, predictiveBackGestureEnabled, usesNonExemptEncryption (+20 more)

### Community 25 - "Mobile Revenue Screen"
Cohesion: 0.15
Nodes (20): GROUPS, KEYS, st, st, width(), clockIST(), fixed(), fmtCell() (+12 more)

### Community 26 - "Web Filters and Formatting"
Cohesion: 0.13
Nodes (21): Fmt, Mode, MultiProps, Trigger(), usePopover(), describeMonths(), monthRange(), dec1 (+13 more)

### Community 27 - "Mobile Assistant Chat"
Cohesion: 0.13
Nodes (21): Assistant(), memory, Msg, nextId(), remember(), Reply, ROUTES, st (+13 more)

### Community 28 - "Config and Secrets Loading"
Cohesion: 0.16
Nodes (12): get_settings(), _load_dotenv(), _load_service_account(), _token_secret(), auth_status(), check_token(), login(), make_token() (+4 more)

### Community 29 - "API Tests and Fake Sources"
Cohesion: 0.14
Nodes (18): CountingSource, make_client(), test_auth_flow(), test_cache_reads_once_per_ttl(), test_column_title_typed_in_a_cell_is_blank(), test_error_without_cache_is_503(), test_health(), test_login_rate_limited() (+10 more)

### Community 30 - "Web Dependencies"
Cohesion: 0.11
Nodes (23): dependencies, d3-scale@^4.0.3, d3-shape@^3.2.1, @fontsource-variable/bodoni-moda@^5.3.0, @fontsource-variable/instrument-sans@^5.3.0, gsap@^3.15.1, @gsap/react@^2.1.2, lucide-react@^1.73.0 (+15 more)

### Community 31 - "Master Sheet Dashboards"
Cohesion: 0.19
Nodes (17): client_dashboard(), client_kpi_values(), designer_dashboard(), designer_kpi_values(), filter_data(), master_options(), month_list(), opt_list() (+9 more)

### Community 32 - "Gemini Fallback"
Cohesion: 0.11
Nodes (10): GeminiInterpreter, _assistant_fetch(), chat(), ChatIn, get_assistant(), Login, refresh(), test_gemini_client_request_and_failures() (+2 more)

### Community 33 - "Web Dev Dependencies"
Cohesion: 0.12
Nodes (17): devDependencies, jsdom@^29.1.1, @types/d3-scale@^4.0.9, @types/d3-shape@^3.2.0, @types/react@^19.3.0, @types/react-dom@^19.3.0, typescript@^7.0.2, vite@^8.3.8 (+9 more)

### Community 34 - "Web TypeScript Config"
Cohesion: 0.11
Nodes (17): compilerOptions, isolatedModules, jsx, lib, module, moduleResolution, noEmit, noFallthroughCasesInSwitch (+9 more)

### Community 35 - "Legacy Client Dashboard"
Cohesion: 0.24
Nodes (14): add_total(), badge(), client_dashboard(), client_kpis(), dash_title(), designer_dashboard(), filter_data(), filter_row() (+6 more)

### Community 36 - "Legacy Master Loader"
Cohesion: 0.18
Nodes (12): load_master(), _main_body(), notice(), render_fabric_po_dashboard(), render_fabricator_dashboard(), render_overview_dashboard(), render_sample_summary_dashboard(), render_target_dashboard() (+4 more)

### Community 37 - "Web Chat Widget"
Cohesion: 0.23
Nodes (10): Assistant(), ChatReply, dockedAway(), load(), Msg, save(), mount(), inline() (+2 more)

### Community 38 - "Mobile Expo Dependencies"
Cohesion: 0.13
Nodes (15): dependencies, expo-router@~58.0.31, expo-status-bar@~58.0.5, expo-system-ui@~58.0.7, @expo/vector-icons@^15.0.2, react-native@0.88.1, react-native-safe-area-context@~5.11.1, react-native-screens@~4.30.1 (+7 more)

### Community 39 - "Number Parsing and Fabricator"
Cohesion: 0.21
Nodes (8): to_num(), build_fab_data(), _cell(), detect_fab_blocks(), fabricator_dashboard(), parse_fabricator(), _rcvd_pct(), split_base()

### Community 40 - "Web E2E Tests"
Cohesion: 0.14
Nodes (7): PAGES, shots, errors, pages, widths, @playwright/test@^1.65.1, @playwright/test

### Community 42 - "Mobile Lint Config"
Cohesion: 0.18
Nodes (11): { defineConfig }, expoConfig, devDependencies, eslint@^9.0.0, eslint-config-expo@~58.0.4, @types/react@~19.3.0, typescript@~6.0.3, @types/react (+3 more)

### Community 43 - "Mobile Package Manifest"
Cohesion: 0.18
Nodes (10): expo-constants@~58.0.16, expo-font@~58.0.12, react-dom@19.3.0, react-dom, main, name, private, version (+2 more)

### Community 44 - "Package Inits and Filter Tests"
Cohesion: 0.22
Nodes (3): api_kpis(), test_each_filter_reaches_its_dashboard(), test_production_risk_filter()

### Community 45 - "Docs: Security and Phone App"
Cohesion: 0.22
Nodes (7): Run with Expo Go (development), FLO Operations phone app (Expo SDK 58), Tabs and screens (Overview, Production, Fabric PO, Revenue, More), Passcode sign-in with signed expiring tokens, Phone app section, Security (passcode, HMAC tokens, no-store, safe CSV), Connecting the real Google Sheets (service account)

### Community 46 - "Mobile Charts"
Cohesion: 0.22
Nodes (9): Legend(), niceMax(), SPLIT, st, Unit, axisLabel(), colorFor(), SeriesChart (+1 more)

### Community 47 - "Vercel Services Config"
Cohesion: 0.20
Nodes (10): entrypoint, root, buildCommand, framework, outputDirectory, rewrites, root, services (+2 more)

### Community 48 - "Table Ordering and Totals"
Cohesion: 0.31
Nodes (4): _cell(), is_pinned(), order_rows(), records()

### Community 49 - "Project Checkpoint"
Cohesion: 0.33
Nodes (8): Checks before every push, Next steps (deploy, real phone, EAS build, sheet cleanup), Project Checkpoint (status at a glance), Recent history (chatbot fixes, API, Vercel, mobile), EAS build for the owner (APK / TestFlight), EXPO_PUBLIC_API_URL (baked API address), Deploy to Vercel (one project, two services), .vercelignore (keeps .env, keys, venvs, tests, legacy out)

### Community 50 - "Docs: FLO Assistant"
Cohesion: 0.25
Nodes (9): Chat widget (robot button), FLO Assistant (chatbot), Follow-ups keep the subject, English and Hinglish questions, Question types (figure, ranking, month-wise, comparison, PO lookup, follow-ups), Robot button (FLO Assistant on every screen), GET /api/context (compact summary for AI assistant), API reference (GET per dashboard, filters as query params) (+1 more)

### Community 51 - "Docs: Expo Guidelines"
Cohesion: 0.22
Nodes (6): Development build needed for native modules beyond Expo Go, EAS build / submit / update, Expo/React Native agent guidelines, npx expo install for SDK-compatible packages, Expo Router (file-based routes in src/app/), App id com.floindia.operations

### Community 52 - "Docs: Business Rules and Design"
Cohesion: 0.25
Nodes (7): Business rules (FY, overdue, fabric PO delivery, revenue, target), Design system (navy/blush tokens from FLO logo), The eight dashboards, Fabric PO 15-day delivery rule (Delayed / Overdue), Five Google Sheets (Master, Sample summary, Fabricator report, Fabric PO, Designer target), FLO Operations Dashboard, Yearly new-order target (Rs 50.2 Cr, split across 12 months)

### Community 53 - "Mobile Scripts"
Cohesion: 0.25
Nodes (8): scripts, android, ios, lint, start, test, typecheck, web

### Community 54 - "Master Sheet Parser"
Cohesion: 0.29
Nodes (3): build_raw(), parse_master(), master_df()

### Community 55 - "Web Test Tooling"
Cohesion: 0.29
Nodes (6): @testing-library/jest-dom@^7.0.1, @testing-library/react@^16.3.3, vitest@^5.1.0, @testing-library/jest-dom, @testing-library/react, vitest

### Community 56 - "Web Scripts"
Cohesion: 0.29
Nodes (7): scripts, build, dev, e2e, preview, test, typecheck

### Community 57 - "Docs: Known Gaps and Caching"
Cohesion: 0.33
Nodes (5): Cold start reads all five sheets (~12-15 s), Known gaps / ideas, 1-minute cache with single-flight fetching, Roadmap, Testing suites (parity, filters, API, unit, Playwright)

### Community 58 - "Docs: Code Location Map"
Cohesion: 0.33
Nodes (5): Where things live (code location map), graphify-out code map (knowledge graph), Working on this project (workflow, adding a sheet), rewrites, $schema

### Community 59 - "Docs: Data Pipeline and Config"
Cohesion: 0.33
Nodes (6): POST /api/chat, Configuration (backend/.env variables), Data pipeline: Read, Cache, Parse, Calculate, Draw, Demo data mode (DATA_SOURCE=demo), Stale-if-error resilience (Live / Delayed light), Troubleshooting

### Community 60 - "Mobile TypeScript Config"
Cohesion: 0.33
Nodes (5): compilerOptions, strict, extends, include, expo/tsconfig.base

## Knowledge Gaps
- **10 isolated node(s):** `expo/tsconfig.base`, `Checks before every push`, `Fabric PO 15-day delivery rule (Delayed / Overdue)`, `Tech stack (FastAPI, pandas, React 19, TanStack Query, GSAP)`, `Configuration (backend/.env variables)` (+5 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 418 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **12 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `FLO Assistant (chatbot)` connect `Docs: FLO Assistant` to `Chatbot Engine (rules)`, `Docs: Security and Phone App`, `Chatbot Tests`, `Project Checkpoint`, `Docs: Business Rules and Design`, `Docs: Data Pipeline and Config`?**
  _High betweenness centrality (0.180) - this node is a cross-community bridge._
- **What connects `expo/tsconfig.base`, `Checks before every push`, `Fabric PO 15-day delivery rule (Delayed / Overdue)` to the rest of the system?**
  _10 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Chatbot Engine (rules)` be split into smaller, more focused modules?**
  _Cohesion score 0.05526512322628827 - nodes in this community are weakly interconnected._
- **Why does `Chat widget (robot button)` connect `Docs: FLO Assistant` to `Web Chat Widget`, `Web API Client and Sign-in`?**
  _High betweenness centrality (0.180) - this node is a cross-community bridge._
- **Should `Core Parsing Helpers` be split into smaller, more focused modules?**
  _Cohesion score 0.09574468085106383 - nodes in this community are weakly interconnected._
- **Why does `react-native` connect `Mobile Assistant Chat` to `Mobile Detail Screens`, `Mobile Expo Dependencies`, `Mobile Package Manifest`, `Mobile Sign-in, Overview, More`, `Mobile Charts`, `Mobile App Shell and Auth`, `Mobile Overview and Data Layer`, `Mobile Revenue Screen`?**
  _High betweenness centrality (0.044) - this node is a cross-community bridge._
- **Should `Web Chart Components` be split into smaller, more focused modules?**
  _Cohesion score 0.10195035460992907 - nodes in this community are weakly interconnected._