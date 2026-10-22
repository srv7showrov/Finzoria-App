// Lightweight accessibility check (not a full WCAG audit): on every section, visible form
// controls have an accessible name, buttons and links have text, the first Tab reaches the
// skip link, and keyboard focus is visibly outlined. Needs the app running and Playwright.
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const BASE = (process.env.FINZORIA_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const SECTIONS = ["dashboard", "workspace", "payments", "currency", "budget", "funding", "trust", "reports", "learn"];

let failures = 0;
function check(name, ok, detail = "") {
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail ? ": " + detail : ""}`);
  if (!ok) failures += 1;
}

const audit = () => {
  const visible = (el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
  const name = (el) =>
    (el.getAttribute("aria-label") || "").trim() ||
    (el.getAttribute("aria-labelledby") || "").split(" ").map((id) => document.getElementById(id)?.textContent || "").join("").trim() ||
    Array.from(el.labels || []).map((l) => l.textContent).join("").trim() ||
    (el.getAttribute("title") || "").trim();
  const unnamedControls = Array.from(document.querySelectorAll("input:not([type=hidden]), select, textarea"))
    .filter(visible).filter((el) => !name(el))
    .map((el) => el.outerHTML.slice(0, 80));
  const unnamedButtons = Array.from(document.querySelectorAll("button, a[href]"))
    .filter(visible).filter((el) => !(el.textContent || "").trim() && !name(el)).map((el) => el.outerHTML.slice(0, 80));
  return { unnamedControls, unnamedButtons };
};

const browser = await chromium.launch();
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await page.goto(BASE + "/");
  await page.getByRole("button", { name: "Explore the demo" }).click();
  await page.waitForURL("**/app/dashboard");
  for (const section of SECTIONS) {
    await page.goto(`${BASE}/app/${section}`);
    await page.locator("main h1").waitFor();
    await page.waitForLoadState("networkidle");
    const { unnamedControls, unnamedButtons } = await page.evaluate(audit);
    check(`${section}: form controls have accessible names`, unnamedControls.length === 0, unnamedControls.join(" | "));
    check(`${section}: buttons and links have names`, unnamedButtons.length === 0, unnamedButtons.join(" | "));
  }
  await page.goto(`${BASE}/app/budget`);
  await page.locator("main h1").waitFor();
  // The skip link is the first focusable element and becomes visible when focused.
  const first = await page.evaluate(() => {
    const el = document.querySelector("a[href], button, input, select, textarea, [tabindex]:not([tabindex='-1'])");
    return { cls: el?.className || "", text: el?.textContent || "" };
  });
  await page.locator(".skip-link").focus();
  const shown = await page.evaluate(() => { const r = document.querySelector(".skip-link").getBoundingClientRect(); return r.top >= 0 && r.bottom <= innerHeight; });
  check("skip link is first in tab order and visible on focus", /skip-link/.test(first.cls) && shown, JSON.stringify(first));
  let outlined = 0, tabbed = 0;
  const missing = [];
  for (let i = 0; i < 12; i++) {
    await page.keyboard.press("Tab");
    tabbed += 1;
    const visibleFocus = await page.evaluate(() => {
      const s = getComputedStyle(document.activeElement);
      return (s.outlineStyle !== "none" && parseFloat(s.outlineWidth) > 0) || (s.boxShadow && s.boxShadow !== "none");
    });
    if (visibleFocus) outlined += 1;
    else missing.push(await page.evaluate(() => document.activeElement?.outerHTML.slice(0, 90)));
  }
  check("keyboard focus is visibly outlined", outlined === tabbed, `${outlined}/${tabbed} ${missing.join(" | ")}`);
} finally {
  await browser.close();
}
console.log(failures === 0 ? "ACCESSIBILITY CHECK: PASSED" : `ACCESSIBILITY CHECK: FAILED (${failures})`);
process.exit(failures === 0 ? 0 : 1);
