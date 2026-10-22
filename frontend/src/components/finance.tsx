import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react";
import { ApiError, type ActivityEvent, type PeriodParams, type Valuation } from "../api";
import { useI18n, type I18n } from "../i18n";
import type { MessageKey } from "../i18n/types";
import { Notice } from "./ui";

/** Loads data and exposes a reload function; errors are kept for display. */
export function useLoad<T>(load: () => Promise<T>, deps: unknown[]): { data: T | null; error: unknown; reload: () => void } {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [tick, setTick] = useState(0);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const run = useCallback(load, deps);
  useEffect(() => {
    let cancelled = false;
    run().then(
      (d) => !cancelled && (setData(d), setError(null)),
      (e: unknown) => !cancelled && setError(e),
    );
    return () => {
      cancelled = true;
    };
  }, [run, tick]);
  return { data, error, reload: () => setTick((n) => n + 1) };
}

const ERROR_KEYS: Partial<Record<string, MessageKey>> = {
  unsupported_pair: "error.unsupportedPair",
  invalid_rate: "error.invalidRate",
  invalid_amount: "form.amountInvalid",
  validation_error: "error.validation",
  no_session: "error.session",
  future_date: "error.futureDate",
  already_recorded: "error.alreadyRecorded",
  assistant_unavailable: "error.assistantUnavailable",
  assistant_minute_limit: "error.assistantMinuteLimit",
  assistant_daily_limit: "error.assistantDailyLimit",
  assistant_quota_exhausted: "error.assistantQuotaExhausted",
  assistant_rate_limited: "error.assistantRateLimited",
  assistant_provider_error: "error.assistantProvider",
  assistant_refused: "error.assistantProvider",
  assistant_invalid_output: "error.assistantInvalidOutput",
  action_not_pending: "error.actionNotPending",
  message_too_long: "error.messageTooLong",
  currency_mismatch: "error.currencyMismatch",
  reserve_breach: "pay.block.reserve_breach",
  insufficient_funds: "pay.block.insufficient_funds",
  proposal_expired: "pay.block.expired",
  terms_changed: "pay.block.terms_changed",
  bill_settled: "pay.block.bill_settled",
};

/** Localized message for an API error, falling back to the server's English message. */
export function errorMessage(err: unknown, t: I18n["t"]): string {
  if (err instanceof ApiError) {
    if (err.status === 0) return t("error.network");
    const key = ERROR_KEYS[err.code];
    if (key) return t(key);
    if (err.status >= 500) return t("error.generic");
    return err.message;
  }
  return t("error.generic");
}

export function ErrorNotice({ error }: { error: unknown }) {
  const { t } = useI18n();
  if (!error) return null;
  return <Notice tone="danger">{errorMessage(error, t)}</Notice>;
}

export function label(t: I18n["t"], prefix: string, value: string): string {
  const key = `${prefix}.${value}` as MessageKey;
  const text = t(key);
  return text === key ? value : text;
}

export function eventText(t: I18n["t"], e: ActivityEvent): string {
  const key = `event.${e.event_type}` as MessageKey;
  const text = t(key);
  return text === key ? t("event.unknown") : text;
}

function currentMonth(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

/** Month or custom date range. Calls onChange only when the user applies a valid choice. */
export function PeriodPicker({ value, onChange }: { value: PeriodParams; onChange: (p: PeriodParams) => void }) {
  const { t } = useI18n();
  const [mode, setMode] = useState<"month" | "custom">(value.start ? "custom" : "month");
  const [month, setMonth] = useState(value.month ?? currentMonth());
  const [start, setStart] = useState(value.start ?? "");
  const [end, setEnd] = useState(value.end ?? "");
  const submit = (e: FormEvent) => {
    e.preventDefault();
    onChange(mode === "month" ? { month } : { start, end });
  };
  return (
    <form className="period-picker" onSubmit={submit} aria-label={t("period.label")}>
      <fieldset>
        <legend>{t("period.label")}</legend>
        <label className="inline">
          <input type="radio" name="period-mode" checked={mode === "month"} onChange={() => setMode("month")} /> {t("period.month")}
        </label>
        <label className="inline">
          <input type="radio" name="period-mode" checked={mode === "custom"} onChange={() => setMode("custom")} /> {t("period.custom")}
        </label>
      </fieldset>
      {mode === "month" ? (
        <label className="stacked">
          {t("period.month")}
          <input type="month" value={month} required onChange={(e) => setMonth(e.target.value)} />
        </label>
      ) : (
        <>
          <label className="stacked">
            {t("period.start")}
            <input type="date" value={start} required onChange={(e) => setStart(e.target.value)} />
          </label>
          <label className="stacked">
            {t("period.end")}
            <input type="date" value={end} required min={start || undefined} onChange={(e) => setEnd(e.target.value)} />
          </label>
        </>
      )}
      <button type="submit" className="btn btn-secondary">
        {t("period.apply")}
      </button>
    </form>
  );
}

export function PeriodCaption({ start, end }: { start: string; end: string }) {
  const { t, formatDate } = useI18n();
  return <p className="muted">{t("period.showing", { start: formatDate(start), end: formatDate(end) })}</p>;
}

export function ValuationNote({ valuation, unconverted }: { valuation: Valuation; unconverted: number }) {
  const { t } = useI18n();
  return (
    <>
      <p className="muted small">
        {t("valuation.note", { currency: valuation.display_currency })}{" "}
        {valuation.rates.map((r) => (
          <span key={`${r.base}${r.quote}`} className="rate-chip" dir="ltr">
            {t("valuation.rate", { base: r.base, quote: r.quote, rate: r.rate, mode: label(t, "rate.mode", r.mode) })}
            {r.derived ? ` · ${t("rate.derived")}` : ""}
          </span>
        ))}
      </p>
      {unconverted > 0 && (
        <Notice tone="warning">
          {t("valuation.missing", { count: unconverted, currency: valuation.display_currency, pairs: valuation.missing_pairs.join(", ") })}
        </Notice>
      )}
    </>
  );
}

/** Label/value pair for stat tiles; values are text so screen readers read them in order. */
export function Stat({ label: text, children, tone }: { label: string; children: ReactNode; tone?: "warning" | "danger" | "success" }) {
  return (
    <div className={`stat${tone ? ` stat-${tone}` : ""}`}>
      <span className="stat-label">{text}</span>
      <span className="stat-value">{children}</span>
    </div>
  );
}

export function todayIso(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}
