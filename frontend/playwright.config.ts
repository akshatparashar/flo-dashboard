import { defineConfig, devices } from "@playwright/test";

import { readFileSync } from "node:fs";

/** Passcode for the sign-in step: E2E_PASSCODE, else the one in backend/.env (local runs only). */
function passcode(): string {
  if (process.env.E2E_PASSCODE) return process.env.E2E_PASSCODE;
  try {
    const env = readFileSync("../backend/.env", "utf8");
    return env.match(/^DASHBOARD_PASSCODE=(.*)$/m)?.[1]?.trim() ?? "";
  } catch {
    return "";
  }
}
process.env.E2E_PASSCODE = passcode();

const WEB = process.env.E2E_WEB_PORT ?? "5173";
const API = process.env.E2E_API_PORT ?? "8000";

// Runs against the real API (demo data unless backend/.env says otherwise). Starts both servers when needed.
export default defineConfig({
  testDir: "e2e",
  testMatch: "**/*.spec.ts",
  timeout: 45_000,
  retries: 0,
  workers: 2,
  reporter: [["list"]],
  use: { baseURL: `http://localhost:${WEB}`, channel: "chrome", trace: "retain-on-failure" },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], channel: "chrome", viewport: { width: 1440, height: 900 } } },
    { name: "phone", use: { ...devices["Pixel 7"], channel: "chrome" } },
  ],
  webServer: [
    {
      command: `${process.platform === "win32" ? ".venv\\Scripts\\python.exe" : ".venv/bin/python"} -m uvicorn app.main:app --port ${API}`,
      cwd: "../backend",
      url: `http://127.0.0.1:${API}/api/health`,
      reuseExistingServer: true,
      timeout: 60_000,
    },
    { command: `npx vite --port ${WEB} --strictPort`, url: `http://localhost:${WEB}`, reuseExistingServer: true, timeout: 60_000, env: { API_URL: `http://127.0.0.1:${API}` } },
  ],
});
