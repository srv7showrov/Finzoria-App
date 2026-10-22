// Browser checks for the Stage B core flows on a FRESH demo workspace (fictional fixture data).
// Needs a running app (default http://127.0.0.1:8000, override with FINZORIA_URL) and Playwright
// (see onboarding.e2e.mjs). Run: npm run e2e:finance
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
// Intl uses non-breaking spaces between the currency code and the amount.
const text = async (page, selector) => (await page.locator(selector).innerText()).replace(/[\u00a0\u202f]/g, " ");

const browser = await chromium.launch();
try {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  const pageErrors = [];
  page.on("pageerror", (e) => pageErrors.push(String(e)));

  // Dashboard derived from shared services.
  await page.goto(BASE + "/");
  await page.getByRole("button", { name: "Explore the demo" }).click();
  await page.waitForURL("**/app/dashboard");
  await page.getByText("Planned remainder").waitFor();
  const dash = await text(page, "main");
  check("dashboard balance", dash.includes("BDT 100,000.00"));
  check("dashboard planned remainder", /Planned remainder\s*BDT 12,500\.00/.test(dash));
  check("dashboard forecast labelled", dash.includes("Forecast — not available cash"));
  check("dashboard reserve floor", /Minimum balance \(floor\)\s*BDT 20,000\.00/.test(dash));
  check("dashboard upcoming tuition", dash.includes("Tuition installment (demo)") && dash.includes("AUD 1,000.00"));
  check("dashboard expected contribution", /Expected contributions \(not received yet\)\s*BDT 10,000\.00/.test(dash));
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/dashboard.png`, fullPage: true });

  // Budget: fixture arithmetic, receive contribution once, delayed-funding scenario.
  await page.getByRole("link", { name: "Budget & Cash Flow" }).click();
  await page.waitForURL("**/app/budget");
  await page.getByText("Planned remainder").first().waitFor();
  const budget = await text(page, "main");
  check("budget planned income/expenses/remainder", budget.includes("BDT 45,000.00") && budget.includes("BDT 32,500.00") && budget.includes("BDT 12,500.00"));
  // Scenario first (contribution still expected): delay to Oct 24 relative to the seeded date.
  // Design B groups Budget & Cash Flow into tabs; each step opens the tab that holds its tool.
  await page.getByRole("tab", { name: "Contributions & reserve" }).click();
  const contributionRow = page.locator("tr", { hasText: "Family (demo)" });
  await contributionRow.getByRole("button", { name: /Mark received/ }).waitFor();
  await page.getByRole("tab", { name: "What-if" }).click();
  const scenarioForm = page.locator("form.subform", { hasText: "Delay a contribution" });
  const seededDate = new Date();
  seededDate.setDate(seededDate.getDate() + 5);
  const delayed = seededDate.toISOString().slice(0, 10);
  await scenarioForm.getByLabel("New expected date").fill(delayed);
  await scenarioForm.getByRole("button", { name: "Run scenario" }).click();
  await page.locator(".scenario-result").waitFor();
  const scenario = await text(page, ".scenario-result");
  check("delay scenario shows route timing", scenario.includes("Route A (fictional)") && scenario.includes("Route B (fictional)"));
  check("delay scenario: A late, B on time", /Route A \(fictional\)[^\n]*\n?[^]*?No/.test(scenario) && scenario.includes("Yes"));
  await page.getByRole("tab", { name: "Contributions & reserve" }).click();
  await contributionRow.getByRole("button", { name: /Mark received/ }).click();
  await page.locator("tr", { hasText: "Family (demo)" }).getByText("Received").waitFor();
  await contributionRow.getByRole("button", { name: /Mark received/ }).waitFor({ state: "detached" }).catch(() => {});
  const accounts = await page.evaluate(async () => (await (await fetch("/api/accounts")).json()).accounts);
  check("contribution credited once (BDT 110000.00)", accounts[0].balance === "110000.00", accounts[0].balance);
  // Actual transactions cannot be dated in the future (form cap + server rejection, nothing posted).
  await page.getByRole("tab", { name: "Plan & actuals" }).click();
  const txForm = page.locator("form.subform", { hasText: "Record an actual transaction" });
  const dateInput = txForm.getByLabel("Date", { exact: true });
  const todayLocal = await page.evaluate(() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  });
  check("transaction date capped at today", (await dateInput.getAttribute("max")) === todayLocal);
  const future = await page.evaluate(async (acct) => {
    const r = await fetch("/api/transactions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ account_id: acct, kind: "income", category: "income", amount: "10000.00", occurred_on: "2099-01-01" }),
    });
    return { status: r.status, body: await r.json() };
  }, accounts[0].id);
  const afterFuture = await page.evaluate(async () => (await (await fetch("/api/accounts")).json()).accounts[0].balance);
  check("future-dated income rejected, balance unchanged", future.status === 422 && future.body.error.code === "future_date" && afterFuture === "110000.00", `${future.status} ${afterFuture}`);
  // Explicitly record a planned expense as paid: one debit, linked, no duplicate.
  const plan = await page.evaluate(async (day) => {
    const r = await fetch("/api/budget/entries", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind: "expense", category: "books", description: "Lab manual (e2e)", amount: "5000.00", currency: "BDT", start_date: day, recurrence: "none" }),
    });
    return r.json();
  }, todayLocal);
  await page.reload();
  await page.getByRole("tab", { name: "Plan & actuals" }).click();
  await page.getByText("are not linked to plans automatically", { exact: false }).waitFor().catch(() => {});
  check("independent-transaction note shown", (await text(page, "main")).includes("are not linked to plans automatically"));
  const planRow = page.locator("#planned-items tr", { hasText: "Lab manual (e2e)" }).first();
  await planRow.getByRole("button", { name: /Record as paid/ }).click();
  await page.locator("#planned-items tr", { hasText: "Lab manual (e2e)" }).first().getByText("Recorded").waitFor();
  const afterRecord = await page.evaluate(async () => (await (await fetch("/api/accounts")).json()).accounts[0].balance);
  const dup = await page.evaluate(async ({ id, day, acct }) => {
    const r = await fetch(`/api/budget/entries/${id}/record`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ occurrence_date: day, account_id: acct, occurred_on: day }),
    });
    return r.status;
  }, { id: plan.id, day: todayLocal, acct: accounts[0].id });
  const linked = (await page.evaluate(async () => (await (await fetch("/api/transactions")).json()).transactions)).filter((t) => t.source_type === "plan_occurrence");
  check("record as paid debits once and links", afterRecord === "105000.00" && linked.length === 1, afterRecord);
  check("second record of the same occurrence rejected (409)", dup === 409 && (await page.evaluate(async () => (await (await fetch("/api/accounts")).json()).accounts[0].balance)) === "105000.00");
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/budget.png`, fullPage: true });

  // Currency: converter with provenance and unsupported pair message.
  await page.getByRole("link", { name: "Currencies", exact: true }).click();
  await page.waitForURL("**/app/currency");
  const converter = page.locator(".card", { hasText: "Converter" });
  await converter.getByRole("button", { name: "Convert" }).click();
  await converter.locator(".big-result").waitFor();
  const conv = (await converter.innerText()).replace(/[\u00a0\u202f]/g, " ");
  check("convert AUD 1000 → BDT 80000 (derived inverse of fixture)", conv.includes("BDT 80,000.00") && conv.includes("inverse"));
  await converter.getByRole("combobox").first().selectOption("EUR");
  await converter.getByRole("button", { name: "Convert" }).click();
  await converter.getByText("No rate is available for this pair").waitFor();
  check("unsupported pair shown, not converted at 1", true);
  const ratesText = await text(page, "main");
  check("fixture rate labelled", ratesText.includes("fixture rate, fictional test data"));

  // Arabic RTL and mobile layout on the budget page.
  await page.evaluate(async () => {
    const prefs = await (await fetch("/api/preferences")).json();
    await fetch("/api/preferences", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ language: "ar", display_currency: prefs.display_currency, time_zone: prefs.time_zone }),
    });
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(BASE + "/app/budget");
  await page.waitForFunction(() => document.documentElement.dir === "rtl");
  await page.locator(".stat-label").first().waitFor();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
  check("Arabic budget page is RTL", (await page.evaluate(() => document.documentElement.dir)) === "rtl");
  check("Arabic heading translated", (await page.locator("h1").innerText()) === "الميزانية والتدفق النقدي");
  check("no horizontal page overflow at 390px", !overflow);
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/budget-ar-mobile.png`, fullPage: true });
  check("no page errors", pageErrors.length === 0, pageErrors.join(" | "));
} finally {
  await browser.close();
}
console.log(failures === 0 ? "FINANCE E2E: PASSED" : `FINANCE E2E: FAILED (${failures})`);
process.exit(failures === 0 ? 0 : 1);
