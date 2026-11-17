# FLO Operations — phone app

The FLO dashboard as a native Android / iPhone app (React Native, Expo SDK 58). It reads the same read-only API as
the web dashboard, so every number matches the web pages exactly, and it includes FLO Assistant.

| Tab / screen | What it shows |
|---|---|
| **Overview** | What needs attention now: alerts, orders, fabric POs, stock, samples, designers |
| **Production** | Pending and overdue pcs by category, fabricator and month |
| **Fabric PO** | Overdue POs, delivery status, vendor scorecard, every PO |
| **Revenue** | The yearly new-order target, revenue by month, designer, item and client, repeat designs |
| **More** | Designers, Clients, Samples, Fabricators, FLO Assistant, sheet status, sign out |
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

## How it is built

| Part | Where |
|---|---|
| Screens (Expo Router, file based) | `src/app/` — `(tabs)/` for the bottom tabs, `designers.tsx` … for pages under More, `assistant.tsx`, `sign-in.tsx` |
| API client, sign-in, data refresh | `src/lib/api.ts`, `src/lib/auth.tsx` (token in the phone's secure storage), `src/lib/query.ts` |
| Number formats (same as the web) | `src/lib/format.ts` |
| Colours and fonts (FLO navy / blush, Bodoni Moda + Instrument Sans) | `src/lib/theme.ts` |
| Tables, charts, filters, KPI tiles | `src/components/` |
| API response types (copied from the web app) | `src/lib/types.ts` |

The app is read-only like the rest of the dashboard: it can never change a sheet.
