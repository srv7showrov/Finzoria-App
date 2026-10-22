import { useState } from "react";
import assistantPortrait from "../assets/assistant-portrait.webp";
import { createPortal } from "react-dom";
import { api, type AiStatus, type Bill, type Dashboard as DashboardData, type PeriodParams, type Proposal, type Transaction } from "../api";
import { useShell } from "../components/AppShell";
import { ErrorNotice, PeriodCaption, PeriodPicker, Stat, ValuationNote, label, useLoad } from "../components/finance";
import { Icon, categoryIcon, type IconName } from "../components/icons";
import { DeadlineNotices } from "../components/Notices";
import { Card, Loading, Money, ScrollRegion, StatusBadge, type StatusTone } from "../components/ui";
import { useI18n } from "../i18n";
import type { MessageKey } from "../i18n/types";
import { hrefFor, navigate, type Route } from "../router";

/** Every figure comes from the API (GET /api/dashboard composes the shared budget, cash-flow,
 * reserve and ledger services). No money arithmetic happens in the browser; bar widths use the
 * percentages the server computed. */
export function Dashboard() {
  const { t } = useI18n();
  const [period, setPeriod] = useState<PeriodParams>({});
  const [customOpen, setCustomOpen] = useState(false);
  const { data, error } = useLoad(() => api.dashboard(period), [period]);

  return (
    <>
      <PeriodSelect period={period} data={data} onMonth={(month) => (setCustomOpen(false), setPeriod({ month }))} onCustom={() => setCustomOpen(true)} />
      <div className="dash-heading">
        <h1 tabIndex={-1}>{t("dash.headline")}</h1>
        <p className="dash-subline">{t("dash.subline")}</p>
      </div>
      {customOpen && <PeriodPicker value={{ ...period, start: period.start ?? "" }} onChange={setPeriod} />}
      <ErrorNotice error={error} />
      {!data ? (
        !error && <Loading />
      ) : (
        <>
          <div className="dash-row dash-row-top">
            <BalanceCard data={data} />
            <AssistantCard bill={primaryBill(data.upcoming_bills)} />
          </div>
          <div className="dash-row dash-row-mid">
            <BudgetCard data={data} />
            <BillCard data={data} />
          </div>
          <NextActions data={data} />
          <RecentActivity />
          <MoreDetails data={data}>
            <PeriodCaption start={data.period.start} end={data.period.end} />
            <div className="grid-3">
              <PlanCard data={data} />
              <ForecastCard data={data} />
              <FundingCard data={data} />
            </div>
            <div className="grid-2">
              <DeadlineNotices />
              <GoalsCard data={data} />
            </div>
            <ValuationNote valuation={data.valuation} unconverted={data.budget.unconverted_count} />
          </MoreDetails>
        </>
      )}
    </>
  );
}

// --- helpers ---------------------------------------------------------------------

function go(route: Route) {
  return (e: React.MouseEvent<HTMLAnchorElement>) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
    e.preventDefault();
    navigate(route);
  };
}

function AppLink({ route, className, children }: { route: Route; className?: string; children: React.ReactNode }) {
  return (
    <a href={hrefFor(route)} className={className} onClick={go(route)}>
      {children}
    </a>
  );
}

/** Earliest open tuition bill, otherwise the earliest open bill (the API sorts by due date). */
function primaryBill(bills: Bill[]): Bill | null {
  return bills.find((b) => b.category === "tuition") ?? bills[0] ?? null;
}

/** Places a node (usually a formatted amount) where a translation has its {amount} placeholder,
 * so each language keeps its own word order. */
function WithAmount({ text, amount }: { text: string; amount: React.ReactNode }) {
  const [before, after = ""] = text.split("{amount}");
  return (
    <>
      {before}
      {amount}
      {after}
    </>
  );
}

const isNegative = (amount: string) => amount.trim().startsWith("-");
const withoutSign = (amount: string) => amount.trim().replace(/^-/, "");

function CardTitle({ icon, children, id }: { icon: IconName; children: React.ReactNode; id?: string }) {
  return (
    <h2 className="dash-card-title" id={id}>
      <Icon name={icon} size={24} />
      {children}
    </h2>
  );
}

