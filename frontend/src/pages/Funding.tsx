import { useState, type FormEvent } from "react";
import { api, type ApplicationStatus, type FundingApplication, type WorkIncomeInput, type WorkIncomeResult } from "../api";
import { ErrorNotice, Stat, errorMessage, label, useLoad } from "../components/finance";
import { AmountInput, DateField } from "../components/inputs";
import { Card, PageHeader, DataTable, Field, FormError, Loading, Money, Notice, StatusBadge } from "../components/ui";
import { useI18n } from "../i18n";
import type { CurrencyCode } from "../money";
import { navigate } from "../router";

const STATUSES: ApplicationStatus[] = ["planning", "applied", "awarded", "declined", "withdrawn"];

/** Student funding: contributions and goals (from the shared services), a work-income
 * calculator computed on the server, Australia-only checklists, official resource links and an
 * application tracker. No eligibility, credit-score, tax or visa claims. */
export function Funding() {
  const { t } = useI18n();
  const overview = useLoad(() => api.funding(), []);
  return (
    <>
      <PageHeader icon="cap" title={t("nav.funding")} subtitle={t("page.funding.subtitle")}>
        <StatusBadge tone="accent">{t("app.demoBadge")}</StatusBadge>
      </PageHeader>
      <Notice tone="info">{t("fund.coverage")}</Notice>
      <div className="grid-2">
        <ContributionsCard />
        <WorkIncomeCard />
      </div>
      <ErrorNotice error={overview.error} />
      {!overview.data ? (
        !overview.error && <Loading />
      ) : (
        <>
          <ApplicationsCard applications={overview.data.applications} onChanged={overview.reload} />
          <div className="grid-3" id="checklists" tabIndex={-1}>
            {overview.data.checklists.groups.map((g) => (
              <ChecklistCard key={g.key} groupKey={g.key} items={g.items} onChanged={overview.reload} />
            ))}
          </div>
          <Card title={t("fund.resources")} icon="book" id="resources">
            <Notice tone="warning">{t("fund.resourcesUnverified", { date: overview.data.checked.date })}</Notice>
            <ul className="resource-list">
              {overview.data.resources.map((r) => (
                <li key={r.key}>
                  <a href={r.url} target="_blank" rel="noopener noreferrer">
                    {label(t, "fund.resource", r.key)}
                  </a>{" "}
                  <span className="muted small">
                    ({label(t, "fund.kind", r.kind)}, <bdi dir="ltr">{new URL(r.url).hostname}</bdi>)
                  </span>
                </li>
              ))}
            </ul>
            <p className="muted small">{t("fund.noMatching")}</p>
          </Card>
        </>
      )}
    </>
  );
}

function ContributionsCard() {
  const { t, formatDate, formatMoney } = useI18n();
  const contributions = useLoad(() => api.contributions(), []);
  const dash = useLoad(() => api.dashboard({}), []);
  return (
    <Card title={t("fund.familyTitle")} icon="plusCircle" id="family">
      <ErrorNotice error={contributions.error ?? dash.error} />
      {contributions.data && (
        <DataTable
          caption={t("budget.contributions")}
          rows={contributions.data.contributions}
          rowKey={(c) => c.id}
          columns={[
            { key: "from", header: t("budget.contributor"), render: (c) => <bdi>{c.contributor}</bdi> },
            { key: "date", header: t("common.date"), render: (c) => formatDate(c.expected_date) },
            { key: "amount", header: t("common.amount"), numeric: true, render: (c) => <Money amount={c.amount} currency={c.currency} /> },
            { key: "status", header: t("common.status"), render: (c) => label(t, "status", c.status) },
          ]}
        />
      )}
      {dash.data && (
        <>
          <Stat label={t("dashboard.gapConfirmed")} tone={dash.data.funding.funding_gap_confirmed !== "0.00" ? "warning" : undefined}>
            <Money amount={dash.data.funding.funding_gap_confirmed} currency={dash.data.display_currency} />
          </Stat>
          <Stat label={t("dashboard.gapWithExpected")}>
            <Money amount={dash.data.funding.funding_gap_with_expected} currency={dash.data.display_currency} />
          </Stat>
          {dash.data.goals.map((g) => (
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
          ))}
        </>
      )}
      <p className="muted small">{t("fund.familyHint")}</p>
      <button type="button" className="btn btn-secondary btn-small" onClick={() => navigate({ page: "section", section: "budget" })}>
        {t("fund.openBudget")}
      </button>
    </Card>
  );
}

