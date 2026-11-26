// Screenshots of the landing page, FLO World and a coming-soon room, light and dark, desktop and phone.
// Usage: node e2e/world-shots.mjs <outdir>   (dev server on :5173)
import { chromium } from "@playwright/test";

const out = process.argv[2] ?? "world-shots";
const base = process.env.BASE ?? "http://127.0.0.1:5173";
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

async function run(theme, w, h, tag) {
  const browser = await chromium.launch({ channel: process.env.CHANNEL || undefined });
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, colorScheme: theme });
  // the API may need the passcode: TOKEN=<token from /api/auth/login>
  if (process.env.TOKEN) await ctx.addInitScript((t) => localStorage.setItem("flo-token", t), process.env.TOKEN);
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  await page.goto(base + "/");
  await page.waitForSelector(".land.is-ready", { timeout: 25000 });
  await wait(1600);
  await page.screenshot({ path: `${out}/${tag}-1-stitching.png` });
  await wait(3600);
  await page.screenshot({ path: `${out}/${tag}-2-hero.png` });
  for (const id of ["system", "thread", "labels"]) {
    await page.evaluate((i) => document.getElementById(i)?.scrollIntoView(), id);
    await wait(1600);
    await page.screenshot({ path: `${out}/${tag}-3-${id}.png` });
  }
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  await wait(1500);
  await page.screenshot({ path: `${out}/${tag}-4-foot.png` });
  await page.evaluate(() => window.scrollTo(0, 0));
  await wait(800);
  await page.getByRole("button", { name: "Enter the FLO world" }).first().click();
  await wait(2500);
  await page.screenshot({ path: `${out}/${tag}-5-flying.png` });
  await wait(2600);
  await page.screenshot({ path: `${out}/${tag}-6-world.png` });
  await page.goto(base + "/world/vibe");
  await wait(2500);
  await page.screenshot({ path: `${out}/${tag}-7-soon.png` });
  await page.goto(base + "/?nointro");
  await wait(4000);
  await page.screenshot({ path: `${out}/${tag}-8-dashboard.png` });
  await page.evaluate(() => document.querySelector(".flow")?.scrollIntoView({ block: "center" }));
  await wait(1200);
  await page.screenshot({ path: `${out}/${tag}-9-flow.png` });
  console.log(tag, errors.length ? errors : "no errors");
  await browser.close();
}

await run("light", 1440, 900, "desk-light");
if (!process.env.ONLY) {
  await run("dark", 1440, 900, "desk-dark");
  await run("light", 390, 844, "phone-light");
}
