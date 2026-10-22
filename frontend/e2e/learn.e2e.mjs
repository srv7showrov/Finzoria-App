// Browser check of Design B Learn More and shared tabs on a FRESH demo workspace: section filters
// (pressed state and counts), every "Open feature" link reaching its working view (page, tab and
// focused card), keyboard operation of the Budget tabs, the Recent activity scroll region at
// phone width, and the Arabic page in RTL without overflow.
// Needs the app running and Playwright (see onboarding.e2e.mjs).
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const BASE = (process.env.FINZORIA_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

let failures = 0;
function check(name, ok, detail = "") {
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail ? ": " + detail : ""}`);
  if (!ok) failures += 1;
}

// Cards per filter, as listed on the page (8 sections + Settings).
const EXPECTED = { "All sections": 31, Dashboard: 2, "AI Workspace": 3, Payments: 4, Currencies: 4, "Budget & Cash Flow": 7, "Student Funding": 4, "Safety & Trust": 4, Reports: 2, Settings: 1 };

const browser = await chromium.launch();
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto(BASE + "/");
  await page.getByRole("button", { name: "Explore the demo" }).click();
  await page.waitForURL("**/app/dashboard");

  // 1. Sidebar entry above Settings opens the page.
  const navLinks = await page.locator("#sidebar a").allInnerTexts();
  check("Learn More is directly above Settings", navLinks.indexOf("Learn More") === navLinks.indexOf("Settings") - 1, navLinks.join(" | "));
  await page.getByRole("link", { name: "Learn More", exact: true }).click();
  await page.waitForURL("**/app/learn");
  await page.getByRole("heading", { level: 1, name: "Understand your Finzoria workspace" }).waitFor();
  check("Learn More heading shown", true);

  // 2. Filters: pressed state, card counts and status text.
  const filters = page.getByRole("group", { name: "Filter by section" });
  for (const [name, count] of Object.entries(EXPECTED)) {
    await filters.getByRole("button", { name, exact: true }).click();
    const pressed = await filters.getByRole("button", { name, exact: true }).getAttribute("aria-pressed");
    const cards = await page.locator(".learn-card").count();
    const status = await page.locator('[role="status"]').innerText();
    check(`filter ${name}: ${count} cards`, pressed === "true" && cards === count && status.includes(String(count)), `${pressed} ${cards} "${status}"`);
  }
  await filters.getByRole("button", { name: "All sections", exact: true }).click();
  // "Back to section filters" at the end of a group returns focus to the filters.
  const back = page.getByRole("link", { name: "Back to section filters" }).last();
  await back.scrollIntoViewIfNeeded();
  await back.click();
  await page.waitForFunction(() => document.activeElement?.id === "learn-filters", null, { timeout: 4000 }).catch(() => {});
  check("back link returns focus to the section filters", (await page.evaluate(() => document.activeElement?.id)) === "learn-filters");

  // 3. Every card has what/how/why and a working link to its feature.
  const links = await page.locator(".learn-open").evaluateAll((as) => as.map((a) => a.getAttribute("href")));
  check("31 feature links", links.length === 31, String(links.length));
  const complete = await page.locator(".learn-card").evaluateAll((cards) => cards.every((c) => c.querySelectorAll("dt").length === 3 && [...c.querySelectorAll("dd")].every((d) => d.textContent.trim().length > 10)));
  check("every card explains what, how and why", complete);
  const broken = [];
  for (let i = 0; i < links.length; i++) {
    await page.goto(BASE + "/app/learn");
    const link = page.locator(".learn-open").nth(i);
    const href = await link.getAttribute("href");
    await link.click();
    const url = new URL(href, BASE);
    await page.waitForURL((u) => new URL(u).pathname === url.pathname);
    await page.locator("main h1").first().waitFor();
    const hash = url.hash.slice(1);
    if (!hash) continue;
    // A hash names a card (focused once rendered) or a tab (selected).
    const ok = await page
      .waitForFunction(
        (id) => {
          const el = document.getElementById(id);
          if (el && document.activeElement === el && !el.closest("[hidden]")) return true;
          const tab = [...document.querySelectorAll('[role="tabpanel"]')].find((p) => p.getAttribute("data-tab-panel") === id);
          return Boolean(tab && !tab.hidden);
        },
        hash,
        { timeout: 6000 },
      )
      .then(() => true, () => false);
    if (!ok) broken.push(href);
  }
  check("every link opens its feature (card focused or tab selected)", broken.length === 0, broken.join(", "));

  // 4. Budget tabs: arrow keys move between tabs; the selected panel is shown, others hidden.
  await page.goto(BASE + "/app/budget");
  const first = page.getByRole("tab", { name: "Overview" });
  await first.focus();
  await page.keyboard.press("ArrowRight");
  const selected = await page.locator('[role="tab"][aria-selected="true"]').innerText();
  const focusedTab = await page.evaluate(() => document.activeElement?.getAttribute("role"));
  const panels = await page.locator('[role="tabpanel"]').evaluateAll((ps) => ps.map((p) => p.hidden));
  check("ArrowRight selects and focuses the next tab", selected.includes("Plan & actuals") && focusedTab === "tab", selected);
  check("exactly one tab panel visible", panels.filter((h) => !h).length === 1, JSON.stringify(panels));
  await page.keyboard.press("End");
  check("End selects the last tab", (await page.locator('[role="tab"][aria-selected="true"]').innerText()).includes("What-if"));

  // 5. Phone width: Recent activity is a named, focusable scroll region whose amount column can be reached.
  await page.evaluate(async () => {
    const accounts = (await (await fetch("/api/accounts")).json()).accounts;
    await fetch("/api/transactions", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ account_id: accounts[0].id, kind: "expense", category: "rent", description: "Accommodation payment", amount: "10000.00", occurred_on: new Date().toLocaleDateString("en-CA") }) });
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(BASE + "/app/dashboard");
  const region = page.getByRole("region", { name: "Recent activity table" });
  await region.waitFor();
  const info = await region.evaluate((el) => ({ tab: el.tabIndex, scrollable: el.scrollWidth > el.clientWidth }));
  await region.focus();
  // Keyboard scrolling is animated (smooth scrolling), so let each step settle.
  for (let i = 0; i < 12; i++) {
    await page.keyboard.press("ArrowRight");
    await page.waitForTimeout(120);
  }
  await page.waitForTimeout(400);
  const amountVisible = await page.evaluate(() => {
    const region = document.querySelector('.dash-recent [role="region"]');
    const cell = document.querySelector(".recent-table tbody td.num");
    const a = region.getBoundingClientRect();
    const b = cell.getBoundingClientRect();
    return { ok: b.left >= a.left - 1 && b.right <= a.right + 1, scrollLeft: region.scrollLeft, max: region.scrollWidth - region.clientWidth, region: [a.left, a.right], cell: [b.left, b.right] };
  });
  const hint = await page.locator(".dash-recent .scroll-hint").count();
  check("recent activity region is keyboard-focusable and scrollable", info.tab === 0 && info.scrollable, JSON.stringify(info));
  check("amount column reachable by keyboard scrolling", amountVisible.ok, JSON.stringify(amountVisible));
  check("scroll hint shown when columns are cut off", hint === 1);

  // 6. Arabic: RTL, translated heading, no page overflow at phone width.
  await page.evaluate(async () => {
    const p = await (await fetch("/api/preferences")).json();
    await fetch("/api/preferences", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ language: "ar", display_currency: p.display_currency, time_zone: p.time_zone }) });
  });
  await page.goto(BASE + "/app/learn");
  await page.getByRole("heading", { level: 1, name: "افهم مساحة عمل Finzoria الخاصة بك" }).waitFor();
  const ar = await page.evaluate(() => ({ dir: document.documentElement.dir, overflow: document.documentElement.scrollWidth > innerWidth + 1 }));
  check("Arabic Learn More is RTL without overflow", ar.dir === "rtl" && !ar.overflow, JSON.stringify(ar));
  check("no page errors", errors.length === 0, errors.join(" | "));
} finally {
  await browser.close();
}
console.log(failures === 0 ? "LEARN E2E: PASSED" : `LEARN E2E: FAILED (${failures})`);
process.exit(failures === 0 ? 0 : 1);
