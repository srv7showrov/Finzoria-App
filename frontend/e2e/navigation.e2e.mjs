// Regression for the white-page crash "TypeError: l is not a function" (React effect cleanup)
// and for stale/invalid sessions. Mobile viewport (iPhone SE). Two browser behaviours are
// emulated with an init script:
//  - newer browsers where Element.scrollIntoView() returns a Promise (programmatic scroll
//    promises); an effect that returned that value crashed React on unmount;
// and a session cookie that the server no longer knows (another database / copy of the app),
// which must show a recovery screen, never a blank page, and never reuse another workspace.
// Needs the app running and Playwright (see onboarding.e2e.mjs).
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { chromium, devices } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const BASE = (process.env.FINZORIA_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

let failures = 0;
function check(name, ok, detail = "") {
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail ? ": " + detail : ""}`);
  if (!ok) failures += 1;
}
// Design B short sidebar labels (page headings keep the full section names).
const SECTIONS = ["Dashboard", "AI Workspace", "Payments", "Currencies", "Budget & Cash Flow", "Student Funding", "Safety & Trust", "Reports"];

const browser = await chromium.launch();
try {
  const context = await browser.newContext({ ...devices["iPhone SE"] });
  await context.addInitScript(() => {
    const original = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = function (...args) {
      original.apply(this, args);
      return Promise.resolve(); // as in browsers with programmatic scroll promises
    };
  });
  const page = await context.newPage();
  const pageErrors = [];
  page.on("pageerror", (e) => pageErrors.push(String(e)));
  const navTo = async (name) => {
    const menu = page.getByRole("button", { name: "Menu" });
    if (await menu.isVisible()) await menu.click();
    await page.getByRole("link", { name, exact: true }).first().click();
    try {
      await page.locator("main h1, h1").first().waitFor({ timeout: 8000 });
    } catch {
      check(`navigating to ${name} shows a page (not blank)`, false, pageErrors.join(" | ") || "no heading");
      throw new Error("blank page");
    }
  };
  const rootText = async () => (await page.locator("#root").innerText()).trim();

  await page.goto(BASE + "/");
  await page.getByRole("button", { name: "Explore the demo" }).click();
  await page.waitForURL("**/app/dashboard");
  await page.locator("main h1").waitFor();
  const workspaceId = (await page.evaluate(async () => (await fetch("/api/session")).json())).workspace_id;

  // 1. Navigate through every section twice, including the AI workspace (chat) and the assistant panel.
  for (let round = 0; round < 2; round++) {
    for (const name of SECTIONS) {
      await navTo(name);
      check(`round ${round + 1}: ${name} renders`, (await rootText()).length > 50);
    }
  }
  const open = page.getByRole("button", { name: "Open assistant" });
  if (await open.isVisible()) {
    await open.click();
    await page.waitForTimeout(500);
    await page.keyboard.press("Escape");
  }
  await navTo("Budget & Cash Flow");
  check("no page errors while navigating", pageErrors.length === 0, pageErrors.join(" | "));

  // 2. The session becomes invalid (server no longer knows the cookie).
  await context.clearCookies();
  await context.addCookies([{ name: "finzoria_session", value: "stale-token-from-another-copy", url: BASE }]);
  await navTo("Payments");
  await page.getByRole("heading", { name: "Your demo session has ended" }).waitFor({ timeout: 10000 });
  check("invalid session shows a recovery screen (not blank)", (await rootText()).includes("Start a new demo workspace"));
  check("no page errors on invalid session", pageErrors.length === 0, pageErrors.join(" | "));

  // 3. Recovery starts a NEW workspace; nothing from the old one is reused or replayed.
  await page.getByRole("button", { name: "Start a new demo workspace" }).click();
  await page.waitForURL("**/app/dashboard");
  await page.locator("main h1").waitFor();
  const newId = (await page.evaluate(async () => (await fetch("/api/session")).json())).workspace_id;
  check("recovery created a different, fresh workspace", newId && newId !== workspaceId);
  const executions = (await page.evaluate(async () => (await fetch("/api/payments/executions")).json())).executions;
  check("no payments replayed in the new workspace", Array.isArray(executions) && executions.length === 0);
  await navTo("AI Workspace");
  await navTo("Reports");
  check("no page errors after recovery", pageErrors.length === 0, pageErrors.join(" | "));
  check("no horizontal overflow (390 px class device)", !(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)));
} catch (err) {
  if (String(err).includes("blank page")) failures += 0;
  else throw err;
} finally {
  await browser.close();
}
console.log(failures === 0 ? "NAVIGATION E2E: PASSED" : `NAVIGATION E2E: FAILED (${failures})`);
process.exit(failures === 0 ? 0 : 1);
