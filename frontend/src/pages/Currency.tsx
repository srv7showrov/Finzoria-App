import { useState } from "react";
import { api, type Conversion, type RateScenarioResult } from "../api";
import { ErrorNotice, errorMessage, label, useLoad } from "../components/finance";
import { AmountInput, CurrencySelect } from "../components/inputs";
import { Card, PageHeader, DataTable, Field, Loading, Money, Notice, StatusBadge } from "../components/ui";
import { useI18n } from "../i18n";
import { checkAmount, type CurrencyCode } from "../money";

const RATE = /^\d{1,15}(\.\d{1,8})?$/;

export function Currency() {
  const { t, formatDateTime } = useI18n();
  const [version, setVersion] = useState(0);
  const rates = useLoad(() => api.rates(), [version]);

  return (
    <>
      <PageHeader icon="globe" title={t("nav.currency")} subtitle={t("page.currency.subtitle")} />
      <Notice tone="warning">{t("currency.provider")}</Notice>
      <div className="grid-2">
        <Converter />
        <RateScenario />
      </div>
      <Card title={t("currency.rates")} icon="coins" id="rates">
        <ErrorNotice error={rates.error} />
        {!rates.data ? (
          <Loading />
        ) : (
          <DataTable
            caption={t("currency.rates")}
            rows={rates.data.snapshots}
            rowKey={(s) => s.id}
            columns={[
              { key: "p", header: t("table.pair"), render: (s) => <span dir="ltr">{`${s.base} → ${s.quote}`}</span> },
              { key: "r", header: t("table.rate"), numeric: true, render: (s) => <span dir="ltr">{s.rate}</span> },
              { key: "m", header: t("table.mode"), render: (s) => <StatusBadge tone={s.mode === "fixture" ? "accent" : "info"}>{label(t, "rate.mode", s.mode)}</StatusBadge> },
              { key: "s", header: t("table.source"), render: (s) => <span className="small">{s.source}</span> },
              { key: "a", header: t("table.asOf"), render: (s) => formatDateTime(s.as_of) },
              { key: "c", header: t("table.current"), render: (s) => (s.current ? t("currency.current") : t("currency.earlier")) },
            ]}
          />
        )}
        <ManualRateForm onSaved={() => setVersion((v) => v + 1)} />
      </Card>
      <Card title={t("currency.targets")} icon="target" id="targets">
        <p className="muted small">{t("currency.targetHint")}</p>
        {rates.data && (
          <DataTable
            caption={t("currency.targets")}
            rows={rates.data.targets}
            rowKey={(x) => x.id}
            columns={[
              { key: "p", header: t("table.pair"), render: (x) => <span dir="ltr">{`${x.base} → ${x.quote}`}</span> },
              { key: "c", header: t("currency.direction"), render: (x) => `${label(t, "direction", x.direction)} ${x.threshold}` },
              { key: "r", header: t("table.rate"), render: (x) => <span dir="ltr">{x.current_rate?.rate ?? "—"}</span> },
              {
                key: "m",
                header: t("common.status"),
                render: (x) => (
                  <StatusBadge tone={x.met === null ? "neutral" : x.met ? "success" : "warning"}>
                    {x.met === null ? t("target.unavailable") : x.met ? t("target.met") : t("target.notMet")}
                  </StatusBadge>
                ),
              },
              {
                key: "x",
                header: t("common.actions"),
                render: (x) => (
                  <button type="button" className="btn btn-ghost btn-small" onClick={() => api.deleteTarget(x.id).then(() => setVersion((v) => v + 1))}>
                    {t("common.delete")}
                  </button>
                ),
              },
            ]}
          />
        )}
        {rates.data?.targets[0] && <p className="muted small">{t("currency.checkedAt", { time: formatDateTime(rates.data.targets[0].checked_at) })}</p>}
        <TargetForm onSaved={() => setVersion((v) => v + 1)} />
      </Card>
    </>
  );
}

function Converter() {
  const { t } = useI18n();
  const [amount, setAmount] = useState("1000");
  const [from, setFrom] = useState<CurrencyCode>("AUD");
  const [to, setTo] = useState<CurrencyCode>("BDT");
  const [result, setResult] = useState<Conversion | null>(null);
  const [error, setError] = useState<string | null>(null);
  return (
    <Card title={t("currency.converter")} icon="globe" id="converter">
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          if (checkAmount(amount, from) !== null) return;
          setError(null);
          setResult(null);
          try {
            setResult(await api.convert(amount, from, to));
          } catch (err) {
            setError(errorMessage(err, t));
          }
        }}
      >
        <AmountInput label={t("common.amount")} value={amount} currency={from} onChange={setAmount} onCurrencyChange={setFrom} required />
        <CurrencySelect label={t("currency.to")} value={to} onChange={setTo} />
        <button type="submit" className="btn btn-primary">
          {t("currency.convert")}
        </button>
      </form>
      {error && <Notice tone="danger">{error}</Notice>}
      {result && (
        <div aria-live="polite">
          <p className="big-result">
            <Money amount={result.amount} currency={result.from} /> = <Money amount={result.result} currency={result.to} />
          </p>
          <p className="muted small" dir="ltr">
            {t("valuation.rate", { base: result.rate.base, quote: result.rate.quote, rate: result.rate.rate, mode: label(t, "rate.mode", result.rate.mode) })}
            {result.rate.derived ? ` · ${t("rate.derived")}` : ""}
          </p>
        </div>
      )}
    </Card>
  );
}

