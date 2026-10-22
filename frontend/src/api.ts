// All requests use relative /api paths: Vite proxies them in development and
// FastAPI serves them directly in the local release.

export interface FieldError {
  field: string;
  message: string;
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly fields: FieldError[] = [],
  ) {
    super(message);
  }
}

export const SESSION_INVALID_EVENT = "finzoria:session-invalid";

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      method,
      credentials: "same-origin",
      headers: body === undefined ? {} : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "network_error", "Network error");
  }
  const data: unknown = await response.json().catch(() => null);
  if (response.status === 401 && !path.startsWith("/session")) {
    // The server no longer knows this session (expired, reset, deleted, or another copy of the
    // app at the same address). The app shows a recovery screen; nothing is retried or replayed.
    window.dispatchEvent(new Event(SESSION_INVALID_EVENT));
  }
  if (!response.ok) {
    const err = (data as { error?: { code?: string; message?: string; fields?: FieldError[] } } | null)?.error;
    throw new ApiError(response.status, err?.code ?? "http_error", err?.message ?? response.statusText, err?.fields ?? []);
  }
  return data as T;
}

export type AiState = "unavailable" | "configured_unverified" | "connected" | "failed";

export interface AiStatus {
  state: AiState;
  reason: string | null;
  missing: string[];
  model?: string;
  provider?: string;
  last_check: { checked_at: string; model: string; ok: boolean; outcome: string } | null;
  /** This app's own request attempts (not the provider's remaining quota). Only on /api/ai/status. */
  requests?: { last_minute: number; last_24h: number; failed_last_24h: number; limits: { per_minute: number | null; per_day: number | null; per_turn: number | null } };
}

export interface Health {
  status: string;
  version: string;
  database: { status: string; schema_version: number };
  ai: AiStatus;
}

export interface Profile {
  display_name: string;
  institution: string;
  updated_at: string;
}

export interface Preferences {
  language: string;
  display_currency: string;
  time_zone: string;
  updated_at: string;
}

export interface Account {
  id: string;
  name: string;
  currency: string;
  opening_balance: string;
  opening_date: string;
  balance: string;
}

// --- Stage B types. Every amount is a decimal string in the stated currency. ---

export interface PeriodParams {
  month?: string;
  start?: string;
  end?: string;
  currency?: string;
}

export interface Period {
  start: string;
  end: string;
  kind: "month" | "custom";
}

export interface RateInfo {
  base: string;
  quote: string;
  rate: string;
  snapshot_id: string | null;
  mode: "identity" | "fixture" | "manual";
  source: string;
  as_of: string | null;
  derived: boolean;
}

export interface Valuation {
  display_currency: string;
  method: string;
  rates: RateInfo[];
  missing_pairs: string[];
}

export interface PlannedItem {
  entry_id: string;
  date: string;
  /** True only after this occurrence was explicitly recorded as paid/received. */
  fulfilled: boolean;
  transaction_id: string | null;
  kind: "income" | "expense";
  category: string;
  description: string;
  recurrence: "none" | "monthly";
  amount: string;
  currency: string;
  display_amount: string | null;
}

export interface Transaction {
  id: string;
  account_id: string;
  account_name: string;
  kind: "income" | "expense" | "contribution" | "payment" | "fee";
  direction: "credit" | "debit";
  category: string;
  description: string;
  amount: string;
  currency: string;
  occurred_on: string;
  source_type?: string | null;
  display_amount?: string | null;
}

export interface BudgetSummary {
  period: Period;
  display_currency: string;
  planned_income: string;
  planned_expenses: string;
  planned_remainder: string;
  actual_income: string;
  actual_expenses: string;
  actual_net: string;
  categories: { category: string; planned: string; actual: string; difference: string }[];
  planned_items: PlannedItem[];
  actual_items: Transaction[];
  unconverted_count: number;
  complete: boolean;
  valuation: Valuation;
}

export interface BudgetEntry {
  id: string;
  kind: "income" | "expense";
  category: string;
  description: string;
  amount: string;
  currency: string;
  start_date: string;
  recurrence: "none" | "monthly";
  end_date: string | null;
}