function WorkIncomeCard() {
  const { t } = useI18n();
  const [form, setForm] = useState<WorkIncomeInput>({
    hourly_rate: "",
    hours_per_week: "",
    weeks: 4,
    currency: "AUD",
    basis: "gross",
    deduction_percent: "0",
  });
  const [result, setResult] = useState<WorkIncomeResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const set = (patch: Partial<WorkIncomeInput>) => (setForm((f) => ({ ...f, ...patch })), setResult(null));

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      setResult(await api.workIncome(form));
    } catch (err) {
      setError(errorMessage(err, t));
    }
  };

  return (
    <Card title={t("fund.incomeTitle")} icon="coins" id="work-income">
      <form onSubmit={submit} className="subform" noValidate>
        <AmountInput label={t("fund.hourlyRate")} value={form.hourly_rate} currency={form.currency as CurrencyCode} onChange={(v) => set({ hourly_rate: v })} onCurrencyChange={(c) => set({ currency: c })} required />
        <Field label={t("fund.hoursPerWeek")}>
          {(props) => <input {...props} type="text" inputMode="decimal" required value={form.hours_per_week} onChange={(e) => set({ hours_per_week: e.target.value })} />}
        </Field>
        <Field label={t("fund.weeks")}>
          {(props) => <input {...props} type="number" min={1} max={104} required value={form.weeks} onChange={(e) => set({ weeks: Number(e.target.value) })} />}
        </Field>
        <fieldset className="inline-radio">
          <legend className="block-label">{t("fund.basis")}</legend>
          {(["gross", "net"] as const).map((b) => (
            <label key={b}>
              <input type="radio" name="basis" checked={form.basis === b} onChange={() => set({ basis: b })} />
              {t(`fund.basis.${b}`)}
            </label>
          ))}
        </fieldset>
        {form.basis === "gross" && (
          <Field label={t("fund.deductionPercent")} hint={t("fund.deductionHint")}>
            {(props) => <input {...props} type="text" inputMode="decimal" value={form.deduction_percent} onChange={(e) => set({ deduction_percent: e.target.value })} />}
          </Field>
        )}
        <FormError message={error} />
        <div className="actions">
          <button type="submit" className="btn btn-primary">
            {t("common.calculate")}
          </button>
        </div>
      </form>
      {result && (
        <div aria-live="polite">
          {result.weekly_gross && (
            <Stat label={t("fund.weeklyGross")}>
              <Money amount={result.weekly_gross} currency={result.currency} />
            </Stat>
          )}
          <Stat label={t("fund.weeklyNet")}>
            <Money amount={result.weekly_net} currency={result.currency} />
          </Stat>
          {result.total_gross && (
            <Stat label={t("fund.totalGross", { weeks: result.weeks })}>
              <Money amount={result.total_gross} currency={result.currency} />
            </Stat>
          )}
          {result.deductions_total && (
            <Stat label={t("fund.deductions", { percent: result.deduction_percent })}>
              <Money amount={result.deductions_total} currency={result.currency} />
            </Stat>
          )}
          <Stat label={t("fund.totalNet", { weeks: result.weeks })}>
            <Money amount={result.total_net} currency={result.currency} />
          </Stat>
          <ul className="muted small">
            {result.assumptions.map((a) => (
              <li key={a}>{label(t, "fund.assumption", a)}</li>
            ))}
          </ul>
        </div>
      )}
      <p className="muted small">{t("fund.incomeHint")}</p>
    </Card>
  );
}

