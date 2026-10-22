// Mirrors backend/app/money.py. Amounts are validated as strings and never parsed to floats.
export const CURRENCY_PRECISION = {
  BDT: 2,
  USD: 2,
  AUD: 2,
  EUR: 2,
  CNY: 2,
  INR: 2,
  GBP: 2,
  AED: 2,
  SAR: 2,
  JPY: 0,
} as const;

export type CurrencyCode = keyof typeof CURRENCY_PRECISION;
export const CURRENCIES = Object.keys(CURRENCY_PRECISION) as CurrencyCode[];

const DECIMAL = /^\d{1,15}(\.\d{1,8})?$/;

export type AmountProblem = null | { kind: "invalid" } | { kind: "precision"; digits: number };

export function checkAmount(value: string, currency: CurrencyCode): AmountProblem {
  const text = value.trim();
  if (!DECIMAL.test(text)) return { kind: "invalid" };
  const fraction = text.split(".")[1] ?? "";
  const digits = CURRENCY_PRECISION[currency];
  // Trailing zeros beyond the precision are harmless ("10.00" JPY is still 10).
  if (fraction.replace(/0+$/, "").length > digits) return { kind: "precision", digits };
  return null;
}
