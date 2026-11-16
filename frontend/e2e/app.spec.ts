import { expect, test, type Page } from "@playwright/test";

const API = `http://127.0.0.1:${process.env.E2E_API_PORT ?? "8000"}`;
let token = "";
let authRequired = false;

// When the API asks for a passcode, sign in once and hand every page the token.
test.beforeAll(async ({ request }) => {
  authRequired = (await (await request.get(`${API}/api/health`)).json()).auth_required;
  if (!authRequired) return;
  const r = await request.post(`${API}/api/auth/login`, { data: { passcode: process.env.E2E_PASSCODE } });
  expect(r.ok(), "E2E_PASSCODE (or DASHBOARD_PASSCODE in backend/.env) must be the dashboard passcode").toBe(true);
  token = (await r.json()).token;
});

test.beforeEach(async ({ page }, info) => {
  if (token && !info.title.startsWith("sign-in")) await page.addInitScript((t) => localStorage.setItem("flo-token", t), token);
});

const PAGES = [
  { path: "/", h1: "Overview", api: "/api/overview" },
  { path: "/production", h1: "Production", api: "/api/production" },
  { path: "/designers", h1: "Designers", api: "/api/designer" },
  { path: "/clients", h1: "Clients", api: "/api/client" },
  { path: "/samples", h1: "Samples", api: "/api/samples" },
  { path: "/fabricators", h1: "Fabricators", api: "/api/fabricator" },
  { path: "/fabric-po", h1: "Fabric PO", api: "/api/fabric-po" },
  { path: "/target", h1: "Target & revenue", api: "/api/target" },
];

function watch(page: Page) {
  const problems: string[] = [];
  page.on("console", (m) => m.type() === "error" && problems.push(`console: ${m.text()}`));
  page.on("pageerror", (e) => problems.push(`page error: ${e.message}`));
  page.on("response", (r) => r.url().includes("/api/") && r.status() >= 400 && problems.push(`${r.status()} ${r.url()}`));
  return problems;
}

for (const p of PAGES) {
  test(`${p.h1} loads with data and no errors`, async ({ page }) => {
    const problems = watch(page);
    await page.goto(`${p.path}?nointro`);
    await expect(page.getByRole("heading", { level: 1, name: p.h1 })).toBeVisible();
    await expect(page.locator(".kpi-value").first()).not.toHaveText("");
    await expect(page.locator(".skel")).toHaveCount(0);
    await page.waitForLoadState("networkidle");
    expect(problems).toEqual([]);
  });
}

test("numbers on screen match the API exactly", async ({ page, request }) => {
  await page.goto("/production?nointro");
  const api = await (await request.get(`${API}/api/production`, { headers: token ? { Authorization: `Bearer ${token}` } : {} })).json();
  const want = api.kpis.find((k: { id: string }) => k.id === "production").value as number;
  const kpi = page.locator(".kpi").filter({ has: page.locator(".kpi-label", { hasText: /^In production$/ }) });
  await expect(kpi.locator(".kpi-value")).toContainText(Math.round(want).toLocaleString("en-US"));
  const total = page.locator("tr.total").first();
  await expect(total).toContainText(Math.round(want).toLocaleString("en-US"));
});

test("month filter updates the URL and the numbers, reset clears it", async ({ page, isMobile }) => {
  test.skip(isMobile, "popover flow is covered on desktop");
  await page.goto("/production?nointro");
  const value = page.locator(".kpi").filter({ has: page.locator(".kpi-label", { hasText: /^In production$/ }) }).locator(".kpi-value");
  await expect(value).not.toHaveText("0");
  const before = await value.textContent();
  await page.getByRole("toolbar", { name: "Filters" }).getByRole("button", { name: /^Month/ }).click();
  await page.getByRole("button", { name: "Pick months" }).click();
  await page.getByRole("option", { name: "Apr 26" }).click();
  await expect(page).toHaveURL(/month=April-26/);
  await expect(value).not.toHaveText(before ?? "");
  await page.keyboard.press("Escape");
  await page.getByRole("toolbar", { name: "Filters" }).getByRole("button", { name: "Reset" }).click();
  await expect(page).not.toHaveURL(/month=/);
  await expect(value).toHaveText(before ?? "");
});