export interface ForecastEvent {
  date: string;
  kind: "planned_income" | "planned_expense" | "bill" | "expected_contribution";
  label: string;
  amount: string;
  balance_confirmed: string;
  balance_with_expected: string;
}

export interface Forecast {
  label: "forecast";
  display_currency: string;
  from: string;
  to: string;
  current_funds: string;
  projected_end_confirmed: string;
  projected_end_with_expected: string;
  lowest_confirmed: string;
  lowest_confirmed_date: string;
  lowest_with_expected: string;
  reserve_floor: string | null;
  gap_to_floor_confirmed: string | null;
  gap_to_floor_with_expected: string | null;
  events: ForecastEvent[];
  unconverted_count: number;
  complete: boolean;
  valuation: Valuation;
}

export interface Contribution {
  id: string;
  account_id: string;
  contributor: string;
  amount: string;
  currency: string;
  expected_date: string;
  certainty: "expected" | "uncertain";
  status: "expected" | "received" | "cancelled";
  received_on: string | null;
}

export interface Goal {
  id: string;
  name: string;
  currency: string;
  target_date: string | null;
  target_amount: string;
  allocated_amount: string;
  remaining: string;
  progress_percent: string;
}

export interface Reserve {
  account_id: string;
  /** Dashboard only: floor and headroom as whole-number percentages of this account's balance. */
  floor_percent?: string | null;
  headroom_percent?: string | null;
  account_name: string;
  currency: string;
  floor_amount: string;
  strict: boolean;
  current_balance: string;
  headroom: string;
}

export interface Bill {
  id: string;
  description: string;
  payee: string;
  category: "tuition" | "campus" | "housing" | "other";
  amount: string;
  currency: string;
  due_date: string;
  status: "open" | "settled" | "cancelled";
  version: number;
  settled_on: string | null;
  settled_by_execution_id: string | null;
  display_amount?: string | null;
  overdue?: boolean;
}

export interface ActivityEvent {
  id: number;
  at: string;
  event_type: string;
  entity_type: string | null;
  entity_id: string | null;
  details: Record<string, unknown>;
}

export interface Dashboard {
  period: Period;
  display_currency: string;
  today: string;
  balances: Account[];
  budget: Pick<BudgetSummary, "planned_income" | "planned_expenses" | "planned_remainder" | "actual_income" | "actual_expenses" | "actual_net" | "complete" | "unconverted_count">;
  forecast: Pick<Forecast, "current_funds" | "projected_end_confirmed" | "projected_end_with_expected" | "lowest_confirmed" | "lowest_confirmed_date" | "to" | "complete">;
  /** Expense categories, largest planned first; the share is of planned spending (server-computed). */
  categories: { category: string; planned: string; actual: string; difference: string; planned_share_percent: string | null }[];
  reserve: Reserve | null;
  upcoming_bills: (Bill & { display_amount: string | null; overdue: boolean })[];
  funding: {
    expected_contributions: string;
    uncertain_contributions_excluded: string;
    funding_gap_confirmed: string;
    funding_gap_with_expected: string;
  };
  goals: Goal[];
  recent_actions: ActivityEvent[];
  valuation: Valuation;
}

export interface RouteTiming {
  route: "A" | "B" | "C";
  status: "feasible" | "not_feasible" | "indeterminate";
  /** null when the result is indeterminate (an outflow could not be valued). */
  feasible: boolean | null;
  total: string;
  currency: string;
  initiation_date: string | null;
  estimated_arrival: string | null;
  on_time: boolean | null;
  balance_after?: string;
  assumptions: string[];
  missing_pairs?: string[];
}

export interface ScenarioResult {
  type: "delay_contribution" | "change_expense";
  saved: false;
  authorizes_payment: false;
  baseline: Forecast;
  scenario: Forecast;
  payment_timing?: { bill_id: string; case: "baseline" | "scenario"; due_date: string; routes: RouteTiming[] }[];
}

export interface Snapshot {
  id: string;
  base: string;
  quote: string;
  rate: string;
  mode: "fixture" | "manual";
  source: string;
  as_of: string;
  current: boolean;
}

export interface RateTarget {
  id: string;
  base: string;
  quote: string;
  threshold: string;
  direction: "at_or_above" | "at_or_below";
  met: boolean | null;
  current_rate: RateInfo | null;
  checked_at: string;
  check_mode: "on_refresh";
}

