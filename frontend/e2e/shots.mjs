// Screenshots every page at 1440 and 390 in light (and optionally dark), and records console errors.
import { chromium } from "@playwright/test";
const base = process.env.BASE ?? "http://localhost:5173";
const out = process.env.OUT ?? "../.taste-skill/shots";
const pages = (process.env.PAGES ?? "/,/production,/designers,/clients,/samples,/fabricators,/fabric-po,/target").split(",");
const widths = (process.env.WIDTHS ?? "1440,390").split(",").map(Number);
const theme = process.env.THEME ?? "light";
const full = process.env.FULL === "1";
const browser = await chromium.launch({ channel: "chrome" });
// sign in when the API asks for a passcode
const api = process.env.API ?? "http://127.0.0.1:8000";
let token = "";
if ((await (await fetch(`${api}/api/health`)).json()).auth_required) {
  const r = await fetch(`${api}/api/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ passcode: process.env.PASSCODE }) });
  token = (await r.json()).token;
}
const errors = [];
for (const w of widths) {
  const ctx = await browser.newContext({ viewport: { width: w, height: w > 800 ? 900 : 844 }, deviceScaleFactor: 1, colorScheme: theme });
  if (token) await ctx.addInitScript((t) => localStorage.setItem("flo-token", t), token);
  const page = await ctx.newPage();
  page.on("console", (m) => m.type() === "error" && errors.push(`${w} ${page.url()} ${m.text()}`));
  page.on("pageerror", (e) => errors.push(`${w} ${page.url()} PAGEERROR ${e.message}`));
  for (const p of pages) {
    await page.goto(base + p + (p.includes("?") ? "&" : "?") + "nointro", { waitUntil: "networkidle" });
    await page.waitForSelector(".preloader", { state: "detached", timeout: 15000 });
    await page.waitForSelector(".page-head h1", { timeout: 15000 });
    await page.waitForTimeout(1600);
    const name = `${out}/${theme}-${w}${p === "/" ? "-overview" : p.replace(/\//g, "-")}.png`;
    // the app scrolls inside the sheet; for a full capture, grow the viewport to the sheet's content height
    if (full) {
      const h = await page.evaluate(() => document.querySelector(".sheet").scrollHeight + 60);
      await page.setViewportSize({ width: w, height: Math.min(h, 9000) });
      await page.waitForTimeout(500);
    }
    await page.screenshot({ path: name });
    if (full) await page.setViewportSize({ width: w, height: w > 800 ? 900 : 844 });
  }
  await ctx.close();
}
await browser.close();
console.log(errors.length ? errors.join("\n") : "no console errors");
