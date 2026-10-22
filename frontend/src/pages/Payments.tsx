import { useState, type FormEvent } from "react";
import { ApiError, api, type Bill, type BillInput, type ExecutionResult, type Proposal, type RouteComparison } from "../api";
import { OPEN_PROPOSAL_KEY } from "../components/Chat";
import { ErrorNotice, Stat, errorMessage, label, todayIso, useLoad } from "../components/finance";
import { AmountInput, DateField } from "../components/inputs";
import { Card, DataTable, Field, Loading, Money, Notice, PageHeader, StatusBadge, type StatusTone } from "../components/ui";
import { Icon } from "../components/icons";
import { useI18n } from "../i18n";
import { checkAmount, type CurrencyCode } from "../money";

type View = { kind: "list" } | { kind: "proposal"; id: string } | { kind: "receipt"; id: string };

const STATUS_TONE: Record<string, StatusTone> = {
  draft: "neutral",
  ready_for_review: "info",
  approved: "warning",
  executed_simulated: "success",
  cancelled: "neutral",
  failed: "danger",
  expired: "neutral",
};

/** Status label for a proposal; one whose bill another payment settled says so explicitly. */
function ProposalStatusBadge({ proposal }: { proposal: Proposal }) {
  const { t } = useI18n();
  if (proposal.status_reason === "bill_settled") return <StatusBadge tone="neutral">{t("pay.billSettledStatus")}</StatusBadge>;
  return <StatusBadge tone={STATUS_TONE[proposal.status] ?? "neutral"}>{label(t, "proposalStatus", proposal.status)}</StatusBadge>;
}

function SimulatedBanner() {
  const { t } = useI18n();
  return (
    <p className="simulated-banner" role="note">
      {t("pay.simulated")}
    </p>
  );
}

export function Payments() {
  const { t } = useI18n();
  // A proposal prepared in the AI workspace opens straight into its review card.
  const [view, setView] = useState<View>(() => {
    try {
      const id = window.sessionStorage.getItem(OPEN_PROPOSAL_KEY);
      if (id) {
        window.sessionStorage.removeItem(OPEN_PROPOSAL_KEY);
        return { kind: "proposal", id };
      }
    } catch {
      /* ignore */
    }
    return { kind: "list" };
  });
  const [version, setVersion] = useState(0);
  const reload = () => setVersion((v) => v + 1);

  return (
    <>
      <PageHeader icon="card" title={t("nav.payments")} subtitle={t("page.payments.subtitle")}>
        <StatusBadge tone="accent">{t("pay.simulated")}</StatusBadge>
      </PageHeader>
      <PaymentSteps current={view.kind === "list" ? 0 : view.kind === "proposal" ? 2 : 3} />
      {view.kind !== "list" && (
        <p>
          <button type="button" className="btn btn-ghost" onClick={() => (setView({ kind: "list" }), reload())}>
            {t("pay.backToList")}
          </button>
        </p>
      )}
      {view.kind === "list" && (
        <>
          <BillsCard version={version} onChanged={reload} />
          <CompareCard version={version} onPrepared={(p) => setView({ kind: "proposal", id: p.id })} />
          <ProposalsCard version={version} onOpen={(id) => setView({ kind: "proposal", id })} />
          <HistoryCard version={version} onOpen={(id) => setView({ kind: "receipt", id })} />
        </>
      )}
      {view.kind === "proposal" && <ReviewCard id={view.id} onExecuted={(r) => setView({ kind: "receipt", id: r.execution_id })} />}
      {view.kind === "receipt" && <ReceiptCard id={view.id} />}
    </>
  );
}

/** The four stages of a simulated payment. Approval and running are separate explicit actions. */
function PaymentSteps({ current }: { current: number }) {
  const { t } = useI18n();
  const steps = [t("pay.step.bill"), t("pay.step.compare"), t("pay.step.review"), t("pay.step.run")];
  return (
    <ol className="pay-steps" aria-label={t("pay.stepsLabel")}>
      {steps.map((s, i) => (
        <li key={s} className={i === current ? "current" : undefined} aria-current={i === current ? "step" : undefined}>
          <span className="step-number" aria-hidden="true">
            {i + 1}
          </span>
          <span>{s}</span>
          {i < steps.length - 1 && <Icon name="arrow" size={16} className="pay-step-arrow" />}
        </li>
      ))}
    </ol>
  );
}

