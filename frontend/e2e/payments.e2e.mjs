// Browser check of the reviewed, approved, SIMULATED payment flow on a FRESH demo workspace,
// following the demo fixture: blocked by the reserve floor -> contribution received
// once -> explicit approval -> simulated execution leaves BDT 29,000.00 -> double-click and
// retries never debit twice. Needs the app running and Playwright (see onboarding.e2e.mjs).
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
const text = async (locator) => norm(await locator.innerText());
const apiGet = (page, path) => page.evaluate(async (p) => (await fetch(p)).json(), path);

const browser = await chromium.launch();
try {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  const pageErrors = [];
  page.on("pageerror", (e) => pageErrors.push(String(e)));

  await page.goto(BASE + "/");
  await page.getByRole("button", { name: "Explore the demo" }).click();
  await page.waitForURL("**/app/dashboard");
  await page.getByRole("link", { name: "Payments", exact: true }).click();
  await page.waitForURL("**/app/payments");

  // 1. Compare fictional routes: A breaks the floor by BDT 1,000.00 today.
  await page.getByRole("button", { name: "Compare routes" }).click();
  const routeA = page.getByRole("region", { name: "Route A (fictional)" });
  await routeA.waitFor();
  const a = await text(routeA);
  check("route A total BDT 81,000.00", a.includes("BDT 81,000.00"));
  check("route A breaks the floor by 1,000", /-BDT 1,000\.00|BDT -1,000\.00/.test(a) && a.includes("Breaks the floor"));
  const c = await text(page.getByRole("region", { name: "Route C (fictional)" }));
  check("route C arrives late", c.includes("Arrives after the due date") && c.includes("BDT 80,500.00"));
  check("routes labelled fictional", (await text(page.locator("main"))).includes("fictional demonstrations"));
  await routeA.getByRole("button", { name: "Prepare route A for review" }).click();

  // 2. Review card: SIMULATED, blocked by reserve, approve disabled.
  await page.getByRole("heading", { name: "Review the payment" }).waitFor();
  const review = await text(page.locator("main"));
  check("review shows SIMULATED label", review.includes("SIMULATED — no real money moves"));
  check("review shows balance after 19,000 and block reason", review.includes("BDT 19,000.00") && review.includes("below its reserve floor"));
  check("approve disabled while blocked", await page.getByRole("button", { name: "Approve version 1" }).isDisabled());
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/payment-blocked.png`, fullPage: true });

  // 3. Receive the contribution once (Budget page), then come back and approve.
  await page.getByRole("link", { name: "Budget & Cash Flow" }).click();
  // Design B: contributions live on the "Contributions & reserve" tab of Budget & Cash Flow.
  await page.getByRole("tab", { name: "Contributions & reserve" }).click();
  const row = page.locator("tr", { hasText: "Family (demo)" });
  await row.getByRole("button", { name: /Mark received/ }).click();
  await row.getByText("Received").waitFor();
  check("balance BDT 110,000.00 after receipt", (await apiGet(page, "/api/accounts")).accounts[0].balance === "110000.00");
  await page.getByRole("link", { name: "Payments", exact: true }).click();
  await page.locator("tr", { hasText: "Ready for your review" }).getByRole("button", { name: "Open" }).click();
  await page.getByRole("heading", { name: "Review the payment" }).waitFor();
  check("review now shows balance after 29,000", (await text(page.locator("main"))).includes("BDT 29,000.00"));
  await page.getByRole("button", { name: "Approve version 1" }).click();
  await page.getByText("Approved by you").waitFor();

  // A second proposal for the same bill (route C), prepared before route A runs (owner's Windows finding).
  const second = await page.evaluate(async () => {
    const bill = (await (await fetch("/api/bills")).json()).bills[0];
    const account = (await (await fetch("/api/accounts")).json()).accounts[0];
    const r = await fetch("/api/payments/proposals", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ bill_id: bill.id, source_account_id: account.id, route: "C" }) });
    return r.json();
  });

  // 4. Double-click "Run simulated payment": one execution, one debit.
  await page.getByRole("button", { name: "Run simulated payment" }).dblclick();
  await page.getByRole("heading", { name: "Simulated receipt" }).waitFor();
  const receipt = await text(page.locator("main"));
  check("receipt is SIMULATED with receipt number", receipt.includes("SIMULATED") && /SIM-[0-9A-F]{8}/.test(receipt));
  check("receipt totals", receipt.includes("BDT 81,000.00") && receipt.includes("BDT 29,000.00") && receipt.includes("AUD 1,000.00"));
  const accounts = (await apiGet(page, "/api/accounts")).accounts;
  const executions = (await apiGet(page, "/api/payments/executions")).executions;
  const bills = (await apiGet(page, "/api/bills")).bills;
  const debits = (await apiGet(page, "/api/transactions")).transactions.filter((t) => t.kind === "payment" || t.kind === "fee");
  check("balance BDT 29000.00 after execution", accounts[0].balance === "29000.00", accounts[0].balance);
  check("exactly one execution after double-click", executions.length === 1, String(executions.length));
  check("exactly one payment and one fee debit", debits.length === 2, String(debits.length));
  check("bill settled once", bills[0].status === "settled" && bills[0].settled_by_execution_id === executions[0].execution_id);
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/receipt.png`, fullPage: true });

  // 5. Retry from the browser with a new key returns the prior result.
  const retry = await page.evaluate(async (id) => {
    const r = await fetch(`/api/payments/proposals/${id}/execute`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ idempotency_key: "browser-retry-0001" }),
    });
    return r.json();
  }, executions[0].proposal_id);
  check("retry replays the same execution", retry.replayed === true && retry.execution_id === executions[0].execution_id);
  check("balance unchanged after retry", (await apiGet(page, "/api/accounts")).accounts[0].balance === "29000.00");

  // 6. Refund record does not move money.
  await page.getByLabel("Amount").fill("200.00");
  await page.getByLabel("Reason").fill("Course dropped");
  await page.getByRole("button", { name: "Add" }).click();
  await page.locator(".refund-draft").waitFor();
  check("refund draft shown, balance unchanged", (await apiGet(page, "/api/accounts")).accounts[0].balance === "29000.00");

  // 7. Print stylesheet hides navigation and keeps the SIMULATED label.
  await page.emulateMedia({ media: "print" });
  check("print hides sidebar", !(await page.locator("#sidebar").isVisible()));
  check("print keeps SIMULATED label", await page.locator(".receipt .simulated-banner").isVisible());
  await page.emulateMedia({ media: "screen" });

  // The other proposal for the now-settled bill is listed and opened as unavailable, and the server refuses it.
  await page.getByRole("button", { name: "Back to payments" }).click();
  const secondRow = page.locator("#proposals tr", { hasText: "Unavailable — bill already settled" });
  await secondRow.waitFor();
  check("second proposal listed as unavailable (bill settled)", (await secondRow.count()) === 1 && (await page.locator("#proposals tr", { hasText: "Ready for your review" }).count()) === 0);
  await secondRow.getByRole("button", { name: "Open" }).click();
  await page.getByRole("heading", { name: "Review the payment" }).waitFor();
  const settledView = await text(page.locator("main"));
  check("review explains the bill is already settled", settledView.includes("already paid by another simulated payment"));
  check("no approve button for the settled bill's proposal", (await page.getByRole("button", { name: /Approve version/ }).count()) === 0);
  const refused = await page.evaluate(async (p) => {
    const r = await fetch(`/api/payments/proposals/${p.id}/approve`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ version: p.version, terms_hash: p.terms_hash }) });
    return { status: r.status, code: (await r.json()).error?.code };
  }, second);
  check("server refuses approval: bill_settled", refused.status === 409 && refused.code === "bill_settled", JSON.stringify(refused));
  check("still one execution and BDT 29,000.00", (await apiGet(page, "/api/payments/executions")).executions.length === 1 && (await apiGet(page, "/api/accounts")).accounts[0].balance === "29000.00");

  // 8. Trust Center: activity log and nothing pending.
  await page.getByRole("link", { name: "Safety & Trust", exact: true }).click();
  await page.getByRole("heading", { name: "Activity log" }).waitFor();
  await page.getByText("Nothing is waiting for your approval.").waitFor();
  await page.getByRole("cell", { name: "Simulated payment executed" }).waitFor();
  const trust = await text(page.locator("main"));
  check("trust log shows approval and simulated execution", trust.includes("Payment approved by you") && trust.includes("Simulated payment executed"));
  check("nothing pending", trust.includes("Nothing is waiting for your approval."));

  // 9. Arabic RTL on the payments page at phone width.
  await page.evaluate(async () => {
    const prefs = await (await fetch("/api/preferences")).json();
    await fetch("/api/preferences", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ language: "ar", display_currency: prefs.display_currency, time_zone: prefs.time_zone }),
    });
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(BASE + "/app/payments");
  await page.waitForFunction(() => document.documentElement.dir === "rtl");
  await page.getByRole("heading", { name: "سجل الدفعات (محاكاة)" }).waitFor();
  check("Arabic payments heading", (await page.locator("h1").innerText()) === "المدفوعات والتحويلات");
  check("no horizontal overflow (ar, 390px)", !(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)));
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/payments-ar-mobile.png`, fullPage: true });
  check("no page errors", pageErrors.length === 0, pageErrors.join(" | "));
} finally {
  await browser.close();
}
console.log(failures === 0 ? "PAYMENTS E2E: PASSED" : `PAYMENTS E2E: FAILED (${failures})`);
process.exit(failures === 0 ? 0 : 1);