export interface Conversion {
  amount: string;
  from: string;
  to: string;
  result: string;
  rate: RateInfo;
}

export interface RateScenarioResult {
  amount: string;
  base: string;
  quote: string;
  change_percent: string;
  current_rate: RateInfo;
  scenario_rate: string;
  current_value: string;
  scenario_value: string;
  difference: string;
}

export interface PreferencesUpdate {
  language: string;
  display_currency: string;
  time_zone: string;
}

// The backend rejects unknown fields, so send exactly the editable fields even if a
// caller passes a full Preferences object (which also carries updated_at).
const preferencesBody = (p: PreferencesUpdate): PreferencesUpdate => ({
  language: p.language,
  display_currency: p.display_currency,
  time_zone: p.time_zone,
});

export interface RouteOption {
  route: "A" | "B" | "C";
  fictional: true;
  assumption: string;
  delivery_days: number;
  principal: string;
  fee: string;
  total_debit: string;
  initiation_date: string;
  estimated_arrival: string;
  on_time: boolean;
  funds_ok: boolean;
  reserve_ok: boolean;
  balance_after: string;
  gap_to_floor: string;
}

export interface RouteComparison {
  objective: { recipient_amount: string; recipient_currency: string; due_date: string; reserve_floor: string; source_currency: string };
  source_account: { id: string; name: string; currency: string; balance: string };
  rate: RateInfo;
  quote_valid_minutes: number;
  limits: string[];
  routes: RouteOption[];
}

export type ProposalStatus = "draft" | "ready_for_review" | "approved" | "executed_simulated" | "cancelled" | "failed" | "expired";

export interface ExecutionResult {
  execution_id: string;
  receipt_number: string;
  proposal_id: string;
  proposal_version: number;
  idempotency_key: string;
  status: "executed_simulated";
  simulated: true;
  executed_at: string;
  executed_on: string;
  bill_id: string;
  bill_description: string;
  recipient: string;
  recipient_amount: string;
  recipient_currency: string;
  route: string;
  rate: RateInfo;
  source_account_name: string;
  source_currency: string;
  principal: string;
  fee: string;
  total_debit: string;
  balance_before: string;
  balance_after: string;
  estimated_arrival: string;
  replayed: boolean;
  refunds?: { id: string; amount: string; currency: string; reason: string; created_at: string }[];
}

export interface Proposal {
  id: string;
  status: ProposalStatus;
  status_reason: string | null;
  version: number;
  terms_hash: string;
  approved_version: number | null;
  approved_at: string | null;
  created_at: string;
  simulated: true;
  terms: {
    bill: { id: string; version: number; description: string; payee: string; category: string; amount: string; currency: string; due_date: string };
    source_account: { id: string; name: string; currency: string };
    route: { code: string; delivery_days: number; assumption: string; fictional: true };
    quote: { id: string; created_at: string; expires_at: string };
    rate: RateInfo;
    recipient: string;
    recipient_amount: string;
    recipient_currency: string;
    source_currency: string;
    principal: string;
    fee: string;
    total_debit: string;
    initiation_date: string;
    estimated_arrival: string;
    on_time: boolean;
  };
  checks: {
    balance_now: string;
    balance_after: string;
    reserve_floor: string;
    gap_to_floor: string;
    funds_ok: boolean;
    reserve_ok: boolean;
    bill_current: boolean;
    expired: boolean;
    blocking: string[];
    currency: string;
  } | null;
  execution: ExecutionResult | null;
}

export interface BillInput {
  description: string;
  payee: string;
  category: "tuition" | "campus" | "housing" | "other";
  amount: string;
  currency: string;
  due_date: string;
}

// --- Stage C: AI Financial Workspace ---

export type ChatMode = "concise" | "detailed";

export interface ToolCard {
  type: string;
  [key: string]: unknown;
}

export interface ToolCallView {
  tool: string;
  status: "ok" | "error" | "rejected";
  round: number;
  card: ToolCard | null;
  error: string | null;
}

export interface ChatMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  mode: ChatMode;
  language: string;
  status: "ok" | "failed" | "refused" | "incomplete";
  error_code: string | null;
  /** Model request attempts for this answer, including failed ones. */
  model_requests?: number;
  created_at: string;
  tool_calls: ToolCallView[];
}