export function BillForm({ initial, onSubmit, submitLabel, title }: { initial?: Bill; onSubmit: (b: BillInput) => Promise<unknown>; submitLabel: string; title: string }) {
  const { t } = useI18n();
  const [description, setDescription] = useState(initial?.description ?? "");
  const [payee, setPayee] = useState(initial?.payee ?? "");
  const [category, setCategory] = useState<BillInput["category"]>(initial?.category ?? "tuition");
  const [amount, setAmount] = useState(initial?.amount ?? "");
  const [currency, setCurrency] = useState<CurrencyCode>((initial?.currency ?? "AUD") as CurrencyCode);
  const [due, setDue] = useState(initial?.due_date ?? todayIso());
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (checkAmount(amount, currency) !== null) return;
    setBusy(true);
    setError(null);
    try {
      await onSubmit({ description, payee, category, amount, currency, due_date: due });
    } catch (err) {
      setError(errorMessage(err, t));
    } finally {
      setBusy(false);
    }
  };
  return (
    <form className="subform" onSubmit={submit}>
      {title && <h3>{title}</h3>}
      <Field label={t("common.description")}>
        {(props) => <input {...props} type="text" required maxLength={120} value={description} onChange={(e) => setDescription(e.target.value)} />}
      </Field>
      <Field label={t("pay.payee")}>{(props) => <input {...props} type="text" required maxLength={120} value={payee} onChange={(e) => setPayee(e.target.value)} />}</Field>
      <Field label={t("common.category")}>
        {(props) => (
          <select {...props} value={category} onChange={(e) => setCategory(e.target.value as BillInput["category"])}>
            {(["tuition", "campus", "housing", "other"] as const).map((c) => (
              <option key={c} value={c}>
                {label(t, "cat", c)}
              </option>
            ))}
          </select>
        )}
      </Field>
      <AmountInput label={t("common.amount")} value={amount} currency={currency} onChange={setAmount} onCurrencyChange={setCurrency} required />
      <DateField label={t("pay.dueDate")} value={due} onChange={setDue} required />
      <button type="submit" className="btn btn-primary" disabled={busy}>
        {submitLabel}
      </button>
      {error && (
        <p className="field-error" role="alert">
          {error}
        </p>
      )}
    </form>
  );
}

function BillsCard({ version, onChanged }: { version: number; onChanged: () => void }) {
  const { t, formatDate } = useI18n();
  const bills = useLoad(() => api.bills(), [version]);
  const [editing, setEditing] = useState<Bill | null>(null);
  return (
    <Card title={t("pay.bills")} icon="receipt" id="bills">
      <ErrorNotice error={bills.error} />
      {!bills.data ? (
        <Loading />
      ) : (
        <DataTable
          caption={t("pay.bills")}
          rows={bills.data.bills}
          rowKey={(b) => b.id}
          columns={[
            { key: "d", header: t("common.description"), render: (b) => <bdi>{b.description}</bdi> },
            { key: "p", header: t("pay.payee"), render: (b) => <bdi>{b.payee}</bdi> },
            { key: "a", header: t("common.amount"), numeric: true, render: (b) => <Money amount={b.amount} currency={b.currency} /> },
            { key: "due", header: t("pay.dueDate"), render: (b) => formatDate(b.due_date) },
            { key: "s", header: t("common.status"), render: (b) => <StatusBadge tone={b.status === "settled" ? "success" : "info"}>{label(t, "billStatus", b.status)}</StatusBadge> },
            {
              key: "x",
              header: t("common.actions"),
              render: (b) =>
                b.status === "open" ? (
                  <button type="button" className="btn btn-ghost btn-small" onClick={() => setEditing(b)}>
                    {t("pay.edit")} <span className="sr-only">{b.description}</span>
                  </button>
                ) : null,
            },
          ]}
        />
      )}
      {editing ? (
        <>
          <Notice tone="warning">{t("pay.billChangedNote")}</Notice>
          <BillForm
            key={editing.id + editing.version}
            initial={editing}
            title={t("pay.editBill")}
            submitLabel={t("settings.save")}
            onSubmit={async (b) => {
              await api.updateBill(editing.id, b);
              setEditing(null);
              onChanged();
            }}
          />
        </>
      ) : (
        <details className="form-details">
          <summary>
            <Icon name="plusCircle" size={18} /> {t("pay.addBill")}
          </summary>
          <BillForm
            key={`new-${version}`}
            title=""
            submitLabel={t("common.add")}
            onSubmit={async (b) => {
              await api.createBill(b);
              onChanged();
            }}
          />
        </details>
      )}
    </Card>
  );
}

