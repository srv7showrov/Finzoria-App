import { useMemo } from "react";
import { LOCALES, useI18n } from "../i18n";
import { CURRENCIES, checkAmount, type CurrencyCode } from "../money";
import { Field } from "./ui";

export function AmountInput({
  label,
  value,
  currency,
  onChange,
  onCurrencyChange,
  required,
}: {
  label: string;
  value: string;
  currency: CurrencyCode;
  onChange: (value: string) => void;
  onCurrencyChange?: (currency: CurrencyCode) => void;
  required?: boolean;
}) {
  const { t } = useI18n();
  // An empty field is left to the form's required check; anything typed is validated as a decimal string.
  const problem = value.trim() === "" ? null : checkAmount(value, currency);
  let error: string | null = null;
  if (problem?.kind === "invalid") error = t("form.amountInvalid");
  if (problem?.kind === "precision") error = t("form.amountPrecision", { currency, digits: problem.digits });
  return (
    <Field label={label} error={error}>
      {(props) => (
        <div className="amount-input" dir="ltr">
          <input
            {...props}
            type="text"
            inputMode="decimal"
            autoComplete="off"
            value={value}
            required={required}
            onChange={(e) => onChange(e.target.value)}
          />
          {onCurrencyChange ? (
            <select aria-label={t("table.currency")} value={currency} onChange={(e) => onCurrencyChange(e.target.value as CurrencyCode)}>
              {CURRENCIES.map((c) => (
                <option key={c}>{c}</option>
              ))}
            </select>
          ) : (
            <span className="currency-code">{currency}</span>
          )}
        </div>
      )}
    </Field>
  );
}

/** Date-only value (YYYY-MM-DD); never converted to a timestamp. */
export function DateField({
  label,
  value,
  onChange,
  required,
  max,
  hint,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  required?: boolean;
  /** Latest allowed date (YYYY-MM-DD), e.g. today for recorded transactions. */
  max?: string;
  hint?: string;
}) {
  const { t } = useI18n();
  let error: string | null = null;
  if (value && !/^\d{4}-\d{2}-\d{2}$/.test(value)) error = t("form.dateInvalid");
  else if (value && max && value > max) error = t("error.futureDate");
  return (
    <Field label={label} error={error} hint={hint}>
      {(props) => <input {...props} type="date" value={value} max={max} required={required} onChange={(e) => onChange(e.target.value)} />}
    </Field>
  );
}

export function CurrencySelect({ label, hint, value, onChange }: { label: string; hint?: string; value: string; onChange: (value: CurrencyCode) => void }) {
  return (
    <Field label={label} hint={hint}>
      {(props) => (
        <select {...props} value={value} onChange={(e) => onChange(e.target.value as CurrencyCode)}>
          {CURRENCIES.map((c) => (
            <option key={c}>{c}</option>
          ))}
        </select>
      )}
    </Field>
  );
}

export function TimeZoneSelect({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  const zones = useMemo(() => {
    const all = Intl.supportedValuesOf("timeZone");
    return all.includes(value) ? all : [value, ...all];
  }, [value]);
  return (
    <Field label={label}>
      {(props) => (
        <select {...props} value={value} onChange={(e) => onChange(e.target.value)}>
          {zones.map((z) => (
            <option key={z}>{z}</option>
          ))}
        </select>
      )}
    </Field>
  );
}

export function LanguageSelect({ label, hint, value, onChange }: { label: string; hint?: string; value: string; onChange: (value: string) => void }) {
  return (
    <Field label={label} hint={hint}>
      {(props) => (
        <select {...props} value={value} onChange={(e) => onChange(e.target.value)}>
          {LOCALES.map((l) => (
            <option key={l.code} value={l.code} lang={l.code}>
              {l.nativeName}
            </option>
          ))}
        </select>
      )}
    </Field>
  );
}