export interface AssistantAction {
  id: string;
  kind: "budget_entry" | "bill" | "contribution";
  payload: Record<string, string | null>;
  status: "pending" | "confirmed" | "dismissed" | "failed";
  result_id: string | null;
  status_reason: string | null;
  conversation_id: string | null;
}

export interface ConversationDetail {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  messages: ChatMessage[];
  actions: AssistantAction[];
}

export interface ChatResult {
  conversation_id: string;
  status: ChatMessage["status"];
  error_code: string | null;
  conversation: ConversationDetail;
}

export interface InvoiceExtraction {
  fields: { payee: string | null; description: string | null; amount: string | null; currency: string | null; due_date: string | null };
  warnings: string[];
  notes: string[];
  requires_review: true;
  saved: false;
}

// --- Stage C Prompt 5 types ---

export type ApplicationStatus = "planning" | "applied" | "awarded" | "declined" | "withdrawn";

export interface FundingApplication {
  id: string;
  name: string;
  provider: string;
  status: ApplicationStatus;
  deadline: string | null;
  notes: string;
  updated_at: string;
}

export interface ChecklistGroup {
  key: string;
  items: { key: string; done: boolean }[];
}

export interface Checklists {
  groups: ChecklistGroup[];
  jurisdiction: string;
}

export interface FundingResource {
  key: string;
  url: string;
  kind: string;
  jurisdiction: string;
}

export interface FundingOverview {
  applications: FundingApplication[];
  checklists: Checklists;
  resources: FundingResource[];
  checked: { date: string; status: string; reason: string };
  jurisdiction: string;
  today: string;
}

export interface WorkIncomeInput {
  hourly_rate: string;
  hours_per_week: string;
  weeks: number;
  currency: string;
  basis: "gross" | "net";
  deduction_percent: string;
}

export interface WorkIncomeResult {
  currency: string;
  basis: "gross" | "net";
  deduction_percent: string;
  weeks: number;
  hours_per_week: string;
  weekly_gross: string | null;
  weekly_net: string;
  total_gross: string | null;
  total_net: string;
  deductions_total: string | null;
  assumptions: string[];
}

export interface Report {
  period: Period;
  display_currency: string;
  generated_for: string;
  totals: Pick<BudgetSummary, "planned_income" | "planned_expenses" | "planned_remainder" | "actual_income" | "actual_expenses" | "actual_net">;
  categories: BudgetSummary["categories"];
  funding: Dashboard["funding"];
  forecast: Dashboard["forecast"];
  reserve: Reserve | null;
  goals: Goal[];
  transfer_fees: { items: { date: string; description: string; amount: string; currency: string }[]; total: string; unvalued_count: number };
  complete: boolean;
  unconverted_count: number;
  valuation: Valuation;
}

export interface DeadlineNotice {
  kind: "bill" | "contribution" | "application";
  id: string;
  date: string;
  title: string;
  detail: string;
  amount: string | null;
  currency: string | null;
  days: number;
  state: "overdue" | "today" | "soon";
}

export const reportCsvUrl = (p: PeriodParams): string => `/api/reports/export.csv${query(p)}`;
export const CALENDAR_URL = "/api/calendar.ics";
export const EXPORT_URL = "/api/workspace/export";