function CompareCard({ version, onPrepared }: { version: number; onPrepared: (p: Proposal) => void }) {
  const { t, formatDate, formatMoney } = useI18n();
  const bills = useLoad(() => api.bills(), [version]);
  const accounts = useLoad(() => api.accounts(), [version]);
  const open = (bills.data?.bills ?? []).filter((b) => b.status === "open");
  const [billId, setBillId] = useState("");
  const [accountId, setAccountId] = useState("");
  const [comparison, setComparison] = useState<RouteComparison | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const bill = open.find((b) => b.id === billId) ?? open[0];
  const account = (accounts.data?.accounts ?? []).find((a) => a.id === accountId) ?? accounts.data?.accounts[0];

  const compare = async (e: FormEvent) => {
    e.preventDefault();
    if (!bill || !account) return;
    setError(null);
    setComparison(null);
    try {
      setComparison(await api.routes(bill.id, account.id));
    } catch (err) {
      setError(errorMessage(err, t));
    }
  };
  const prepare = async (route: string) => {
    if (!bill || !account) return;
    setBusy(true);
    setError(null);
    try {
      onPrepared(await api.createProposal({ bill_id: bill.id, source_account_id: account.id, route }));
    } catch (err) {
      setError(errorMessage(err, t));
    } finally {
      setBusy(false);
    }
  };

  if (!bills.data || !accounts.data) return <Loading />;
  if (open.length === 0) return null;
  const c = comparison;
  return (
    <Card title={t("pay.compareTitle")} icon="globe" id="compare">
      <SimulatedBanner />
      <form className="compare-form" onSubmit={compare}>
        <Field label={t("pay.bills")}>
          {(props) => (
            <select {...props} value={bill?.id ?? ""} onChange={(e) => (setBillId(e.target.value), setComparison(null))}>
              {open.map((b) => (
                <option key={b.id} value={b.id}>
                  {`${b.description} · ${formatMoney(b.amount, b.currency)}`}
                </option>
              ))}
            </select>
          )}
        </Field>
        <Field label={t("pay.from")}>
          {(props) => (
            <select {...props} value={account?.id ?? ""} onChange={(e) => (setAccountId(e.target.value), setComparison(null))}>
              {accounts.data!.accounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {`${a.name} · ${formatMoney(a.balance, a.currency)}`}
                </option>
              ))}
            </select>
          )}
        </Field>
        <div className="field compare-submit">
          <button type="submit" className="btn btn-primary">
            {t("pay.compare")}
          </button>
        </div>
      </form>
      {/* Native selects truncate long names on phones, so the current choice is repeated in full. */}
      {bill && account && (
        <dl className="compare-summary" aria-live="polite">
          <div>
            <dt>{t("pay.bills")}</dt>
            <dd>
              <bdi>{bill.description}</bdi>
              <bdi>{bill.payee}</bdi>
              <Money amount={bill.amount} currency={bill.currency} />
              <span>{t("dash.due", { date: formatDate(bill.due_date) })}</span>
            </dd>
          </div>
          <div>
            <dt>{t("pay.from")}</dt>
            <dd>
              <bdi>{account.name}</bdi>
              <Money amount={account.balance} currency={account.currency} />
            </dd>
          </div>
        </dl>
      )}
      {error && <Notice tone="danger">{error}</Notice>}
      {c && (
        <div aria-live="polite">
          <p>
            {t("pay.objective", {
              amount: formatMoney(c.objective.recipient_amount, c.objective.recipient_currency),
              due: formatDate(c.objective.due_date),
              floor: formatMoney(c.objective.reserve_floor, c.objective.source_currency),
            })}
          </p>
          <div className="route-grid">
            {c.routes.map((r) => (
              <section key={r.route} className="route-card" aria-label={t("route.name", { code: r.route })}>
                <h3>{t("route.name", { code: r.route })}</h3>
                <p className="muted small">{label(t, "pay.assumption", r.assumption)}</p>
                <Stat label={t("pay.principal")}>
                  <Money amount={r.principal} currency={c.objective.source_currency} />
                </Stat>
                <Stat label={t("pay.fee")}>
                  <Money amount={r.fee} currency={c.objective.source_currency} />
                </Stat>
                <Stat label={t("pay.total")}>
                  <Money amount={r.total_debit} currency={c.objective.source_currency} />
                </Stat>
                <Stat label={t("pay.arrival")}>{formatDate(r.estimated_arrival)}</Stat>
                <Stat label={t("pay.gap")} tone={r.reserve_ok ? undefined : "danger"}>
                  <Money amount={r.gap_to_floor} currency={c.objective.source_currency} />
                </Stat>
                <p className="badges">
                  <StatusBadge tone={r.on_time ? "success" : "danger"}>{r.on_time ? t("pay.onTime") : t("pay.late")}</StatusBadge>
                  <StatusBadge tone={r.funds_ok ? "success" : "danger"}>{r.funds_ok ? t("pay.fundsOk") : t("pay.noFunds")}</StatusBadge>
                  <StatusBadge tone={r.reserve_ok ? "success" : "danger"}>{r.reserve_ok ? t("pay.reserveOk") : t("pay.reserveBreach")}</StatusBadge>
                </p>
                <button type="button" className="btn btn-secondary" disabled={busy} onClick={() => prepare(r.route)}>
                  {t("pay.prepare", { code: r.route })}
                </button>
              </section>
            ))}
          </div>
          <ul className="muted small">
            {c.limits.map((l) => (
              <li key={l}>{label(t, "pay.limit", l)}</li>
            ))}
            <li>{t("pay.quoteValid", { minutes: c.quote_valid_minutes })}</li>
          </ul>
          <p className="muted small" dir="ltr">
            {t("valuation.rate", { base: c.rate.base, quote: c.rate.quote, rate: c.rate.rate, mode: label(t, "rate.mode", c.rate.mode) })}
          </p>
        </div>
      )}
    </Card>
  );
}

