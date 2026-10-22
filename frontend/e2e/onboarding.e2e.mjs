// Regression check: a fresh visitor who picks a non-English language on the landing page
// can enter through BOTH buttons and keeps that language after a reload.
// Needs a running app (default http://127.0.0.1:8000, override with FINZORIA_URL) and Playwright:
//   npm install --no-save playwright && npx playwright install chromium
// or set PLAYWRIGHT_MODULE to an existing Playwright install path.
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const BASE = (process.env.FINZORIA_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const CASES = [
  { locale: "bn", dir: "ltr" },
  { locale: "ar", dir: "rtl" },
];
const BUTTONS = [
  { index: 0, name: "Start planning", path: "/app/settings" },
  { index: 1, name: "Explore the demo", path: "/app/dashboard" },
];

const browser = await chromium.launch();
let failures = 0;
try {
  for (const { locale, dir } of CASES) {
    for (const button of BUTTONS) {
      const label = `${locale} + ${button.name}`;
      const context = await browser.newContext(); // fresh visitor: no cookie
      const page = await context.newPage();
      const apiErrors = [];
      page.on("response", (r) => {
        if (r.url().includes("/api/") && r.status() >= 400) apiErrors.push(`${r.request().method()} ${new URL(r.url()).pathname} ${r.status()}`);
      });
      try {
        await page.goto(BASE + "/");
        await page.locator(".landing-language select").selectOption(locale);
        await page.waitForFunction((l) => document.documentElement.lang === l, locale);
        // Button labels are localized, so select by position within the hero actions.
        await page.locator(".hero-actions button").nth(button.index).click();
        await page.waitForURL(`**${button.path}`, { timeout: 10000 });
        await page.waitForFunction((l) => document.documentElement.lang === l, locale, { timeout: 10000 });
        await page.reload();
        await page.locator("h1").waitFor();
        const after = await page.evaluate(() => ({ lang: document.documentElement.lang, dir: document.documentElement.dir }));
        const saved = await page.evaluate(async () => (await (await fetch("/api/preferences")).json()).language);
        const ok = after.lang === locale && after.dir === dir && saved === locale && apiErrors.length === 0;
        console.log(`${ok ? "PASS" : "FAIL"} ${label}: path=${new URL(page.url()).pathname} lang=${after.lang} dir=${after.dir} saved=${saved}${apiErrors.length ? " apiErrors=" + apiErrors.join(", ") : ""}`);
        if (!ok) failures += 1;
      } catch (err) {
        failures += 1;
        console.log(`FAIL ${label}: ${err.message.split("\n")[0]}${apiErrors.length ? " apiErrors=" + apiErrors.join(", ") : ""}`);
      } finally {
        await context.close();
      }
    }
  }
} finally {
  await browser.close();
}
console.log(failures === 0 ? "ONBOARDING REGRESSION: PASSED" : `ONBOARDING REGRESSION: FAILED (${failures})`);
process.exit(failures === 0 ? 0 : 1);