test("multi-select filter narrows the designer table", async ({ page, isMobile }) => {
  test.skip(isMobile, "popover flow is covered on desktop");
  await page.goto("/designers?nointro");
  await page.getByRole("toolbar", { name: "Filters" }).getByRole("button", { name: /^Designer/ }).click();
  await page.getByPlaceholder("Search designer").fill("anam");
  await page.getByRole("option", { name: "Anamika" }).click();
  await expect(page).toHaveURL(/designer=ANAMIKA/);
  await page.keyboard.press("Escape");
  const rows = page.locator(".panel", { hasText: "Designer table" }).locator("tbody tr");
  await expect(rows).toHaveCount(2); // the designer + TOTAL
});

test("phone menu opens and navigates", async ({ page, isMobile }) => {
  test.skip(!isMobile, "phone only");
  await page.goto("/?nointro");
  await page.getByRole("button", { name: "Open menu" }).click();
  await page.getByRole("link", { name: "Samples" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Samples" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Open menu" })).toBeVisible();
});

test("theme toggle switches and persists", async ({ page }) => {
  await page.goto("/?nointro");
  await page.getByRole("button", { name: /Switch to (dark|light) mode/ }).click();
  const theme = await page.evaluate(() => document.documentElement.dataset.theme);
  expect(theme === "dark" || theme === "light").toBe(true);
  await page.reload();
  expect(await page.evaluate(() => document.documentElement.dataset.theme)).toBe(theme);
});

test("intro plays once per session and then gets out of the way", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator(".preloader")).toBeVisible();
  await expect(page.locator(".preloader")).toHaveCount(0, { timeout: 15_000 });
  await expect(page.getByRole("heading", { level: 1, name: "Overview" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("heading", { level: 1, name: "Overview" })).toBeVisible();
  await expect(page.locator(".preloader")).toHaveCount(0);
});

test("tables download as CSV", async ({ page, isMobile }) => {
  test.skip(isMobile, "desktop only");
  await page.goto("/production?nointro");
  const [dl] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: /Download production_categories/ }).click()]);
  expect(dl.suggestedFilename()).toBe("production_categories.csv");
});

test("live status shows a synced state", async ({ page }) => {
  await page.goto("/?nointro");
  await expect(page.locator(".live b")).toHaveText("Live");
});

test("sign-in rejects a wrong passcode and accepts the right one", async ({ page }) => {
  test.skip(!authRequired, "no passcode configured");
  await page.goto("/?nointro");
  await expect(page.getByRole("heading", { name: "Operations dashboard" })).toBeVisible();
  await page.getByLabel("Passcode").fill("wrong-code");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("alert")).toContainText("not right");
  await page.getByLabel("Passcode").fill(process.env.E2E_PASSCODE ?? "");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Overview" })).toBeVisible();
});

test("desktop sidebar folds into an icon rail and remembers it", async ({ page, isMobile }) => {
  test.skip(isMobile, "desktop only; phones use the drawer");
  await page.goto("/production?nointro");
  const sidebar = page.locator(".sidebar");
  await expect(page.getByRole("link", { name: "Fabric PO" })).toBeVisible();
  const wide = (await sidebar.boundingBox())!.width;
  await page.getByRole("button", { name: "Collapse sidebar" }).click();
  await expect.poll(async () => (await sidebar.boundingBox())!.width).toBeLessThan(80);
  expect(wide).toBeGreaterThan(200);
  // icons still navigate, and keep their accessible names
  await page.getByRole("link", { name: "Fabric PO" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Fabric PO" })).toBeVisible();
  await page.reload();
  await expect.poll(async () => (await sidebar.boundingBox())!.width).toBeLessThan(80);
  await page.keyboard.press("[");
  await expect.poll(async () => (await sidebar.boundingBox())!.width).toBeGreaterThan(200);
  await expect(page.getByRole("button", { name: "Collapse sidebar" })).toBeVisible();
});