function ProposalsCard({ version, onOpen }: { version: number; onOpen: (id: string) => void }) {
  const { t, formatDateTime } = useI18n();
  const proposals = useLoad(() => api.proposals(), [version]);
  if (!proposals.data) return <Loading />;
  return (
    <Card title={t("pay.proposals")} icon="shield" id="proposals">
      {proposals.data.proposals.length === 0 ? (
        <p className="muted">{t("pay.noProposals")}</p>
      ) : (
        <DataTable
          caption={t("pay.proposals")}
          rows={proposals.data.proposals}
          rowKey={(p) => p.id}
          columns={[
            { key: "r", header: t("table.route"), render: (p) => t("route.name", { code: p.terms.route.code }) },
            { key: "b", header: t("common.description"), render: (p) => <bdi>{p.terms.bill.description}</bdi> },
            { key: "t", header: t("pay.total"), numeric: true, render: (p) => <Money amount={p.terms.total_debit} currency={p.terms.source_currency} /> },
            { key: "s", header: t("common.status"), render: (p) => <ProposalStatusBadge proposal={p} /> },
            { key: "c", header: t("common.date"), render: (p) => formatDateTime(p.created_at) },
            {
              key: "x",
              header: t("common.actions"),
              render: (p) => (
                <button type="button" className="btn btn-ghost btn-small" onClick={() => onOpen(p.id)}>
                  {t("pay.open")}
                </button>
              ),
            },
          ]}
        />
      )}
    </Card>
  );
}