// --- period ------------------------------------------------------------------------

function monthOptions(locale: string, anchor: string): { value: string; text: string }[] {
  const [y = 1970, m = 1] = anchor.split("-").map(Number);
  const fmt = new Intl.DateTimeFormat(locale, { month: "long", year: "numeric", timeZone: "UTC" });
  const out = [];
  for (let offset = -6; offset <= 6; offset++) {
    const d = new Date(Date.UTC(y, m - 1 + offset, 1));
    out.push({ value: `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`, text: fmt.format(d) });
  }
  return out;
}

/** Month selector in the top bar; it sets the dashboard's period (the existing ?month= parameter). */
function PeriodSelect({ period, data, onMonth, onCustom }: { period: PeriodParams; data: DashboardData | null; onMonth: (m: string) => void; onCustom: () => void }) {
  const { t, locale } = useI18n();
  const { topbarSlot } = useShell();
  if (!topbarSlot || !data) return null;
  const today = data.today.slice(0, 7);
  const current = period.start ? "custom" : period.month ?? (data.period.kind === "month" ? data.period.start.slice(0, 7) : "custom");
  const options = monthOptions(locale, today);
  if (current !== "custom" && !options.some((o) => o.value === current)) options.unshift({ value: current, text: current });
  return createPortal(
    <label className="top-select">
      <Icon name="calendar" size={20} />
      <span className="sr-only">{t("top.period")}</span>
      <select value={current} onChange={(e) => (e.target.value === "custom" ? onCustom() : onMonth(e.target.value))}>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.text}
          </option>
        ))}
        <option value="custom">{t("top.customRange")}</option>
      </select>
      <Icon name="chevronDown" size={16} className="top-select-chevron" />
    </label>,
    topbarSlot,
  );
}

// --- balance and reserve ---------------------------------------------------------------

function BalanceCard({ data }: { data: DashboardData }) {
  const { t } = useI18n();
  const reserve = data.reserve;
  return (
    <section className="card dash-card dash-balance" aria-labelledby="dash-balance-title">
      <div className="dash-card-head">
        <CardTitle icon="wallet" id="dash-balance-title">
          {t("dash.totalBalance")}
        </CardTitle>
        <span className="dash-head-tags">
          {data.valuation.rates.map((r) => (
            <span key={`${r.base}${r.quote}`} className="chip chip-lavender">
              <WithAmount
                text={t("dash.rateChip", { mode: label(t, "dash.rateMode", r.mode) })}
                amount={<bdi dir="ltr">{`1 ${r.base} = ${r.rate} ${r.quote}`}</bdi>}
              />
            </span>
          ))}
          <span className="currency-tag">{data.display_currency}</span>
        </span>
      </div>
      <p className="dash-big">
        <Money amount={data.forecast.current_funds} currency={data.display_currency} />
      </p>
      <div className="dash-balance-meta">
        <ul className="account-lines">
          {data.balances.map((a) => (
            <li key={a.id}>
              <bdi>{a.name}</bdi> <Money amount={a.balance} currency={a.currency} />
            </li>
          ))}
        </ul>
      </div>
      {!data.forecast.complete && <p className="dash-warning">{t("dash.totalIncomplete", { currency: data.display_currency })}</p>}
      {reserve ? (
        <div className="reserve-box">
          <div className="reserve-cell">
            <Stat label={t("dashboard.floor")}>
              <Money amount={reserve.floor_amount} currency={reserve.currency} />
            </Stat>
            {reserve.floor_percent && <span className="muted">{t("dash.ofAccount", { percent: reserve.floor_percent })}</span>}
          </div>
          <div className="reserve-cell">
            <Stat label={t("dashboard.headroom")} tone={isNegative(reserve.headroom) ? "danger" : undefined}>
              <Money amount={reserve.headroom} currency={reserve.currency} />
            </Stat>
            {reserve.headroom_percent && <span className="muted">{t("dash.ofAccount", { percent: reserve.headroom_percent })}</span>}
          </div>
          <div className="reserve-note">
            <span>{t("dash.reserveAccount", { account: reserve.account_name })}</span>
            <details className="inline-details">
              <summary>{t("dash.reserveWhat")}</summary>
              <p>{t("dash.reserveFootnote")}</p>
            </details>
          </div>
        </div>
      ) : (
        <div className="reserve-box">
          <p className="muted">
            {t("dashboard.noReserve")} <AppLink route={{ page: "section", section: "budget" }}>{t("dash.setReserve")}</AppLink>
          </p>
        </div>
      )}
    </section>
  );
}

