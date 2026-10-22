import { useState } from "react";
import { api, reportCsvUrl, type PeriodParams } from "../api";
import { ErrorNotice, PeriodCaption, PeriodPicker, Stat, ValuationNote, label, useLoad } from "../components/finance";
import { Card, PageHeader, DataTable, Loading, Money, Notice, StatusBadge } from "../components/ui";
import { useI18n } from "../i18n";

/** Every figure comes from GET /api/reports, which reuses the budget summary and dashboard
 * services (same data and valuation policy as the dashboard). No arithmetic in the browser. */
export function Reports() {
  const { t, formatDate, formatMoney } = useI18n();
  const [period, setPeriod] = useState<PeriodParams>({});
  const { data, error } = useLoad(() => api.report(period), [period]);

  return (
    <>
      <PageHeader icon="doc" title={t("nav.reports")} subtitle={t("page.reports.subtitle")}>
        <StatusBadge tone="accent">{t("app.demoBadge")}</StatusBadge>
      </PageHeader>
      <div className="no-print">
        <PeriodPicker value={period} onChange={setPeriod} />
      </div>
      <ErrorNotice error={error} />
      {!data ? (
        !error && <Loading />
      ) : (
        <>
          <div className="actions report-toolbar no-print" id="export" tabIndex={-1}>
            <a className="btn btn-secondary" href={reportCsvUrl(period)} download>
              {t("rep.csv")}
            </a>
            <button type="button" className="btn btn-secondary" onClick={() => window.print()}>
              {t("rep.print")}
            </button>
          </div>
          <p className="simulated-banner small">{t("rep.demoNote")}</p>
          <PeriodCaption start={data.period.start} end={data.period.end} />
          {!data.complete && <Notice tone="warning">{t("rep.incomplete", { count: data.unconverted_count })}</Notice>}
          <div className="grid-2">
            <Card title={t("rep.summary")} icon="doc" id="report-summary">
              <Stat label={t("dashboard.plannedIncome")}><Money amount={data.totals.planned_income} currency={data.display_currency} /></Stat>
              <Stat label={t("dashboard.plannedExpenses")}><Money amount={data.totals.planned_expenses} currency={data.display_currency} /></Stat>
              <Stat label={t("dashboard.plannedRemainder")}><Money amount={data.totals.planned_remainder} currency={data.display_currency} /></Stat>
              <Stat label={t("dashboard.actualIncome")}><Money amount={data.totals.actual_income} currency={data.display_currency} /></Stat>
              <Stat label={t("dashboard.actualExpenses")}><Money amount={data.totals.actual_expenses} currency={data.display_currency} /></Stat>
              <Stat label={t("rep.actualNet")}><Money amount={data.totals.actual_net} currency={data.display_currency} /></Stat>
            </Card>
            <Card title={t("rep.cashflow")} icon="calendar">
              <p><StatusBadge tone="warning">{t("label.forecast")}</StatusBadge></p>
              <Stat label={t("dashboard.endConfirmed", { date: formatDate(data.forecast.to) })}><Money amount={data.forecast.projected_end_confirmed} currency={data.display_currency} /></Stat>
              <Stat label={t("dashboard.lowest", { date: formatDate(data.forecast.lowest_confirmed_date) })}><Money amount={data.forecast.lowest_confirmed} currency={data.display_currency} /></Stat>
              <Stat label={t("dashboard.gapConfirmed")} tone={data.funding.funding_gap_confirmed !== "0.00" ? "warning" : undefined}><Money amount={data.funding.funding_gap_confirmed} currency={data.display_currency} /></Stat>
              <Stat label={t("dashboard.gapWithExpected")}><Money amount={data.funding.funding_gap_with_expected} currency={data.display_currency} /></Stat>
              {data.reserve && (
                <Stat label={t("dashboard.headroom")} tone={data.reserve.headroom.startsWith("-") ? "danger" : undefined}><Money amount={data.reserve.headroom} currency={data.reserve.currency} /></Stat>
              )}
            </Card>
          </div>
          <Card title={t("rep.categories")} icon="chart">
            <DataTable
              caption={t("rep.categoriesCaption", { currency: data.display_currency })}
              rows={data.categories}
              rowKey={(c) => c.category}
              columns={[
                { key: "c", header: t("common.category"), render: (c) => label(t, "cat", c.category) },
                { key: "p", header: t("rep.planned"), numeric: true, render: (c) => <Money amount={c.planned} currency={data.display_currency} /> },
                { key: "a", header: t("rep.actual"), numeric: true, render: (c) => <Money amount={c.actual} currency={data.display_currency} /> },
                { key: "d", header: t("rep.difference"), numeric: true, render: (c) => <Money amount={c.difference} currency={data.display_currency} /> },
              ]}
            />
          </Card>
          <div className="grid-2">
            <Card title={t("rep.fees")} icon="receipt">
              <DataTable
                caption={t("rep.fees")}
                rows={data.transfer_fees.items}
                rowKey={(f) => `${f.date}-${f.description}-${f.amount}`}
                columns={[
                  { key: "d", header: t("common.date"), render: (f) => formatDate(f.date) },
                  { key: "x", header: t("common.description"), render: (f) => <bdi>{f.description}</bdi> },
                  { key: "a", header: t("common.amount"), numeric: true, render: (f) => <Money amount={f.amount} currency={f.currency} /> },
                ]}
              />
              <Stat label={t("rep.feesTotal")}><Money amount={data.transfer_fees.total} currency={data.display_currency} /></Stat>
            </Card>
            <Card title={t("dashboard.goals")} icon="target">
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
          </div>
          <ValuationNote valuation={data.valuation} unconverted={data.unconverted_count} />
          <p className="muted small">{t("rep.csvNote")}</p>
        </>
      )}
    </>
  );
}