function HistoryCard({ version, onOpen }: { version: number; onOpen: (id: string) => void }) {
  const { t, formatDateTime } = useI18n();
  const executions = useLoad(() => api.executions(), [version]);
  if (!executions.data) return null;
  return (
    <Card title={t("pay.history")} icon="checkCircle" id="history">
      <DataTable
        caption={t("pay.history")}
        rows={executions.data.executions}
        rowKey={(e) => e.execution_id}
        columns={[
          { key: "n", header: t("pay.receiptNumber"), render: (e) => <span dir="ltr">{e.receipt_number}</span> },
          { key: "b", header: t("common.description"), render: (e) => <bdi>{e.bill_description}</bdi> },
          { key: "t", header: t("pay.total"), numeric: true, render: (e) => <Money amount={e.total_debit} currency={e.source_currency} /> },
          { key: "d", header: t("pay.executedAt"), render: (e) => formatDateTime(e.executed_at) },
          {
            key: "x",
            header: t("common.actions"),
            render: (e) => (
              <button type="button" className="btn btn-ghost btn-small" onClick={() => onOpen(e.execution_id)}>
                {t("pay.receipt")}
              </button>
            ),
          },
        ]}
      />
    </Card>
  );
}

/** One idempotency key per proposal version, kept for this tab so a retry after a lost
 * response reuses it and can never create a second debit. */
function executionKey(p: Proposal): string {
  const storageKey = `finzoria-exec-${p.id}-v${p.version}`;
  try {
    const existing = window.sessionStorage.getItem(storageKey);
    if (existing) return existing;
    const created = crypto.randomUUID();
    window.sessionStorage.setItem(storageKey, created);
    return created;
  } catch {
    return `${p.id}-v${p.version}`.replace(/[^A-Za-z0-9_-]/g, "-");
  }
}