// --- assistant -------------------------------------------------------------------------

type AiView = { kind: "loading" } | { kind: "unknown" } | { kind: "status"; status: AiStatus };

function aiBadge(view: AiView): { tone: StatusTone; key: MessageKey } {
  if (view.kind === "loading") return { tone: "neutral", key: "dash.ai.status.loading" };
  if (view.kind === "unknown") return { tone: "neutral", key: "dash.ai.status.unknown" };
  switch (view.status.state) {
    case "connected":
      return { tone: "success", key: "dash.ai.status.connected" };
    case "configured_unverified":
      return { tone: "info", key: "dash.ai.status.configured_unverified" };
    case "failed":
      return { tone: "danger", key: "dash.ai.status.failed" };
    default:
      return { tone: "warning", key: "dash.ai.status.unavailable" };
  }
}

/** Reports the configured state from /api/ai/status (no model request is made to paint it). */
function AssistantCard({ bill }: { bill: Bill | null }) {
  const { t, formatDateTime } = useI18n();
  const { openAssistant } = useShell();
  const status = useLoad(() => api.aiStatus(), []);
  const view: AiView = status.data ? { kind: "status", status: status.data } : status.error ? { kind: "unknown" } : { kind: "loading" };
  const badge = aiBadge(view);
  const usable = view.kind === "status" && (view.status.state === "connected" || view.status.state === "configured_unverified");
  const steps: [MessageKey, MessageKey][] = [
    ["dash.ai.step1", "dash.ai.step1Text"],
    ["dash.ai.step2", "dash.ai.step2Text"],
    ["dash.ai.step3", "dash.ai.step3Text"],
  ];
  const note =
    view.kind === "loading"
      ? null
      : view.kind === "unknown"
        ? t("dash.ai.note.unknown")
        : view.status.state === "connected" && view.status.last_check
          ? t("dash.ai.note.connected", { date: formatDateTime(view.status.last_check.checked_at) })
          : t(`dash.ai.note.${view.status.state}` as MessageKey);
  const manual: Route = { page: "section", section: "payments" };
  return (
    <section className="card dash-card dash-assistant" aria-labelledby="dash-ai-title">
      <div className="dash-ai-head">
        <span className="dash-ai-name">
          <Icon name="sparkle" size={24} />
          {t("dash.ai.name")}
        </span>
        <StatusBadge tone={badge.tone}>
          <Icon name={badge.tone === "success" ? "checkCircle" : "alertCircle"} size={16} /> {t(badge.key)}
        </StatusBadge>
      </div>
      <h2 id="dash-ai-title" className="dash-ai-question">
        {bill?.category === "tuition" || !bill ? t("dash.ai.question") : t("dash.ai.questionBill")}
      </h2>
      {/* Decorative mascot approved by the owner; empty alt text keeps it out of the accessibility tree. */}
      <img className="dash-ai-portrait" src={assistantPortrait} alt="" width={520} height={435} decoding="async" />
      <p className="dash-ai-sub">{t("dash.ai.sub")}</p>
      <ol className="steps">
        {steps.map(([title], i) => (
          <li key={title}>
            <span className="step-number" aria-hidden="true">
              {i + 1}
            </span>
            <strong>{t(title)}</strong>
          </li>
        ))}
      </ol>
      <div className="dash-ai-actions">
        {usable ? (
          <>
            <button type="button" className="btn btn-primary" onClick={openAssistant}>
              {t("dash.ai.ask")} <Icon name="arrow" size={18} />
            </button>
            <AppLink route={manual} className="btn btn-link">
              {t("dash.ai.manual")}
            </AppLink>
          </>
        ) : (
          <AppLink route={manual} className="btn btn-primary">
            {t("dash.ai.manual")} <Icon name="arrow" size={18} />
          </AppLink>
        )}
      </div>
      <div className="dash-ai-foot">
        <details className="inline-details">
          <summary>{t("dash.ai.how")}</summary>
          {note && <p className="dash-ai-note">{note}</p>}
          <ol>
            {steps.map(([title, text]) => (
              <li key={title}>
                <strong>{t(title)}:</strong> {t(text)}
              </li>
            ))}
          </ol>
        </details>
      </div>
    </section>
  );
}

