# Notes for the AI assistant

The assistant is being built on its own branch. This page lists what the API already offers so it can answer from
the same numbers the dashboard shows.

- **`GET /api/context?month=...`** returns a compact snapshot of every dashboard: the "needs attention" alerts and the
  headline figures of each section, as label → (value, unit). It is small enough to put in a prompt.
- **Every dashboard endpoint is a ready-made tool.** `GET /api/production`, `/api/designer`, `/api/client`,
  `/api/samples`, `/api/fabricator`, `/api/fabric-po`, `/api/target` and `/api/overview` take the same filters as
  the page (repeat a parameter for several values: `?month=April-26&month=May-26`) and return KPIs, tables and chart
  series. The full list of parameters is in the OpenAPI document at `/api/openapi.json`.
- All endpoints are read-only and cached for a minute, so the assistant can call them freely.
- When sign-in is on, send `Authorization: Bearer <token>` (from `POST /api/auth/login`).

Answers should quote the same figures as the dashboard rather than computing their own from raw sheet data; the
calculations in `backend/app/dashboards/` are tested against the original app.