function ReviewCard({ id, onExecuted }: { id: string; onExecuted: (r: ExecutionResult) => void }) {
  const { t, formatDate, formatDateTime } = useI18n();
  const [tick, setTick] = useState(0);
  const loaded = useLoad(() => api.proposal(id), [id, tick]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const p = loaded.data;

  const act = async (name: string, action: () => Promise<unknown>) => {
    setBusy(name);
    setError(null);
    try {
      await action();
    } catch (err) {
      setError(errorMessage(err, t));
    } finally {
      setBusy(null);
      setTick((n) => n + 1);
    }
  };

  const run = async (proposal: Proposal) => {
    const key = executionKey(proposal);
    setBusy("execute");
    setError(null);
    try {
      let result: ExecutionResult;
      try {
        result = await api.executeProposal(proposal.id, key);
      } catch (err) {
        if (!(err instanceof ApiError) || err.status !== 0) throw err;
        // Response lost: ask for the status first, then retry with the same key.
        setError(t("pay.lostResponse"));
        const status = await api.executionStatus(key);
        result = status.found && status.result ? status.result : await api.executeProposal(proposal.id, key);
      }
      onExecuted(result);
    } catch (err) {
      setError(errorMessage(err, t));
      setTick((n) => n + 1);
    } finally {
      setBusy(null);
    }
  };

  if (loaded.error) return <ErrorNotice error={loaded.error} />;
  if (!p) return <Loading />;
  const terms = p.terms;
  const checks = p.checks;
  const cur = terms.source_currency;
  return (
    <Card title={t("pay.review")} icon="shield" className="review-card">
      <SimulatedBanner />
      <p>
        <ProposalStatusBadge proposal={p} /> <span className="muted small">{t("pay.version", { version: p.version })}</span>
      </p>
      {p.status_reason === "bill_settled" && <Notice tone="info">{t("pay.billSettledNote")}</Notice>}
      <dl className="terms">
        <div>
          <dt>{t("pay.recipient")}</dt>
          <dd>
            <bdi>{terms.recipient}</bdi> · <bdi>{terms.bill.description}</bdi>
          </dd>
        </div>
        <div>
          <dt>{t("pay.recipientAmount")}</dt>
          <dd>
            <Money amount={terms.recipient_amount} currency={terms.recipient_currency} />
          </dd>
        </div>
        <div>
          <dt>{t("pay.senderAmount")}</dt>
          <dd>
            <Money amount={terms.principal} currency={cur} />
          </dd>
        </div>
        <div>
          <dt>{t("pay.fee")}</dt>
          <dd>
            <Money amount={terms.fee} currency={cur} />
          </dd>
        </div>
        <div>
          <dt>{t("pay.total")}</dt>
          <dd>
            <strong>
              <Money amount={terms.total_debit} currency={cur} />
            </strong>
          </dd>
        </div>
        <div>
          <dt>{t("pay.rate")}</dt>
          <dd dir="ltr">{t("valuation.rate", { base: terms.rate.base, quote: terms.rate.quote, rate: terms.rate.rate, mode: label(t, "rate.mode", terms.rate.mode) })}</dd>
        </div>
        <div>
          <dt>{t("table.route")}</dt>
          <dd>
            {t("route.name", { code: terms.route.code })} · {label(t, "pay.assumption", terms.route.assumption)}
          </dd>
        </div>
        <div>
          <dt>{t("pay.arrival")}</dt>
          <dd>
            {formatDate(terms.estimated_arrival)} ({t("pay.dueDate")}: {formatDate(terms.bill.due_date)}){" "}
            <StatusBadge tone={terms.on_time ? "success" : "danger"}>{terms.on_time ? t("pay.onTime") : t("pay.late")}</StatusBadge>
          </dd>
        </div>
        <div>
          <dt>{t("pay.expiresAt")}</dt>
          <dd>{formatDateTime(terms.quote.expires_at)}</dd>
        </div>
      </dl>
      {checks && (
        <>
          <h3>{t("pay.reserveImpact")}</h3>
          <div className="stat-row">
            <Stat label={t("pay.balanceNow")}>
              <Money amount={checks.balance_now} currency={cur} />
            </Stat>
            <Stat label={t("pay.balanceAfter")}>
              <Money amount={checks.balance_after} currency={cur} />
            </Stat>
            <Stat label={t("dashboard.floor")}>
              <Money amount={checks.reserve_floor} currency={cur} />
            </Stat>
            <Stat label={t("pay.gap")} tone={checks.reserve_ok ? "success" : "danger"}>
              <Money amount={checks.gap_to_floor} currency={cur} />
            </Stat>
          </div>
          {checks.blocking.length > 0 && (
            <Notice tone="warning">
              <p>{t("pay.blocked")}</p>
              <ul>
                {checks.blocking.map((b) => (
                  <li key={b}>{label(t, "pay.block", b)}</li>
                ))}
              </ul>
            </Notice>
          )}
        </>
      )}
      {error && <Notice tone="danger">{error}</Notice>}
      <div className="actions review-actions">
        {p.status === "ready_for_review" && (
          <>
            <p className="muted small full">{t("pay.approveNote")}</p>
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy !== null || (checks?.blocking.length ?? 1) > 0}
              onClick={() => act("approve", () => api.approveProposal(p))}
            >
              {t("pay.approve", { version: p.version })}
            </button>
          </>
        )}
        {p.status === "approved" && (
          <button type="button" className="btn btn-primary" disabled={busy !== null} onClick={() => run(p)}>
            {busy === "execute" ? t("pay.executing") : t("pay.execute")}
          </button>
        )}
        {["ready_for_review", "approved", "expired"].includes(p.status) && (
          <button type="button" className="btn btn-secondary" disabled={busy !== null} onClick={() => act("refresh", () => api.refreshProposal(p.id))}>
            {t("pay.refresh")}
          </button>
        )}
        {["draft", "ready_for_review", "approved"].includes(p.status) && (
          <button type="button" className="btn btn-ghost" disabled={busy !== null} onClick={() => act("cancel", () => api.cancelProposal(p.id))}>
            {t("pay.cancelProposal")}
          </button>
        )}
        {p.execution && (
          <button type="button" className="btn btn-secondary" onClick={() => onExecuted(p.execution!)}>
            {t("pay.receipt")}
          </button>
        )}
      </div>
    </Card>
  );
}