// --- budget ---------------------------------------------------------------------------

function BudgetCard({ data }: { data: DashboardData }) {
  const { t } = useI18n();
  const d = data.display_currency;
  return (
    <section className="card dash-card dash-budget" aria-labelledby="dash-budget-title">
      <div className="dash-card-head">
        <CardTitle icon="chart" id="dash-budget-title">
          {t("dash.budgetTitle")}
        </CardTitle>
        <span className="dash-total">
          {data.period.kind === "month" ? t("dash.plannedMonthly") : t("dash.plannedPeriod")}{" "}
          <strong>
            <Money amount={data.budget.planned_expenses} currency={d} />
          </strong>
        </span>
      </div>
      {data.categories.length === 0 ? (
        <p className="muted">{t("dash.noCategories")}</p>
      ) : (
        <table className="category-table">
          <caption className="sr-only">{t("dash.budgetCaption")}</caption>
          <thead className="sr-only">
            <tr>
              <th scope="col">{t("common.category")}</th>
              <th scope="col">{t("dash.shareOfPlan")}</th>
              <th scope="col">{t("dash.planned")}</th>
              <th scope="col">{t("dash.shareOfPlan")} (%)</th>
            </tr>
          </thead>
          <tbody>
            {data.categories.map((c) => (
              <tr key={c.category}>
                <th scope="row">
                  <span className="cat-name">
                    <Icon name={categoryIcon(c.category)} size={20} />
                    {label(t, "cat", c.category)}
                  </span>
                </th>
                <td className="bar-cell">
                  <span className="bar" aria-hidden="true">
                    <span className="bar-fill" style={{ width: `${c.planned_share_percent ?? "0"}%` }} />
                  </span>
                </td>
                <td className="num">
                  <Money amount={c.planned} currency={d} />
                </td>
                <td className="num bar-percent">{c.planned_share_percent === null ? "—" : `${c.planned_share_percent}%`}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div className="budget-foot">
      <dl className="budget-totals">
        <div>
          <dt>{t("dash.spent")}</dt>
          <dd>
            <Money amount={data.budget.actual_expenses} currency={d} />
          </dd>
        </div>
        <div>
          <dt>{t("dash.unallocated")}</dt>
          <dd>
            <Money amount={data.budget.planned_remainder} currency={d} />
          </dd>
        </div>
      </dl>
      <details className="inline-details">
        <summary>{t("dash.figuresAbout")}</summary>
        <p>{t("dash.barsNote")}</p>
      </details>
      </div>
    </section>
  );
}

// --- upcoming bill ------------------------------------------------------------------------

const OPEN_PROPOSAL = new Set(["ready_for_review", "approved"]);

function BillCard({ data }: { data: DashboardData }) {
  const { t, formatDate } = useI18n();
  const bill = primaryBill(data.upcoming_bills);
  const proposals = useLoad(() => api.proposals(), []);
  const proposal: Proposal | undefined = bill ? proposals.data?.proposals.find((p) => p.terms.bill.id === bill.id && OPEN_PROPOSAL.has(p.status)) : undefined;
  const others = data.upcoming_bills.length - (bill ? 1 : 0);
  const payments: Route = { page: "section", section: "payments" };
  return (
    <section className="card dash-card dash-bill" aria-labelledby="dash-bill-title">
      <div className="dash-card-head">
        <CardTitle icon="cap" id="dash-bill-title">
          {bill && bill.category !== "tuition" ? t("dash.billTitle") : t("dash.tuitionTitle")}
        </CardTitle>
        <span className="chip chip-lavender">
          <Icon name="checkCircle" size={16} /> {t("dash.simulated")}
        </span>
      </div>
      {!bill ? (
        <p className="muted">
          {t("dashboard.noBills")} <AppLink route={payments}>{t("dash.addBill")}</AppLink>
        </p>
      ) : (
        <>
          <div className="bill-head">
            <span className="bill-icon" aria-hidden="true">
              <Icon name="bank" size={26} />
            </span>
            <div className="bill-name">
              <strong>
                <bdi>{bill.description}</bdi>
              </strong>
              <span className="muted">
                <bdi>{bill.payee}</bdi>
              </span>
            </div>
            <div className="bill-amount">
              <strong>
                <Money amount={bill.amount} currency={bill.currency} />
              </strong>
              <span className="muted">
                {bill.overdue ? <StatusBadge tone="danger">{t("dashboard.overdue")}</StatusBadge> : null} {t("dash.due", { date: formatDate(bill.due_date) })}
              </span>
              {!proposal && bill.display_amount && bill.currency !== data.display_currency && (
                <span className="muted small">
                  <WithAmount text={t("dash.approx")} amount={<Money amount={bill.display_amount} currency={data.display_currency} />} />
                </span>
              )}
            </div>
          </div>
          {proposal && proposal.checks && <ProposalSummary proposal={proposal} />}
          <div className="bill-foot">
            {!proposal && proposals.data ? (
              <p className="bill-no-route">{t("dash.routeNotChosen")}</p>
            ) : proposal?.checks && !proposal.checks.reserve_ok ? (
              <p className="dash-warning">
                <Icon name="alert" size={18} />
                <span>
                  <WithAmount text={t("dash.belowReserve")} amount={<Money amount={withoutSign(proposal.checks.gap_to_floor)} currency={proposal.checks.currency} />} />
                </span>
              </p>
            ) : (
              <span />
            )}
            <AppLink route={payments} className="link-arrow">
              {proposal ? t("dash.reviewPayment") : t("dash.compareRoutes")} <Icon name="arrow" size={18} />
            </AppLink>
          </div>
          {others > 0 && <p className="muted small">{t("dash.moreBills", { count: others })}</p>}
        </>
      )}
    </section>
  );
}

/** Figures from the existing proposal's stored terms and the server's current checks. */
function ProposalSummary({ proposal }: { proposal: Proposal }) {
  const { t } = useI18n();
  const checks = proposal.checks!;
  const cur = proposal.terms.source_currency;
  return (
    <>
      <p className="muted small">
        {t("dash.proposalFor", {
          route: t("route.name", { code: proposal.terms.route.code }),
          account: proposal.terms.source_account.name,
          status: label(t, "proposalStatus", proposal.status),
        })}
      </p>
      <dl className="bill-lines">
        <div>
          <dt>{t("dash.fee")}</dt>
          <dd>
            <Money amount={proposal.terms.fee} currency={cur} />
          </dd>
        </div>
        <div>
          <dt>{t("dash.totalCost")}</dt>
          <dd>
            <Money amount={proposal.terms.total_debit} currency={cur} />
          </dd>
        </div>
        <div>
          <dt>{t("dash.balanceAfter")}</dt>
          <dd>
            <Money amount={checks.balance_after} currency={checks.currency} />
          </dd>
        </div>
      </dl>
      {checks.blocking.filter((code) => code !== "reserve_breach").map((code) => (
        <p key={code} className="muted small">
          {label(t, "pay.block", code)}
        </p>
      ))}
    </>
  );
}

// --- next actions ---------------------------------------------------------------------------

function NextActions({ data }: { data: DashboardData }) {
  const { t } = useI18n();
  const bill = primaryBill(data.upcoming_bills);
  const pendingContribution = data.funding.expected_contributions !== "0.00" || data.funding.uncertain_contributions_excluded !== "0.00";
  const actions: { icon: IconName; title: string; text: string; route: Route }[] = [
    bill
      ? { icon: "cap", title: bill.category === "tuition" ? t("dash.next.tuition") : t("dash.next.bill"), text: t("dash.next.billText"), route: { page: "section", section: "payments" } }
      : { icon: "receipt", title: t("dash.next.addBill"), text: t("dash.next.addBillText"), route: { page: "section", section: "payments" } },
    pendingContribution
      ? { icon: "plusCircle", title: t("dash.next.receive"), text: t("dash.next.receiveText"), route: { page: "section", section: "budget" } }
      : { icon: "plusCircle", title: t("dash.next.contribution"), text: t("dash.next.contributionText"), route: { page: "section", section: "budget" } },
    { icon: "target", title: t("dash.next.rate"), text: t("dash.next.rateText"), route: { page: "section", section: "currency" } },
  ];
  return (
    <section className="card dash-card dash-next" aria-labelledby="dash-next-title">
      <CardTitle icon="list" id="dash-next-title">
        {t("dash.next")}
      </CardTitle>
      <ul className="next-list">
        {actions.map((a) => (
          <li key={a.title}>
            <AppLink route={a.route} className="next-item">
              <Icon name={a.icon} size={30} />
              <span className="next-text">
                <strong>{a.title}</strong>
                <span>{a.text}</span>
              </span>
              <Icon name="arrow" size={20} className="next-arrow" />
            </AppLink>
          </li>
        ))}
      </ul>
    </section>
  );
}

// --- recent activity --------------------------------------------------------------------------

function signed(tx: Transaction): string {
  return tx.direction === "debit" ? `-${tx.amount}` : tx.amount;
}

function RecentActivity() {
  const { t, formatDate } = useI18n();
  const txs = useLoad(() => api.transactions(), []);
  const rows = txs.data?.transactions.slice(0, 5) ?? [];
  return (
    <section className="card dash-card dash-recent" aria-labelledby="dash-recent-title">
      <div className="dash-card-head">
        <CardTitle icon="list" id="dash-recent-title">
          {t("dash.recentTitle")}
        </CardTitle>
        <span className="recent-links">
          <AppLink route={{ page: "section", section: "trust" }} className="link-arrow">
            {t("dash.activityLog")}
          </AppLink>
          <AppLink route={{ page: "section", section: "budget" }} className="link-arrow">
            {t("dash.viewAll")} <Icon name="arrow" size={18} />
          </AppLink>
        </span>
      </div>
      <ErrorNotice error={txs.error} />
      {!txs.data ? (
        !txs.error && <Loading />
      ) : rows.length === 0 ? (
        <p className="muted">{t("dash.recentEmpty")}</p>
      ) : (
        <ScrollRegion label={t("dash.recentTitle")}>
          <table className="recent-table">
            <caption className="sr-only">{t("dash.recentTitle")}</caption>
            <thead>
              <tr>
                <th scope="col">{t("common.date")}</th>
                <th scope="col">{t("common.description")}</th>
                <th scope="col">{t("common.category")}</th>
                <th scope="col" className="num">
                  {t("common.amount")}
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((tx) => (
                <tr key={tx.id}>
                  <td>{formatDate(tx.occurred_on)}</td>
                  <td>
                    <bdi>{tx.description || label(t, "cat", tx.category)}</bdi>
                  </td>
                  <td>
                    <span className="chip chip-grey">
                      <Icon name={categoryIcon(tx.category)} size={16} /> {label(t, "cat", tx.category)}
                    </span>
                  </td>
                  <td className="num">
                    <Money amount={signed(tx)} currency={tx.currency} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </ScrollRegion>
      )}
    </section>
  );
}

// --- secondary detail (existing dashboard capabilities) -------------------------------------------

/** Secondary planning detail: open by default on wide screens, collapsed on phones with a
 * one-line summary so the controls stay discoverable. */
function MoreDetails({ data, children }: { data: DashboardData; children: React.ReactNode }) {
  const { t, formatDate } = useI18n();
  const [open, setOpen] = useState(() => typeof window === "undefined" || !window.matchMedia || window.matchMedia("(min-width: 901px)").matches);
  return (
    <details className="dash-more" open={open} onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary>
        <h2>{t("dash.more")}</h2>
        <span className="dash-more-summary">
          <WithAmount
            text={`${t("dashboard.lowest", { date: formatDate(data.forecast.lowest_confirmed_date) })}: {amount}`}
            amount={<Money amount={data.forecast.lowest_confirmed} currency={data.display_currency} />}
          />
        </span>
      </summary>
      {children}
    </details>
  );
}

function PlanCard({ data }: { data: DashboardData }) {
  const { t } = useI18n();
  const d = data.display_currency;
  return (
    <Card title={t("dashboard.planned")}>
      <Stat label={t("dashboard.plannedIncome")}>
        <Money amount={data.budget.planned_income} currency={d} />
      </Stat>
      <Stat label={t("dashboard.plannedExpenses")}>
        <Money amount={data.budget.planned_expenses} currency={d} />
      </Stat>
      <Stat label={t("dashboard.plannedRemainder")}>
        <Money amount={data.budget.planned_remainder} currency={d} />
      </Stat>
      <Stat label={t("dashboard.actualIncome")}>
        <Money amount={data.budget.actual_income} currency={d} />
      </Stat>
      <Stat label={t("dashboard.actualExpenses")}>
        <Money amount={data.budget.actual_expenses} currency={d} />
      </Stat>
    </Card>
  );
}

function ForecastCard({ data }: { data: DashboardData }) {
  const { t, formatDate } = useI18n();
  const d = data.display_currency;
  return (
    <Card title={t("dashboard.forecast")}>
      <p>
        <StatusBadge tone="warning">{t("label.forecast")}</StatusBadge>
      </p>
      <Stat label={t("dashboard.endConfirmed", { date: formatDate(data.forecast.to) })}>
        <Money amount={data.forecast.projected_end_confirmed} currency={d} />
      </Stat>
      <Stat label={t("dashboard.endWithExpected")}>
        <Money amount={data.forecast.projected_end_with_expected} currency={d} />
      </Stat>
      <Stat label={t("dashboard.lowest", { date: formatDate(data.forecast.lowest_confirmed_date) })}>
        <Money amount={data.forecast.lowest_confirmed} currency={d} />
      </Stat>
    </Card>
  );
}

function FundingCard({ data }: { data: DashboardData }) {
  const { t } = useI18n();
  const d = data.display_currency;
  return (
    <Card title={t("dashboard.funding")}>
      <Stat label={t("dashboard.expected")}>
        <Money amount={data.funding.expected_contributions} currency={d} />
      </Stat>
      <Stat label={t("dashboard.uncertain")}>
        <Money amount={data.funding.uncertain_contributions_excluded} currency={d} />
      </Stat>
      <Stat label={t("dashboard.gapConfirmed")} tone={data.funding.funding_gap_confirmed !== "0.00" ? "warning" : undefined}>
        <Money amount={data.funding.funding_gap_confirmed} currency={d} />
      </Stat>
      <Stat label={t("dashboard.gapWithExpected")}>
        <Money amount={data.funding.funding_gap_with_expected} currency={d} />
      </Stat>
    </Card>
  );
}

function GoalsCard({ data }: { data: DashboardData }) {
  const { t, formatMoney } = useI18n();
  return (
    <Card title={t("dashboard.goals")}>
      {data.goals.length === 0 ? (
        <p className="muted">{t("table.empty")}</p>
      ) : (
        data.goals.map((g) => (
          <div key={g.id} className="goal">
            <bdi>{g.name}</bdi>
            <progress max={100} value={Number(g.progress_percent)} aria-label={g.name} />
            <span className="muted small">
              {t("dashboard.goalProgress", {
                allocated: formatMoney(g.allocated_amount, g.currency),
                target: formatMoney(g.target_amount, g.currency),
                percent: g.progress_percent,
              })}
            </span>
          </div>
        ))
      )}
    </Card>
  );
}