function ChecklistCard({ groupKey, items, onChanged }: { groupKey: string; items: { key: string; done: boolean }[]; onChanged: () => void }) {
  const { t } = useI18n();
  const [error, setError] = useState<string | null>(null);
  // Shown immediately; the server's answer replaces it (or the error is shown and it reverts).
  const [local, setLocal] = useState<Record<string, boolean>>({});
  const toggle = async (key: string, done: boolean) => {
    setError(null);
    setLocal((l) => ({ ...l, [key]: done }));
    try {
      await api.setChecklist(key, done);
      onChanged();
    } catch (err) {
      setLocal((l) => ({ ...l, [key]: !done }));
      setError(errorMessage(err, t));
    }
  };
  items = items.map((i) => ({ ...i, done: local[i.key] ?? i.done }));
  const done = items.filter((i) => i.done).length;
  return (
    <Card title={label(t, "fund.checklist", groupKey)} icon="list">
      <p className="muted small">{t("fund.checklistProgress", { done, total: items.length })}</p>
      <ul className="checklist">
        {items.map((i) => (
          <li key={i.key}>
            <label>
              <input type="checkbox" checked={i.done} onChange={(e) => toggle(i.key, e.target.checked)} />
              <span>{label(t, "fund.item", i.key)}</span>
            </label>
          </li>
        ))}
      </ul>
      {groupKey === "credit_au" && <p className="muted small">{t("fund.creditNote")}</p>}
      <FormError message={error} />
    </Card>
  );
}

const EMPTY_APP = { name: "", provider: "", status: "planning" as ApplicationStatus, deadline: null as string | null, notes: "" };

function ApplicationsCard({ applications, onChanged }: { applications: FundingApplication[]; onChanged: () => void }) {
  const { t, formatDate } = useI18n();
  const [draft, setDraft] = useState(EMPTY_APP);
  const [error, setError] = useState<string | null>(null);

  const run = async (fn: () => Promise<unknown>) => {
    setError(null);
    try {
      await fn();
      onChanged();
    } catch (err) {
      setError(errorMessage(err, t));
    }
  };
  const add = (e: FormEvent) => {
    e.preventDefault();
    run(async () => {
      await api.createApplication({ ...draft, deadline: draft.deadline || null });
      setDraft(EMPTY_APP);
    });
  };
  return (
    <Card title={t("fund.applications")} icon="doc" id="applications">
      <p className="muted small">{t("fund.applicationsHint")}</p>
      <DataTable
        caption={t("fund.applications")}
        rows={applications}
        rowKey={(a) => a.id}
        columns={[
          { key: "name", header: t("fund.appName"), render: (a) => <><bdi>{a.name}</bdi>{a.provider && <div className="muted small"><bdi>{a.provider}</bdi></div>}</> },
          { key: "deadline", header: t("fund.deadline"), render: (a) => (a.deadline ? formatDate(a.deadline) : "—") },
          {
            key: "status",
            header: t("common.status"),
            render: (a) => (
              <select
                aria-label={t("fund.statusFor", { name: a.name })}
                value={a.status}
                onChange={(e) => run(() => api.updateApplication(a.id, { name: a.name, provider: a.provider, deadline: a.deadline, notes: a.notes, status: e.target.value as ApplicationStatus }))}
              >
                {STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {label(t, "fund.status", s)}
                  </option>
                ))}
              </select>
            ),
          },
          {
            key: "actions",
            header: t("common.actions"),
            render: (a) => (
              <button type="button" className="btn btn-ghost btn-small" onClick={() => run(() => api.deleteApplication(a.id))} aria-label={t("fund.removeApp", { name: a.name })}>
                {t("common.delete")}
              </button>
            ),
          },
        ]}
      />
      <form onSubmit={add} className="subform" noValidate>
        <Field label={t("fund.appName")}>
          {(props) => <input {...props} type="text" required maxLength={120} value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />}
        </Field>
        <Field label={t("fund.provider")}>
          {(props) => <input {...props} type="text" maxLength={120} value={draft.provider} onChange={(e) => setDraft({ ...draft, provider: e.target.value })} />}
        </Field>
        <DateField label={t("fund.deadline")} value={draft.deadline ?? ""} onChange={(v) => setDraft({ ...draft, deadline: v || null })} />
        <Field label={t("common.status")}>
          {(props) => (
            <select {...props} value={draft.status} onChange={(e) => setDraft({ ...draft, status: e.target.value as ApplicationStatus })}>
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {label(t, "fund.status", s)}
                </option>
              ))}
            </select>
          )}
        </Field>
        <FormError message={error} />
        <div className="actions">
          <button type="submit" className="btn btn-primary" disabled={!draft.name.trim()}>
            {t("fund.addApp")}
          </button>
        </div>
      </form>
    </Card>
  );
}