function ReceiptCard({ id }: { id: string }) {
  const { t, formatDate, formatDateTime, formatMoney } = useI18n();
  const [tick, setTick] = useState(0);
  const loaded = useLoad(() => api.execution(id), [id, tick]);
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const r = loaded.data;
  if (loaded.error) return <ErrorNotice error={loaded.error} />;
  if (!r) return <Loading />;
  const cur = r.source_currency;
  return (
    <Card title={t("pay.receipt")} icon="receipt" className="receipt-card">
      <div className="receipt">
        <SimulatedBanner />
        <p className="muted small">{t("pay.receiptNote")}</p>
        <dl className="terms">
          <div>
            <dt>{t("pay.receiptNumber")}</dt>
            <dd dir="ltr">{r.receipt_number}</dd>
          </div>
          <div>
            <dt>{t("pay.executedAt")}</dt>
            <dd>{formatDateTime(r.executed_at)}</dd>
          </div>
          <div>
            <dt>{t("pay.recipient")}</dt>
            <dd>
              <bdi>{r.recipient}</bdi> · <bdi>{r.bill_description}</bdi>
            </dd>
          </div>
          <div>
            <dt>{t("pay.recipientAmount")}</dt>
            <dd>
              <Money amount={r.recipient_amount} currency={r.recipient_currency} />
            </dd>
          </div>
          <div>
            <dt>{t("pay.senderAmount")}</dt>
            <dd>
              <Money amount={r.principal} currency={cur} />
            </dd>
          </div>
          <div>
            <dt>{t("pay.fee")}</dt>
            <dd>
              <Money amount={r.fee} currency={cur} />
            </dd>
          </div>
          <div>
            <dt>{t("pay.total")}</dt>
            <dd>
              <Money amount={r.total_debit} currency={cur} />
            </dd>
          </div>
          <div>
            <dt>{t("pay.rate")}</dt>
            <dd dir="ltr">{t("valuation.rate", { base: r.rate.base, quote: r.rate.quote, rate: r.rate.rate, mode: label(t, "rate.mode", r.rate.mode) })}</dd>
          </div>
          <div>
            <dt>{t("table.route")}</dt>
            <dd>{t("route.name", { code: r.route })}</dd>
          </div>
          <div>
            <dt>{t("pay.arrival")}</dt>
            <dd>{formatDate(r.estimated_arrival)}</dd>
          </div>
          <div>
            <dt>{t("pay.balanceAfter")}</dt>
            <dd>
              <bdi>{r.source_account_name}</bdi>: <Money amount={r.balance_after} currency={cur} />
            </dd>
          </div>
        </dl>
      </div>
      <p className="no-print">
        <button type="button" className="btn btn-secondary" onClick={() => window.print()}>
          {t("pay.print")}
        </button>
      </p>
      <section className="no-print">
        <h3>{t("pay.refunds")}</h3>
        <p className="muted small">{t("pay.refundNote")}</p>
        {(r.refunds ?? []).map((f) => (
          <p key={f.id} className="refund-draft">
            {t("pay.refundDraft", { amount: formatMoney(f.amount, f.currency), receipt: r.receipt_number, reason: f.reason })}
          </p>
        ))}
        <form
          className="subform"
          onSubmit={async (e) => {
            e.preventDefault();
            if (checkAmount(amount, r.recipient_currency as CurrencyCode) !== null) return;
            setError(null);
            try {
              await api.recordRefund(r.execution_id, { amount, reason });
              setAmount("");
              setReason("");
              setTick((n) => n + 1);
            } catch (err) {
              setError(errorMessage(err, t));
            }
          }}
        >
          <h3>{t("pay.addRefund")}</h3>
          <AmountInput label={t("common.amount")} value={amount} currency={r.recipient_currency as CurrencyCode} onChange={setAmount} required />
          <Field label={t("pay.refundReason")}>{(props) => <input {...props} type="text" required maxLength={200} value={reason} onChange={(e) => setReason(e.target.value)} />}</Field>
          <button type="submit" className="btn btn-primary">
            {t("common.add")}
          </button>
          {error && (
            <p className="field-error" role="alert">
              {error}
            </p>
          )}
        </form>
      </section>
    </Card>
  );
}