export const api = {
  health: () => request<Health>("GET", "/health"),
  aiStatus: () => request<AiStatus>("GET", "/ai/status"),
  startSession: () => request<{ workspace_id: string; created: boolean }>("POST", "/session"),
  session: () => request<{ workspace_id: string; data_mode: string }>("GET", "/session"),
  profile: () => request<Profile>("GET", "/profile"),
  saveProfile: (body: { display_name: string; institution: string }) => request<Profile>("PUT", "/profile", body),
  preferences: () => request<Preferences>("GET", "/preferences"),
  savePreferences: (body: PreferencesUpdate) => request<Preferences>("PUT", "/preferences", preferencesBody(body)),
  accounts: () => request<{ accounts: Account[] }>("GET", "/accounts"),

  dashboard: (p: PeriodParams) => request<Dashboard>("GET", `/dashboard${query(p)}`),
  activity: () => request<{ events: ActivityEvent[] }>("GET", "/activity"),
  summary: (p: PeriodParams) => request<BudgetSummary>("GET", `/budget/summary${query(p)}`),
  cashflow: (p: PeriodParams) => request<Forecast>("GET", `/cashflow${query(p)}`),
  scenario: (p: PeriodParams, body: Record<string, string>) => request<ScenarioResult>("POST", `/scenarios${query(p)}`, body),
  entries: () => request<{ entries: BudgetEntry[] }>("GET", "/budget/entries"),
  createEntry: (body: Omit<BudgetEntry, "id">) => request<BudgetEntry>("POST", "/budget/entries", body),
  // Explicitly links one planned occurrence to a new actual transaction (no automatic matching).
  recordOccurrence: (entryId: string, body: { occurrence_date: string; account_id: string; occurred_on: string }) =>
    request<{ transaction_id: string; balances: Account[] }>("POST", `/budget/entries/${encodeURIComponent(entryId)}/record`, body),
  deleteEntry: (id: string) => request<{ deleted: boolean }>("DELETE", `/budget/entries/${encodeURIComponent(id)}`),
  transactions: () => request<{ transactions: Transaction[] }>("GET", "/transactions"),
  createTransaction: (body: { account_id: string; kind: "income" | "expense"; category: string; description: string; amount: string; occurred_on: string }) =>
    request<{ id: string; balances: Account[] }>("POST", "/transactions", body),
  contributions: () => request<{ contributions: Contribution[] }>("GET", "/contributions"),
  createContribution: (body: { account_id: string; contributor: string; amount: string; expected_date: string; certainty: "expected" | "uncertain" }) =>
    request<Contribution>("POST", "/contributions", body),
  receiveContribution: (id: string) =>
    request<{ contribution: Contribution; credited: boolean; balances: Account[] }>("POST", `/contributions/${encodeURIComponent(id)}/receive`, {}),
  cancelContribution: (id: string) => request<Contribution>("POST", `/contributions/${encodeURIComponent(id)}/cancel`),
  goals: () => request<{ goals: Goal[] }>("GET", "/goals"),
  createGoal: (body: { name: string; target_amount: string; allocated_amount: string; currency: string; target_date: string | null }) =>
    request<{ goals: Goal[] }>("POST", "/goals", body),
  updateGoal: (id: string, allocated_amount: string) => request<{ goals: Goal[] }>("PUT", `/goals/${encodeURIComponent(id)}`, { allocated_amount }),
  reserve: () => request<{ reserve: Reserve | null }>("GET", "/reserve"),
  saveReserve: (body: { account_id: string; floor_amount: string }) => request<{ reserve: Reserve }>("PUT", "/reserve", body),
  rates: () => request<{ snapshots: Snapshot[]; targets: RateTarget[]; reference_provider: { connected: boolean; reason: string } }>("GET", "/rates"),
  addManualRate: (body: { base: string; quote: string; rate: string }) => request<{ id: string; snapshots: Snapshot[] }>("POST", "/rates/manual", body),
  convert: (amount: string, from: string, to: string) => request<Conversion>("GET", `/rates/convert${query({ amount, from, to })}`),
  rateScenario: (body: { base: string; quote: string; amount: string; change_percent: string }) => request<RateScenarioResult>("POST", "/rates/scenario", body),
  addTarget: (body: { base: string; quote: string; threshold: string; direction: "at_or_above" | "at_or_below" }) =>
    request<{ targets: RateTarget[] }>("POST", "/rates/targets", body),
  deleteTarget: (id: string) => request<{ targets: RateTarget[] }>("DELETE", `/rates/targets/${encodeURIComponent(id)}`),

  bills: () => request<{ bills: Bill[] }>("GET", "/bills"),
  createBill: (body: BillInput) => request<Bill>("POST", "/bills", body),
  updateBill: (id: string, body: BillInput) => request<Bill>("PUT", `/bills/${encodeURIComponent(id)}`, body),
  routes: (billId: string, sourceAccountId: string) =>
    request<RouteComparison>("GET", `/bills/${encodeURIComponent(billId)}/routes${query({ source_account_id: sourceAccountId })}`),
  proposals: () => request<{ proposals: Proposal[] }>("GET", "/payments/proposals"),
  proposal: (id: string) => request<Proposal>("GET", `/payments/proposals/${encodeURIComponent(id)}`),
  createProposal: (body: { bill_id: string; source_account_id: string; route: string }) => request<Proposal>("POST", "/payments/proposals", body),
  // Approval names the exact version and fingerprint the person reviewed.
  approveProposal: (p: Pick<Proposal, "id" | "version" | "terms_hash">) =>
    request<Proposal>("POST", `/payments/proposals/${encodeURIComponent(p.id)}/approve`, { version: p.version, terms_hash: p.terms_hash }),
  executeProposal: (id: string, idempotencyKey: string) =>
    request<ExecutionResult>("POST", `/payments/proposals/${encodeURIComponent(id)}/execute`, { idempotency_key: idempotencyKey }),
  cancelProposal: (id: string) => request<Proposal>("POST", `/payments/proposals/${encodeURIComponent(id)}/cancel`),
  refreshProposal: (id: string) => request<Proposal>("POST", `/payments/proposals/${encodeURIComponent(id)}/refresh`),
  executionStatus: (key: string) =>
    request<{ found: boolean; result?: ExecutionResult }>("GET", `/payments/executions/status${query({ idempotency_key: key })}`),
  executions: () => request<{ executions: ExecutionResult[] }>("GET", "/payments/executions"),
  execution: (id: string) => request<ExecutionResult>("GET", `/payments/executions/${encodeURIComponent(id)}`),
  recordRefund: (id: string, body: { amount: string; reason: string }) =>
    request<ExecutionResult>("POST", `/payments/executions/${encodeURIComponent(id)}/refunds`, body),

  chat: (body: { conversation_id?: string; message: string; mode: ChatMode }) => request<ChatResult>("POST", "/assistant/chat", body),
  conversations: () => request<{ conversations: { id: string; title: string; updated_at: string }[] }>("GET", "/assistant/conversations"),
  conversation: (id: string) => request<ConversationDetail>("GET", `/assistant/conversations/${encodeURIComponent(id)}`),
  pendingActions: () => request<{ actions: AssistantAction[] }>("GET", "/assistant/actions"),
  // Explicit user confirmation; the assistant itself can never call these.
  confirmAction: (id: string) => request<AssistantAction>("POST", `/assistant/actions/${encodeURIComponent(id)}/confirm`),
  dismissAction: (id: string) => request<AssistantAction>("POST", `/assistant/actions/${encodeURIComponent(id)}/dismiss`),
  extractInvoice: (text: string) => request<InvoiceExtraction>("POST", "/assistant/invoice/extract", { text }),
  funding: () => request<FundingOverview>("GET", "/funding"),
  createApplication: (body: Omit<FundingApplication, "id" | "updated_at">) => request<FundingApplication>("POST", "/funding/applications", body),
  updateApplication: (id: string, body: Omit<FundingApplication, "id" | "updated_at">) =>
    request<FundingApplication>("PUT", `/funding/applications/${encodeURIComponent(id)}`, body),
  deleteApplication: (id: string) => request<{ deleted: boolean }>("DELETE", `/funding/applications/${encodeURIComponent(id)}`),
  setChecklist: (key: string, done: boolean) => request<Checklists>("PUT", `/funding/checklist/${encodeURIComponent(key)}`, { done }),
  workIncome: (body: WorkIncomeInput) => request<WorkIncomeResult>("POST", "/funding/work-income", body),
  report: (p: PeriodParams) => request<Report>("GET", `/reports${query(p)}`),
  notices: () => request<{ notices: DeadlineNotice[]; today: string; window_days: number; background: false }>("GET", "/notices"),
  // Destructive controls: the server also requires the exact confirmation word.
  resetWorkspace: () => request<{ reset: boolean }>("POST", "/workspace/reset", { confirm: "RESET" }),
  deleteWorkspace: () => request<{ deleted: boolean }>("POST", "/workspace/delete", { confirm: "DELETE" }),
};

function query(params: object): string {
  const entries = Object.entries(params).filter((e): e is [string, string] => typeof e[1] === "string" && e[1] !== "");
  return entries.length ? `?${new URLSearchParams(entries).toString()}` : "";
}
