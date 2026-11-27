# FLO Operations — phone app

The FLO dashboard as a native Android / iPhone app (React Native, Expo SDK 58), **version 2.0**. It reads the same
read-only API as the web dashboard, so every number matches the web pages exactly, and it includes FLO Assistant.

The app opens like the website: the **opening** (the FLO bracket draws itself and opens out to the screen edges),
then the **landing** hero (a needle stitches a thread through the FLO letters), live figures, the thread from design
to delivery, the 22 labels and the house. **Enter the FLO world** opens the label hub; **Open dashboard** opens the
tabs below (Back returns to the landing).

| Tab / screen | What it shows |
|---|---|
| **Landing** (`/`) | The FLO front door: hero, live figures, a link to every page, the labels, footer |
| **FLO World** (`/world`) | The live Dashboard card and the 22 labels (burst-in, stitches, signal pings); each label opens a "coming soon" room |
| **Overview** (`/overview`) | What needs attention now: alerts, orders, fabric POs, stock, samples, FLO Future, designers |
| **Production** | Pending and overdue pcs by category, fabricator and month |
| **Fabric PO** | Overdue POs, delivery status, vendor scorecard, every PO |
| **Revenue** | The yearly new-order target, revenue by month, designer, item and client, repeat designs |
| **More** | FLO World, the landing screen, FLO Assistant; In/Out Sale, Stock Ageing (+ Unsold Inventory), Clients Order Status, FLO Future, Designers, Samples, Fabricators, Vendor Rate, Daily Delegation; sheet status, sign out |
| **Robot button** | FLO Assistant on every screen — English or Hinglish, same answers as the web chatbot |

Every screen: month chips, a **Filters** sheet (designer, vendor, client…), tables with a fixed first column that
scroll sideways and sort on tap, charts that show exact figures when you tap a month, pull down to read the sheets
again, light and dark mode following the phone, refresh every minute and whenever the app is reopened.

## Run it on your phone (development)

```bash
cd mobile
npm install
npx expo start          # scan the QR code with the Expo Go app (Android) or the Camera app (iPhone)
```

On the sign-in screen, enter the dashboard address and the team passcode (the same one as the web dashboard).

- Against the deployed site: the address is the Vercel URL, `flo-dashboardd.vercel.app`.
- Against a local API: start the backend with `uvicorn app.main:app --host 0.0.0.0 --port 8000` and use your PC's
  Wi-Fi address, e.g. `http://192.168.1.20:8000`.

## Build an installable app for the owner (EAS)

1. The dashboard is live at `https://flo-dashboardd.vercel.app`.
2. That URL is already in `eas.json` → `build.preview.env.EXPO_PUBLIC_API_URL` and `build.production.env.EXPO_PUBLIC_API_URL`
   (change it there if the site moves). The sign-in screen then only asks for the passcode. Left empty, it
   also asks for the address.
3. Build:

```bash
npx eas-cli@latest login
npx eas-cli@latest build --profile preview --platform android    # an .apk link you can send on WhatsApp
npx eas-cli@latest build --profile production --platform ios     # for TestFlight / the App Store (Apple account needed)
```

App ids: `com.floindia.operations` (Android and iOS). Change them in `app.json` before the first store upload if
FLO wants a different id.

## Checks

```bash
npm run typecheck      # TypeScript
npm run lint           # ESLint (expo lint)
npm test               # number formatting and API helpers (Node test runner)
npx expo-doctor        # Expo dependency and config check
```

To look at the screens without a phone: `EXPO_PUBLIC_API_URL=http://localhost:8000 npx expo start --web` (the
backend needs `CORS_ORIGINS` set to the web address). Animations are the same code on the phone, but check them on a
real phone before handing over a build.

## Builds handed over

| Version | Build | Date | What changed |
|---|---|---|---|
| 1.0.0 | 2 | 17 Nov 2026 | First app: eight dashboards, FLO Assistant |
| 2.0.0 | 5 | 27 Nov 2026 | FLO World (opening, landing, hub, label rooms, web animations); FLO Future, Vendor Rate, In/Out Sale, Daily Delegation, Stock Ageing; Clients and Overview additions; chat memory. Builds 3 and 4 were intermediate and replaced by 5. |

## How it is built

| Part | Where |
|---|---|
| Screens (Expo Router, file based) | `src/app/` — `index.tsx` the landing (home route), `world/` the hub and label rooms, `(tabs)/` the bottom tabs, `designers.tsx` … `stock-ageing.tsx` the pages under More, `assistant.tsx`, `sign-in.tsx` |
| FLO World pieces | `src/world/` — labels list and logos (`brands.ts`, artwork in `assets/world/`), `NeedleFLO.tsx` (needle and thread), `Preloader.tsx`, `motion.tsx` (scroll reveals, count-up, ping dot) |
| API client, sign-in, data refresh | `src/lib/api.ts`, `src/lib/auth.tsx` (token in the phone's secure storage), `src/lib/query.ts` |
| Number formats (same as the web) | `src/lib/format.ts` |
| Colours and fonts (FLO navy / blush, Bodoni Moda + Instrument Sans) | `src/lib/theme.ts` |
| Tables, charts, filters, KPI tiles | `src/components/` |
| API response types (copied from the web app) | `src/lib/types.ts` |

The app is read-only like the rest of the dashboard: it can never change a sheet.
