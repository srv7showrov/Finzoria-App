// Browser check of Stage C Prompt 5 on a FRESH demo workspace: funding calculator, checklist,
// application tracker -> dashboard deadline notice, reports equal to the dashboard, CSV and
// calendar downloads, print view, data reset/delete with typed confirmation, and every
// section in all six languages (RTL for Arabic) at phone width without overflow or raw keys.
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const BASE = (process.env.FINZORIA_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const SHOTS = process.env.FINZORIA_SCREENSHOTS || "";

let failures = 0;
function check(name, ok, detail = "") {
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail ? ": " + detail : ""}`);
  if (!ok) failures += 1;
}
const norm = (s) => s.replace(/[  ]/g, " ");
const apiGet = (page, path) => page.evaluate(async (p) => (await fetch(p)).json(), path);
const fetchText = (page, path) => page.evaluate(async (p) => { const r = await fetch(p); return { type: r.headers.get("content-type"), text: await r.text() }; }, path);
const setLanguage = (page, language) =>
  page.evaluate(async (lang) => {
    const prefs = await (await fetch("/api/preferences")).json();
    await fetch("/api/preferences", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ language: lang, display_currency: prefs.display_currency, time_zone: prefs.time_zone }),
    });
  }, language);

const SECTIONS = ["dashboard", "workspace", "payments", "currency", "budget", "funding", "trust", "reports", "learn"];

const browser = await chromium.launch();
try {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  const pageErrors = [];
  page.on("pageerror", (e) => pageErrors.push(String(e)));
  await page.goto(BASE + "/");
  await page.getByRole("button", { name: "Explore the demo" }).click();
  await page.waitForURL("**/app/dashboard");

  // 1. Funding: calculator (server-computed), checklist, application tracker.
  await page.getByRole("link", { name: "Student Funding", exact: true }).click();
  await page.waitForURL("**/app/funding");
  const main = page.locator("main");
  await main.getByText("Guidance here covers Australia only").waitFor();
  await main.getByLabel("Hourly rate").fill("25.50");
  await main.getByLabel("Hours per week").fill("20");
  await main.getByLabel("Number of weeks").fill("4");
  await main.getByLabel("Deductions (% you expect)").fill("12.5");
  await main.getByRole("button", { name: "Calculate" }).click();
  await main.getByText("Total after deductions (4 weeks)").waitFor();
  const calc = norm(await main.innerText());
  check("calculator totals", calc.includes("AUD 2,040.00") && calc.includes("AUD 1,785.00") && calc.includes("AUD 255.00"));
  check("calculator states no tax engine", calc.includes("No tax rules are modelled."));
  await main.getByLabel("Find out how to get your own credit report for free").check();
  await main.getByText("1 of 6 done").waitFor();
  check("checklist saved", (await apiGet(page, "/api/funding")).checklists.groups[1].items[1].done === true);
  check("resources marked unverified with date", calc.includes("network blocked, checked 2026-10-19") || (await main.innerText()).includes("checked 2026-10-19"));
  await main.getByLabel("Name", { exact: true }).fill("Faculty bursary (demo)");
  await main.getByLabel("Provider").fill("Demo University");
  const deadline = await page.evaluate(() => { const d = new Date(); d.setDate(d.getDate() + 5); return d.toLocaleDateString("en-CA"); });
  await main.getByLabel("Deadline").fill(deadline);
  await main.getByRole("button", { name: "Add application" }).click();
  await main.getByLabel("Status for Faculty bursary (demo)").waitFor();
  await main.getByLabel("Status for Faculty bursary (demo)").selectOption("applied");
  await page.waitForFunction(async () => (await (await fetch("/api/funding")).json()).applications[0]?.status === "applied");
  check("application tracked", true);
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/funding.png`, fullPage: true });

  // 2. Dashboard notices include the new deadline; calendar is date-only with a time zone.
  await page.getByRole("link", { name: "Dashboard", exact: true }).click();
  await page.getByRole("heading", { name: "Upcoming deadlines" }).waitFor();
  await main.getByText("Application: Faculty bursary (demo)").waitFor();
  check("notice says no background notifications", (await main.innerText()).includes("does not send background notifications"));
  const ics = await fetchText(page, "/api/calendar.ics");
  check("calendar is text/calendar", ics.type.startsWith("text/calendar"));
  check("calendar all-day with time zone", ics.text.includes(`DTSTART;VALUE=DATE:${deadline.replaceAll("-", "")}`) && /X-WR-TIMEZONE:\S+/.test(ics.text));

  // 3. Reports equal the dashboard; CSV and print.
  const dash = await apiGet(page, "/api/dashboard");
  await page.getByRole("link", { name: "Reports", exact: true }).click();
  await page.getByRole("heading", { name: "Period summary" }).waitFor();
  const rep = await apiGet(page, "/api/reports");
  check("report totals equal dashboard", ["planned_income", "planned_expenses", "planned_remainder", "actual_income", "actual_expenses"].every((k) => rep.totals[k] === dash.budget[k]));
  check("report funding equals dashboard", JSON.stringify(rep.funding) === JSON.stringify(dash.funding));
  const reportText = norm(await main.innerText());
  check("report shows planned remainder from service", reportText.includes(rep.totals.planned_remainder.replace(/\B(?=(\d{3})+(?!\d))/g, ",")));
  const csv = await fetchText(page, "/api/reports/export.csv");
  check("CSV downloads with totals", csv.type.startsWith("text/csv") && csv.text.includes(`total,,planned_remainder,,,${rep.totals.planned_remainder}`));
  const [download] = await Promise.all([page.waitForEvent("download"), main.getByRole("link", { name: "Download CSV" }).click()]);
  check("CSV link downloads a file", download.suggestedFilename().endsWith(".csv"), download.suggestedFilename());
  await page.emulateMedia({ media: "print" });
  check("print hides sidebar and controls", !(await page.locator("#sidebar").isVisible()) && !(await main.getByRole("button", { name: "Print or save as PDF" }).isVisible()));
  await page.emulateMedia({ media: "screen" });
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/reports.png`, fullPage: true });

  // 4. Every section in six languages at phone width: no overflow, no raw keys, RTL for Arabic.
  await page.setViewportSize({ width: 390, height: 844 });
  for (const lang of ["de", "zh-Hans", "bn", "hi", "ar", "en"]) {
    await setLanguage(page, lang);
    let overflow = [], rawKeys = [];
    for (const section of SECTIONS) {
      await page.goto(`${BASE}/app/${section}`);
      await page.locator("main h1").waitFor();
      await page.waitForLoadState("networkidle");
      if (await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)) overflow.push(section);
      const txt = await page.locator("body").innerText();
      const raw = txt.match(/\b(?:fund|rep|notice|data|ai|nav|pay|budget|dashboard|trust|currency|event|error)\.[a-zA-Z_.]+[a-zA-Z]\b/g);
      if (raw) rawKeys.push(`${section}:${raw.slice(0, 2).join(",")}`);
    }
    const dir = await page.evaluate(() => document.documentElement.dir);
    check(`${lang}: all sections and Learn More, no overflow at 390px`, overflow.length === 0, overflow.join(","));
    check(`${lang}: no untranslated keys`, rawKeys.length === 0, rawKeys.join(" "));
    check(`${lang}: direction`, dir === (lang === "ar" ? "rtl" : "ltr"), dir);
    if (SHOTS && (lang === "ar" || lang === "bn")) {
      await page.goto(`${BASE}/app/funding`);
      await page.locator("main h1").waitFor();
      await page.screenshot({ path: `${SHOTS}/funding-${lang}-mobile.png`, fullPage: true });
    }
  }
  await page.setViewportSize({ width: 1280, height: 900 });

  // 5. Reset needs the typed word; it restores the fixture balance and keeps preferences.
  await page.goto(BASE + "/app/budget");
  await page.getByRole("tab", { name: "Contributions & reserve" }).click();
  const row = page.locator("tr", { hasText: "Family (demo)" });
  await row.getByRole("button", { name: /Mark received/ }).click();
  await row.getByText("Received").waitFor();
  check("balance 110,000 before reset", (await apiGet(page, "/api/accounts")).accounts[0].balance === "110000.00");
  await page.goto(BASE + "/app/trust");
  const resetButton = page.getByRole("button", { name: "Reset workspace" });
  check("reset disabled until RESET typed", await resetButton.isDisabled());
  await page.getByLabel("Type RESET to confirm").fill("reset");
  check("lower-case does not enable reset", await resetButton.isDisabled());
  await page.getByLabel("Type RESET to confirm").fill("RESET");
  await resetButton.click();
  await page.waitForURL("**/app/dashboard");
  await page.locator("main h1").waitFor();
  check("reset restores 100,000 fixture balance", (await apiGet(page, "/api/accounts")).accounts[0].balance === "100000.00");
  check("reset removed applications", (await apiGet(page, "/api/funding")).applications.length === 0);

  // 6. Delete ends the session.
  await page.goto(BASE + "/app/trust");
  await page.getByLabel("Type DELETE to confirm").fill("DELETE");
  await page.getByRole("button", { name: "Delete workspace" }).click();
  await page.waitForURL((u) => new URL(u).pathname === "/");
  const status = await page.evaluate(async () => (await fetch("/api/accounts")).status);
  check("session ended after delete", status === 401, String(status));
  check("no page errors", pageErrors.length === 0, pageErrors.join(" | "));
} finally {
  await browser.close();
}
console.log(failures === 0 ? "SUPPORTING E2E: PASSED" : `SUPPORTING E2E: FAILED (${failures})`);
process.exit(failures === 0 ? 0 : 1);