function RateScenario() {
  const { t } = useI18n();
  const [amount, setAmount] = useState("1000");
  const [base, setBase] = useState<CurrencyCode>("AUD");
  const [quote, setQuote] = useState<CurrencyCode>("BDT");
  const [change, setChange] = useState("5");
  const [result, setResult] = useState<RateScenarioResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  return (
    <Card title={t("currency.scenario")} icon="chart" id="rate-scenario">
      <p className="muted small">{t("currency.scenarioNote")}</p>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setError(null);
          try {
            setResult(await api.rateScenario({ base, quote, amount, change_percent: change }));
          } catch (err) {
            setError(errorMessage(err, t));
          }
        }}
      >
        <AmountInput label={t("common.amount")} value={amount} currency={base} onChange={setAmount} onCurrencyChange={setBase} required />
        <CurrencySelect label={t("currency.to")} value={quote} onChange={setQuote} />
        <Field label={t("currency.changePercent")}>
          {(props) => <input {...props} type="text" inputMode="decimal" dir="ltr" value={change} onChange={(e) => setChange(e.target.value)} />}
        </Field>
        <button type="submit" className="btn btn-primary">
          {t("common.calculate")}
        </button>
      </form>
      {error && <Notice tone="danger">{error}</Notice>}
      {result && (
        <p aria-live="polite">
          {t("currency.scenarioResult", {
            now: `${result.current_value} ${result.quote}`,
            then: `${result.scenario_value} ${result.quote}`,
            diff: `${result.difference} ${result.quote}`,
          })}
        </p>
      )}
    </Card>
  );
}

function ManualRateForm({ onSaved }: { onSaved: () => void }) {
  const { t } = useI18n();
  const [base, setBase] = useState<CurrencyCode>("EUR");
  const [quote, setQuote] = useState<CurrencyCode>("AUD");
  const [rate, setRate] = useState("");
  const [error, setError] = useState<string | null>(null);
  const invalid = rate !== "" && (!RATE.test(rate) || /^0+(\.0+)?$/.test(rate));
  return (
    <form
      className="subform"
      onSubmit={async (e) => {
        e.preventDefault();
        if (invalid || !rate) return;
        setError(null);
        try {
          await api.addManualRate({ base, quote, rate });
          setRate("");
          onSaved();
        } catch (err) {
          setError(errorMessage(err, t));
        }
      }}
    >
      <h3>{t("currency.addManual")}</h3>
      <div className="inline-fields">
        <CurrencySelect label={t("currency.from")} value={base} onChange={setBase} />
        <CurrencySelect label={t("currency.to")} value={quote} onChange={setQuote} />
      </div>
      <Field label={t("table.rate")} hint={t("currency.rateHint")} error={invalid ? t("error.invalidRate") : null}>
        {(props) => <input {...props} type="text" inputMode="decimal" dir="ltr" required value={rate} onChange={(e) => setRate(e.target.value)} />}
      </Field>
      <button type="submit" className="btn btn-primary">
        {t("common.add")}
      </button>
      {error && (
        <p className="field-error" role="alert">
          {error}
        </p>
      )}
    </form>
  );
}

function TargetForm({ onSaved }: { onSaved: () => void }) {
  const { t } = useI18n();
  const [base, setBase] = useState<CurrencyCode>("BDT");
  const [quote, setQuote] = useState<CurrencyCode>("AUD");
  const [threshold, setThreshold] = useState("");
  const [direction, setDirection] = useState<"at_or_above" | "at_or_below">("at_or_above");
  const [error, setError] = useState<string | null>(null);
  return (
    <form
      className="subform"
      onSubmit={async (e) => {
        e.preventDefault();
        setError(null);
        try {
          await api.addTarget({ base, quote, threshold, direction });
          setThreshold("");
          onSaved();
        } catch (err) {
          setError(errorMessage(err, t));
        }
      }}
    >
      <h3>{t("currency.addTarget")}</h3>
      <div className="inline-fields">
        <CurrencySelect label={t("currency.from")} value={base} onChange={setBase} />
        <CurrencySelect label={t("currency.to")} value={quote} onChange={setQuote} />
      </div>
      <Field label={t("currency.direction")}>
        {(props) => (
          <select {...props} value={direction} onChange={(e) => setDirection(e.target.value as "at_or_above" | "at_or_below")}>
            <option value="at_or_above">{t("direction.at_or_above")}</option>
            <option value="at_or_below">{t("direction.at_or_below")}</option>
          </select>
        )}
      </Field>
      <Field label={t("currency.threshold")}>
        {(props) => <input {...props} type="text" inputMode="decimal" dir="ltr" required value={threshold} onChange={(e) => setThreshold(e.target.value)} />}
      </Field>
      <button type="submit" className="btn btn-primary">
        {t("currency.addTarget")}
      </button>
      {error && (
        <p className="field-error" role="alert">
          {error}
        </p>
      )}
    </form>
  );
}
