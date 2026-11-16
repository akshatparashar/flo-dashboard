// Screenshots for the README, taken on DEMO data only (never real business data).
import { chromium } from "@playwright/test";
const base = process.env.BASE ?? "http://localhost:5174";
const out = "../.taste-skill/readme";
const shots = [
  { name: "overview-light", path: "/", w: 1440, h: 1000, theme: "light" },
  { name: "overview-dark", path: "/", w: 1440, h: 1000, theme: "dark" },
  { name: "production", path: "/production", w: 1440, h: 1000, theme: "light" },
  { name: "target", path: "/target", w: 1440, h: 1000, theme: "light" },
  { name: "fabricators-dark", path: "/fabricators", w: 1440, h: 1000, theme: "dark", scroll: 1050 },
  { name: "mobile-overview", path: "/", w: 390, h: 844, theme: "light", scale: 2 },
  { name: "mobile-samples-dark", path: "/samples", w: 390, h: 844, theme: "dark", scale: 2 },
];
const browser = await chromium.launch({ channel: "chrome" });
for (const s of shots) {
  const ctx = await browser.newContext({ viewport: { width: s.w, height: s.h }, deviceScaleFactor: s.scale ?? 1, colorScheme: s.theme });
  const page = await ctx.newPage();
  await page.goto(`${base}${s.path}?nointro`, { waitUntil: "networkidle" });
  await page.waitForSelector(".page-head h1");
  if (s.scroll) await page.evaluate(() => { const h = [...document.querySelectorAll(".section-title h2")].find((e) => e.textContent === "Scorecard"); const sh = document.querySelector(".sheet"); sh.scrollTo(0, h.getBoundingClientRect().top + sh.scrollTop - 90); });
  await page.waitForTimeout(2200);
  await page.screenshot({ path: `${out}/${s.name}.png` });
  await ctx.close();
}
// the intro, caught mid-draw
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: "dark" });
const page = await ctx.newPage();
await page.goto(`${base}/`);
await page.waitForTimeout(1500);
await page.screenshot({ path: `${out}/intro.png` });
await browser.close();
console.log("done");
