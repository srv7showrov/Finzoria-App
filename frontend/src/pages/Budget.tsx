import { useState, type FormEvent, type ReactNode } from "react";
import { api, type Account, type BudgetEntry, type Contribution, type Goal, type PeriodParams, type Reserve, type ScenarioResult, type Transaction } from "../api";
import { ErrorNotice, PeriodCaption, PeriodPicker, Stat, ValuationNote, errorMessage, label, todayIso, useLoad } from "../components/finance";
import { AmountInput, DateField } from "../components/inputs";
import { Card, DataTable, PageHeader, Tabs, Field, Loading, Money, Notice, StatusBadge } from "../components/ui";
import { useI18n } from "../i18n";
import { checkAmount, type CurrencyCode } from "../money";

const EXPENSE_CATEGORIES = ["rent", "food", "transport", "phone", "books", "utilities", "health", "other"] as const;

/** Submit wrapper: shows a localized error, disables while saving, reloads on success. */
function useSubmit(onDone: () => void) {
  const { t } = useI18n();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submit = async (action: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await action();
      onDone();
    } catch (err) {
      setError(errorMessage(err, t));
    } finally {
      setBusy(false);
    }
  };
  return { busy, error, submit };
}

function FormBox({
  title,
  onSubmit,
  busy,
  error,
  children,
  submitLabel,
  note,
}: {
  title: string;
  onSubmit: () => void;
  busy: boolean;
  error: string | null;
  children: ReactNode;
  submitLabel: string;
  note?: string;
}) {
  return (
    <form
      className="subform"
      onSubmit={(e: FormEvent) => {
        e.preventDefault();
        onSubmit();
      }}
    >
      <h3>{title}</h3>
      {note && <p className="muted small">{note}</p>}
      {children}
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

function SelectField({ label: text, value, onChange, options, hint }: { label: string; value: string; onChange: (v: string) => void; options: { value: string; label: string }[]; hint?: string }) {
  return (
    <Field label={text} hint={hint}>
      {(props) => (
        <select {...props} value={value} onChange={(e) => onChange(e.target.value)}>
          {options.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      )}
    </Field>
  );
}

function TextField({ label: text, value, onChange, required, maxLength = 120 }: { label: string; value: string; onChange: (v: string) => void; required?: boolean; maxLength?: number }) {
  return (
    <Field label={text}>
      {(props) => <input {...props} type="text" value={value} required={required} maxLength={maxLength} onChange={(e) => onChange(e.target.value)} />}
    </Field>
  );
}

export function Budget() {
  const { t, formatDate } = useI18n();
  const [period, setPeriod] = useState<PeriodParams>({});
  const [version, setVersion] = useState(0);
  const reload = () => setVersion((v) => v + 1);
  const summary = useLoad(() => api.summary(period), [period, version]);
  const forecast = useLoad(() => api.cashflow(period), [period, version]);
  const entries = useLoad(() => api.entries(), [version]);
  const transactions = useLoad(() => api.transactions(), [version]);
  const contributions = useLoad(() => api.contributions(), [version]);
  const goals = useLoad(() => api.goals(), [version]);
  const reserve = useLoad(() => api.reserve(), [version]);
  const accounts = useLoad(() => api.accounts(), [version]);
  const s = summary.data;
  const f = forecast.data;
  const [recording, setRecording] = useState<string | null>(null);
  const [recordError, setRecordError] = useState<string | null>(null);
  // One explicit click links this occurrence to a new actual transaction dated today
  // (or the occurrence date if that is earlier). The server rejects a second submission.
  const recordItem = async (entryId: string, occurrenceDate: string, accountId: string, occurredOn: string) => {
    setRecording(entryId + occurrenceDate);
    setRecordError(null);
    try {
      await api.recordOccurrence(entryId, { occurrence_date: occurrenceDate, account_id: accountId, occurred_on: occurredOn });
    } catch (err) {
      setRecordError(errorMessage(err, t));
    } finally {
      setRecording(null);
      reload();
    }
  };

  return (
    <>
      <PageHeader icon="chart" title={t("nav.budget")} subtitle={t("page.budget.subtitle")} />
      <PeriodPicker value={period} onChange={setPeriod} />
      <ErrorNotice error={summary.error} />
      <Tabs
        label={t("budget.tabs")}
        items={[
          {
            id: "overview",
            label: t("budget.tab.overview"),
            icon: "chart",
            content: (
              <>
                <Card title={t("budget.summary")} icon="chart" id="summary">
                  {!s ? (
                    <Loading />
                  ) : (
                    <>
                      <PeriodCaption start={s.period.start} end={s.period.end} />
                      <div className="stat-row">
                        <Stat label={t("dashboard.plannedIncome")}>
                          <Money amount={s.planned_income} currency={s.display_currency} />
                        </Stat>
                        <Stat label={t("dashboard.plannedExpenses")}>
                          <Money amount={s.planned_expenses} currency={s.display_currency} />
                        </Stat>
                        <Stat label={t("dashboard.plannedRemainder")}>
                          <Money amount={s.planned_remainder} currency={s.display_currency} />
                        </Stat>
                        <Stat label={t("dashboard.actualIncome")}>
                          <Money amount={s.actual_income} currency={s.display_currency} />
                        </Stat>
                        <Stat label={t("dashboard.actualExpenses")}>
                          <Money amount={s.actual_expenses} currency={s.display_currency} />
                        </Stat>
                      </div>
                      <h3>{t("budget.categories")}</h3>
                      <DataTable
                        caption={t("budget.categories")}
                        rows={s.categories}
                        rowKey={(c) => c.category}
                        columns={[
                          { key: "c", header: t("common.category"), render: (c) => label(t, "cat", c.category) },
                          { key: "p", header: t("table.planned"), numeric: true, render: (c) => <Money amount={c.planned} currency={s.display_currency} /> },
                          { key: "a", header: t("table.actual"), numeric: true, render: (c) => <Money amount={c.actual} currency={s.display_currency} /> },
                          { key: "d", header: t("table.difference"), numeric: true, render: (c) => <Money amount={c.difference} currency={s.display_currency} /> },
                        ]}
                      />
                      <ValuationNote valuation={s.valuation} unconverted={s.unconverted_count} />
                    </>
                  )}
                </Card>


                <Card title={t("budget.forecast")} icon="calendar" id="forecast">
                  <p>
                    <StatusBadge tone="warning">{t("label.forecast")}</StatusBadge>
                  </p>
                  {!f ? (
                    <Loading />
                  ) : f.events.length === 0 ? (
                    <p className="muted">{t("forecast.noEvents")}</p>
                  ) : (
                    <>
                      <p className="muted">
                        {t("dashboard.currentFunds")}: <Money amount={f.current_funds} currency={f.display_currency} />
                      </p>
                      <DataTable
                        caption={t("budget.forecast")}
                        rows={f.events}
                        rowKey={(e) => e.date + e.kind + e.label + e.amount}
                        columns={[
                          { key: "date", header: t("common.date"), render: (e) => formatDate(e.date) },
                          { key: "kind", header: t("common.kind"), render: (e) => label(t, "forecast.kind", e.kind) },
                          { key: "label", header: t("common.description"), render: (e) => <bdi>{e.label}</bdi> },
                          { key: "amount", header: t("common.amount"), numeric: true, render: (e) => <Money amount={e.amount} currency={f.display_currency} /> },
                          { key: "bal", header: t("table.balanceConfirmed"), numeric: true, render: (e) => <Money amount={e.balance_confirmed} currency={f.display_currency} /> },
                          { key: "exp", header: t("table.balanceWithExpected"), numeric: true, render: (e) => <Money amount={e.balance_with_expected} currency={f.display_currency} /> },
                        ]}
                      />
                    </>
                  )}
                </Card>


              </>
            ),
          },
          {
            id: "plan",
            label: t("budget.tab.plan"),
            icon: "list",
            content: (
              <>
                <Card title={t("budget.plannedItems")} icon="checkCircle" id="planned-items">
                  {!s ? (
                    <Loading />
                  ) : (
                    <>
                      <p className="muted small">{t("budget.linkNote")}</p>
                      {recordError && <Notice tone="danger">{recordError}</Notice>}
                      <DataTable
                        caption={t("budget.plannedItems")}
                        rows={s.planned_items}
                        rowKey={(i) => i.entry_id + i.date}
                        columns={[
                          { key: "date", header: t("common.date"), render: (i) => formatDate(i.date) },
                          { key: "kind", header: t("common.kind"), render: (i) => label(t, "kind", i.kind) },
                          { key: "cat", header: t("common.category"), render: (i) => label(t, "cat", i.category) },
                          { key: "desc", header: t("common.description"), render: (i) => <bdi>{i.description}</bdi> },
                          { key: "orig", header: t("common.amount"), numeric: true, render: (i) => <Money amount={i.amount} currency={i.currency} /> },
                          {
                            key: "disp",
                            header: s.display_currency,
                            numeric: true,
                            render: (i) => (i.display_amount === null ? <StatusBadge tone="warning">—</StatusBadge> : <Money amount={i.display_amount} currency={s.display_currency} />),
                          },
                          {
                            key: "rec",
                            header: t("common.status"),
                            render: (i) => {
                              if (i.fulfilled) return <StatusBadge tone="success">{t("budget.recorded")}</StatusBadge>;
                              const account = (accounts.data?.accounts ?? []).find((a) => a.currency === i.currency);
                              if (!account) return null;
                              const today = todayIso();
                              return (
                                <button
                                  type="button"
                                  className="btn btn-ghost btn-small"
                                  disabled={recording !== null}
                                  onClick={() => recordItem(i.entry_id, i.date, account.id, i.date < today ? i.date : today)}
                                >
                                  {i.kind === "income" ? t("budget.recordReceived") : t("budget.recordPaid")}
                                  <span className="sr-only"> {i.description || label(t, "cat", i.category)} {formatDate(i.date)}</span>
                                </button>
                              );
                            },
                          },
                        ]}
                      />
                    </>
                  )}
                </Card>

                <div className="grid-2">
                  <EntriesCard entries={entries.data?.entries ?? null} onChanged={reload} />
                  <TransactionsCard accounts={accounts.data?.accounts ?? []} transactions={transactions.data?.transactions ?? null} onChanged={reload} />
                </div>
              </>
            ),
          },
          {
            id: "money",
            label: t("budget.tab.money"),
            icon: "plusCircle",
            content: (
              <>
                <ContributionsCard accounts={accounts.data?.accounts ?? []} contributions={contributions.data?.contributions ?? null} onChanged={reload} />
                <div className="grid-2">
                  <ReserveCard accounts={accounts.data?.accounts ?? []} reserve={reserve.data?.reserve ?? null} onChanged={reload} />
                  <GoalsCard goals={goals.data?.goals ?? null} onChanged={reload} />
                </div>
              </>
            ),
          },
          {
            id: "scenarios",
            label: t("budget.tab.scenarios"),
            icon: "bolt",
            content: <ScenarioCard period={period} entries={entries.data?.entries ?? []} contributions={contributions.data?.contributions ?? []} />,
          },
        ]}
      />
    </>
  );
}

function EntriesCard({ entries, onChanged }: { entries: BudgetEntry[] | null; onChanged: () => void }) {
  const { t, formatDate } = useI18n();
  const { busy, error, submit } = useSubmit(onChanged);
  const [kind, setKind] = useState<"income" | "expense">("expense");
  const [category, setCategory] = useState<string>("food");
  const [description, setDescription] = useState("");
  const [amount, setAmount] = useState("");
  const [currency, setCurrency] = useState<CurrencyCode>("BDT");
  const [start, setStart] = useState(todayIso());
  const [end, setEnd] = useState("");
  const [recurrence, setRecurrence] = useState<"none" | "monthly">("monthly");
  return (
    <Card title={t("budget.entries")} icon="list" id="entries">
      {!entries ? (
        <Loading />
      ) : (
        <DataTable
          caption={t("budget.entries")}
          rows={entries}
          rowKey={(e) => e.id}
          columns={[
            { key: "k", header: t("common.kind"), render: (e) => label(t, "kind", e.kind) },
            { key: "c", header: t("common.category"), render: (e) => label(t, "cat", e.category) },
            { key: "a", header: t("common.amount"), numeric: true, render: (e) => <Money amount={e.amount} currency={e.currency} /> },
            { key: "r", header: t("budget.recurrence"), render: (e) => `${label(t, "recurrence", e.recurrence)} · ${formatDate(e.start_date)}` },
            {
              key: "x",
              header: t("common.actions"),
              render: (e) => (
                <button type="button" className="btn btn-ghost btn-small" disabled={busy} onClick={() => submit(() => api.deleteEntry(e.id))}>
                  {t("common.delete")} <span className="sr-only">{e.description || e.category}</span>
                </button>
              ),
            },
          ]}
        />
      )}
      <FormBox
        title={t("budget.addEntry")}
        busy={busy}
        error={error}
        submitLabel={t("common.add")}
        onSubmit={() =>
          checkAmount(amount, currency) === null &&
          submit(() =>
            api.createEntry({ kind, category: kind === "income" ? "income" : category, description, amount, currency, start_date: start, recurrence, end_date: end || null }),
          )
        }
      >
        <SelectField
          label={t("common.kind")}
          value={kind}
          onChange={(v) => setKind(v as "income" | "expense")}
          options={[
            { value: "expense", label: t("kind.expense") },
            { value: "income", label: t("kind.income") },
          ]}
        />
        {kind === "expense" && (
          <SelectField label={t("common.category")} value={category} onChange={setCategory} options={EXPENSE_CATEGORIES.map((c) => ({ value: c, label: label(t, "cat", c) }))} />
        )}
        <TextField label={t("common.description")} value={description} onChange={setDescription} />
        <AmountInput label={t("common.amount")} value={amount} currency={currency} onChange={setAmount} onCurrencyChange={setCurrency} required />
        <DateField label={t("budget.startDate")} value={start} onChange={setStart} required />
        <SelectField
          label={t("budget.recurrence")}
          value={recurrence}
          onChange={(v) => setRecurrence(v as "none" | "monthly")}
          hint={t("recurrence.rule")}
          options={[
            { value: "monthly", label: t("recurrence.monthly") },
            { value: "none", label: t("recurrence.none") },
          ]}
        />
        {recurrence === "monthly" && <DateField label={t("budget.endDate")} value={end} onChange={setEnd} />}
      </FormBox>
    </Card>
  );
}

function TransactionsCard({ accounts, transactions, onChanged }: { accounts: Account[]; transactions: Transaction[] | null; onChanged: () => void }) {
  const { t, formatDate } = useI18n();
  const { busy, error, submit } = useSubmit(onChanged);
  const [accountId, setAccountId] = useState("");
  const [kind, setKind] = useState<"income" | "expense">("expense");
  const [category, setCategory] = useState<string>("food");
  const [description, setDescription] = useState("");
  const [amount, setAmount] = useState("");
  const [date, setDate] = useState(todayIso());
  const account = accounts.find((a) => a.id === accountId) ?? accounts[0];
  const currency = (account?.currency ?? "BDT") as CurrencyCode;
  return (
    <Card title={t("budget.actuals")} icon="receipt" id="transactions">
      {!transactions ? (
        <Loading />
      ) : (
        <DataTable
          caption={t("budget.actuals")}
          rows={transactions.slice(0, 15)}
          rowKey={(x) => x.id}
          columns={[
            { key: "d", header: t("common.date"), render: (x) => formatDate(x.occurred_on) },
            { key: "k", header: t("common.kind"), render: (x) => label(t, "kind", x.kind) },
            { key: "c", header: t("common.category"), render: (x) => label(t, "cat", x.category) },
            { key: "a", header: t("common.amount"), numeric: true, render: (x) => <Money amount={(x.direction === "debit" ? "-" : "") + x.amount} currency={x.currency} /> },
          ]}
        />
      )}
      <FormBox
        title={t("budget.addTransaction")}
        note={t("budget.linkNote")}
        busy={busy}
        error={error}
        submitLabel={t("common.add")}
        onSubmit={() =>
          account &&
          checkAmount(amount, currency) === null &&
          date <= todayIso() &&
          submit(() => api.createTransaction({ account_id: account.id, kind, category: kind === "income" ? "income" : category, description, amount, occurred_on: date }))
        }
      >
        <SelectField label={t("common.account")} value={account?.id ?? ""} onChange={setAccountId} options={accounts.map((a) => ({ value: a.id, label: a.name }))} />
        <SelectField
          label={t("common.kind")}
          value={kind}
          onChange={(v) => setKind(v as "income" | "expense")}
          options={[
            { value: "expense", label: t("kind.expense") },
            { value: "income", label: t("kind.income") },
          ]}
        />
        {kind === "expense" && (
          <SelectField label={t("common.category")} value={category} onChange={setCategory} options={EXPENSE_CATEGORIES.map((c) => ({ value: c, label: label(t, "cat", c) }))} />
        )}
        <TextField label={t("common.description")} value={description} onChange={setDescription} />
        <AmountInput label={t("common.amount")} value={amount} currency={currency} onChange={setAmount} required />
        <DateField label={t("common.date")} value={date} onChange={setDate} required max={todayIso()} hint={t("budget.actualDateHint")} />
      </FormBox>
    </Card>
  );
}

function ContributionsCard({ accounts, contributions, onChanged }: { accounts: Account[]; contributions: Contribution[] | null; onChanged: () => void }) {
  const { t, formatDate } = useI18n();
  const { busy, error, submit } = useSubmit(onChanged);
  const [accountId, setAccountId] = useState("");
  const [contributor, setContributor] = useState("");
  const [amount, setAmount] = useState("");
  const [date, setDate] = useState(todayIso());
  const [certainty, setCertainty] = useState<"expected" | "uncertain">("expected");
  const account = accounts.find((a) => a.id === accountId) ?? accounts[0];
  const currency = (account?.currency ?? "BDT") as CurrencyCode;
  return (
    <Card title={t("budget.contributions")} icon="plusCircle" id="contributions">
      <p className="muted small">{t("budget.receivedNote")}</p>
      {!contributions ? (
        <Loading />
      ) : (
        <DataTable
          caption={t("budget.contributions")}
          rows={contributions}
          rowKey={(c) => c.id}
          columns={[
            { key: "f", header: t("budget.contributor"), render: (c) => <bdi>{c.contributor}</bdi> },
            { key: "a", header: t("common.amount"), numeric: true, render: (c) => <Money amount={c.amount} currency={c.currency} /> },
            { key: "d", header: t("budget.expectedDate"), render: (c) => formatDate(c.received_on ?? c.expected_date) },
            {
              key: "s",
              header: t("common.status"),
              render: (c) => (
                <StatusBadge tone={c.status === "received" ? "success" : c.status === "cancelled" ? "neutral" : "info"}>
                  {label(t, "status", c.status)}
                  {c.status === "expected" && c.certainty === "uncertain" ? ` · ${t("certainty.uncertain")}` : ""}
                </StatusBadge>
              ),
            },
            {
              key: "x",
              header: t("common.actions"),
              render: (c) =>
                c.status === "expected" ? (
                  <span className="actions">
                    <button type="button" className="btn btn-primary btn-small" disabled={busy} onClick={() => submit(() => api.receiveContribution(c.id))}>
                      {t("budget.markReceived")} <span className="sr-only">{c.contributor}</span>
                    </button>
                    <button type="button" className="btn btn-ghost btn-small" disabled={busy} onClick={() => submit(() => api.cancelContribution(c.id))}>
                      {t("common.cancel")} <span className="sr-only">{c.contributor}</span>
                    </button>
                  </span>
                ) : null,
            },
          ]}
        />
      )}
      <FormBox
        title={t("budget.addContribution")}
        busy={busy}
        error={error}
        submitLabel={t("common.add")}
        onSubmit={() =>
          account && checkAmount(amount, currency) === null && submit(() => api.createContribution({ account_id: account.id, contributor, amount, expected_date: date, certainty }))
        }
      >
        <SelectField label={t("common.account")} value={account?.id ?? ""} onChange={setAccountId} options={accounts.map((a) => ({ value: a.id, label: a.name }))} />
        <TextField label={t("budget.contributor")} value={contributor} onChange={setContributor} required maxLength={80} />
        <AmountInput label={t("common.amount")} value={amount} currency={currency} onChange={setAmount} required />
        <DateField label={t("budget.expectedDate")} value={date} onChange={setDate} required />
        <SelectField
          label={t("budget.certainty")}
          value={certainty}
          onChange={(v) => setCertainty(v as "expected" | "uncertain")}
          options={[
            { value: "expected", label: t("certainty.expected") },
            { value: "uncertain", label: t("certainty.uncertain") },
          ]}
        />
      </FormBox>
    </Card>
  );
}

function ReserveCard({ accounts, reserve, onChanged }: { accounts: Account[]; reserve: Reserve | null; onChanged: () => void }) {
  const { t } = useI18n();
  const { busy, error, submit } = useSubmit(onChanged);
  const [accountId, setAccountId] = useState("");
  const [amount, setAmount] = useState("");
  const account = accounts.find((a) => a.id === (accountId || reserve?.account_id)) ?? accounts[0];
  const currency = (account?.currency ?? "BDT") as CurrencyCode;
  return (
    <Card title={t("budget.reserve")} icon="shield" id="reserve">
      <p className="muted small">{t("budget.reserveHint")}</p>
      {reserve && (
        <div className="stat-row">
          <Stat label={t("dashboard.floor")}>
            <Money amount={reserve.floor_amount} currency={reserve.currency} />
          </Stat>
          <Stat label={t("dashboard.headroom")} tone={reserve.headroom.startsWith("-") ? "danger" : undefined}>
            <Money amount={reserve.headroom} currency={reserve.currency} />
          </Stat>
        </div>
      )}
      <FormBox
        title={t("budget.reserve")}
        busy={busy}
        error={error}
        submitLabel={t("settings.save")}
        onSubmit={() => account && checkAmount(amount, currency) === null && submit(() => api.saveReserve({ account_id: account.id, floor_amount: amount }))}
      >
        <SelectField label={t("common.account")} value={account?.id ?? ""} onChange={setAccountId} options={accounts.map((a) => ({ value: a.id, label: a.name }))} />
        <AmountInput label={t("budget.floorAmount")} value={amount} currency={currency} onChange={setAmount} required />
      </FormBox>
    </Card>
  );
}

function GoalsCard({ goals, onChanged }: { goals: Goal[] | null; onChanged: () => void }) {
  const { t } = useI18n();
  const { busy, error, submit } = useSubmit(onChanged);
  const [name, setName] = useState("");
  const [target, setTarget] = useState("");
  const [allocated, setAllocated] = useState("0");
  const [currency, setCurrency] = useState<CurrencyCode>("BDT");
  const [edits, setEdits] = useState<Record<string, string>>({});
  return (
    <Card title={t("budget.goals")} icon="target" id="goals">
      <p className="muted small">{t("budget.goalHint")}</p>
      {!goals ? (
        <Loading />
      ) : (
        <DataTable
          caption={t("budget.goals")}
          rows={goals}
          rowKey={(g) => g.id}
          columns={[
            { key: "n", header: t("budget.goalName"), render: (g) => <bdi>{g.name}</bdi> },
            { key: "t", header: t("budget.target"), numeric: true, render: (g) => <Money amount={g.target_amount} currency={g.currency} /> },
            { key: "p", header: "%", numeric: true, render: (g) => <progress max={100} value={Number(g.progress_percent)} aria-label={`${g.name} ${g.progress_percent}%`} /> },
            {
              key: "a",
              header: t("budget.allocated"),
              render: (g) => (
                <span className="actions">
                  <input
                    className="small-input"
                    aria-label={`${t("budget.allocated")} ${g.name}`}
                    inputMode="decimal"
                    value={edits[g.id] ?? g.allocated_amount}
                    onChange={(e) => setEdits({ ...edits, [g.id]: e.target.value })}
                  />
                  <button type="button" className="btn btn-ghost btn-small" disabled={busy} onClick={() => submit(() => api.updateGoal(g.id, edits[g.id] ?? g.allocated_amount))}>
                    {t("budget.update")}
                  </button>
                </span>
              ),
            },
          ]}
        />
      )}
      <FormBox
        title={t("budget.addGoal")}
        busy={busy}
        error={error}
        submitLabel={t("common.add")}
        onSubmit={() => checkAmount(target, currency) === null && submit(() => api.createGoal({ name, target_amount: target, allocated_amount: allocated || "0", currency, target_date: null }))}
      >
        <TextField label={t("budget.goalName")} value={name} onChange={setName} required maxLength={80} />
        <AmountInput label={t("budget.target")} value={target} currency={currency} onChange={setTarget} onCurrencyChange={setCurrency} required />
        <AmountInput label={t("budget.allocated")} value={allocated} currency={currency} onChange={setAllocated} />
      </FormBox>
    </Card>
  );
}

function ScenarioCard({ period, entries, contributions }: { period: PeriodParams; entries: BudgetEntry[]; contributions: Contribution[] }) {
  const { t, formatDate } = useI18n();
  const [result, setResult] = useState<ScenarioResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const expected = contributions.filter((c) => c.status === "expected");
  const expenses = entries.filter((e) => e.kind === "expense");
  const [contributionId, setContributionId] = useState("");
  const [newDate, setNewDate] = useState("");
  const [entryId, setEntryId] = useState("");
  const [newAmount, setNewAmount] = useState("");
  const run = async (body: Record<string, string>) => {
    setError(null);
    try {
      setResult(await api.scenario(period, body));
    } catch (err) {
      setError(errorMessage(err, t));
    }
  };
  const chosenContribution = contributionId || expected[0]?.id || "";
  const chosenEntry = entryId || expenses[0]?.id || "";
  return (
    <Card title={t("scenario.title")} icon="bolt" id="scenario">
      <Notice>{t("scenario.note")}</Notice>
      {expected.length > 0 && (
        <FormBox title={t("scenario.delay")} busy={false} error={null} submitLabel={t("scenario.run")} onSubmit={() => newDate && run({ type: "delay_contribution", contribution_id: chosenContribution, new_date: newDate })}>
          <SelectField
            label={t("budget.contributor")}
            value={chosenContribution}
            onChange={setContributionId}
            options={expected.map((c) => ({ value: c.id, label: `${c.contributor} · ${c.amount} ${c.currency} · ${formatDate(c.expected_date)}` }))}
          />
          <DateField label={t("scenario.newDate")} value={newDate} onChange={setNewDate} required />
        </FormBox>
      )}
      {expenses.length > 0 && (
        <FormBox title={t("scenario.change")} busy={false} error={null} submitLabel={t("scenario.run")} onSubmit={() => newAmount && run({ type: "change_expense", entry_id: chosenEntry, new_amount: newAmount })}>
          <SelectField
            label={t("common.category")}
            value={chosenEntry}
            onChange={setEntryId}
            options={expenses.map((e) => ({ value: e.id, label: `${label(t, "cat", e.category)} · ${e.amount} ${e.currency}` }))}
          />
          <AmountInput
            label={t("scenario.newAmount")}
            value={newAmount}
            currency={(expenses.find((e) => e.id === chosenEntry)?.currency ?? "BDT") as CurrencyCode}
            onChange={setNewAmount}
            required
          />
        </FormBox>
      )}
      {error && <Notice tone="danger">{error}</Notice>}
      {result && <ScenarioView result={result} />}
    </Card>
  );
}

function ScenarioView({ result }: { result: ScenarioResult }) {
  const { t, formatDate } = useI18n();
  const d = result.baseline.display_currency;
  return (
    <div className="scenario-result" aria-live="polite">
      <div className="stat-row">
        <Stat label={`${t("scenario.baseline")} · ${t("scenario.endBalance")}`}>
          <Money amount={result.baseline.projected_end_with_expected} currency={d} />
        </Stat>
        <Stat label={`${t("scenario.result")} · ${t("scenario.endBalance")}`}>
          <Money amount={result.scenario.projected_end_with_expected} currency={d} />
        </Stat>
        <Stat label={`${t("scenario.result")} · ${t("scenario.lowest")}`}>
          <Money amount={result.scenario.lowest_with_expected} currency={d} />
        </Stat>
      </div>
      {result.payment_timing && (
        <>
          <h3>{t("scenario.timing")}</h3>
          <p className="muted small">{t("scenario.assumption")}</p>
          <p className="muted small">{t("scenario.outflowAssumption")}</p>
          {result.payment_timing.map((timing) => (
            <div key={timing.bill_id + timing.case}>
              <h4>{timing.case === "baseline" ? t("scenario.baseline") : t("scenario.result")}</h4>
              <DataTable
                caption={t("scenario.timing")}
                rows={timing.routes}
                rowKey={(r) => r.route}
                columns={[
                  { key: "r", header: t("table.route"), render: (r) => t("route.name", { code: r.route }) },
                  { key: "tot", header: t("table.total"), numeric: true, render: (r) => <Money amount={r.total} currency={r.currency} /> },
                  {
                    key: "s",
                    header: t("table.canStart"),
                    render: (r) =>
                      r.status === "indeterminate" ? t("scenario.indeterminate") : r.initiation_date ? formatDate(r.initiation_date) : t("scenario.notFeasible"),
                  },
                  { key: "a", header: t("table.arrival"), render: (r) => (r.estimated_arrival ? formatDate(r.estimated_arrival) : "—") },
                  {
                    key: "o",
                    header: t("table.onTime"),
                    render: (r) =>
                      r.on_time === null ? (
                        <StatusBadge tone="neutral">—</StatusBadge>
                      ) : (
                        <StatusBadge tone={r.on_time ? "success" : "danger"}>{r.on_time ? t("common.yes") : t("common.no")}</StatusBadge>
                      ),
                  },
                ]}
              />
            </div>
          ))}
        </>
      )}
    </div>
  );
}
